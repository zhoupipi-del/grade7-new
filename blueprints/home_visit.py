"""家访记录管理"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, session
from datetime import datetime
from io import BytesIO
import openpyxl

from decorators import login_required, require_role
from models import db, HomeVisit, Student, Class, Grade, User, ProblemStudent
from utils.db_utils import safe_commit

home_visit_bp = Blueprint("home_visit", __name__, url_prefix="/home-visits")


@home_visit_bp.route("/")
@login_required
def index():
    """家访记录列表"""
    user = db.session.get(User, session.get("user_id"))
    visits = HomeVisit.query

    # scope filter
    if user.role == "class_teacher" and user.class_id:
        visits = visits.filter(HomeVisit.class_id == user.class_id)
    elif user.role == "grade_leader" and user.grade_id:
        visits = visits.filter(HomeVisit.grade_id == user.grade_id)

    # search/filter
    student_name = request.args.get("student_name", "")
    if student_name:
        visits = visits.join(Student).filter(Student.name.contains(student_name))
    visit_type = request.args.get("visit_type", "")
    if visit_type:
        visits = visits.filter(HomeVisit.visit_type == visit_type)

    visits = visits.order_by(HomeVisit.visit_date.desc()).all()

    visit_types = ["上门家访", "电话家访", "来校面谈", "线上沟通", "其他"]
    classes = Class.query.filter_by(is_active=True).all()
    stats = {
        "total": len(visits),
        "home": sum(1 for v in visits if v.visit_type == "上门家访"),
        "phone": sum(1 for v in visits if v.visit_type == "电话家访"),
        "school": sum(1 for v in visits if v.visit_type == "来校面谈"),
    }

    return render_template("home_visit/index.html",
                           visits=visits, visit_types=visit_types,
                           classes=classes, stats=stats,
                           student_name=student_name, visit_type=visit_type)


@home_visit_bp.route("/create", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def create():
    """新增家访记录"""
    data = request.form
    user = db.session.get(User, session.get("user_id"))

    student_id = data.get("student_id")
    if not student_id:
        flash("缺少学生ID", "danger")
        return redirect(url_for("home_visit.index"))
    student = Student.query.get(student_id)
    if not student:
        flash("学生不存在", "danger")
        return redirect(url_for("home_visit.index"))
    # 班主任只能为本班学生创建家访记录
    if session.get("role") == "class_teacher" and student.class_id != session.get("class_id"):
        flash("无权操作", "danger")
        return redirect(url_for("home_visit.index"))

    visit = HomeVisit(
        student_id=student.id,
        class_id=student.class_id,
        grade_id=student.grade_id,
        visit_date=datetime.strptime(data["visit_date"], "%Y-%m-%d").date(),
        visit_type=data.get("visit_type", "上门家访"),
        content_summary=data.get("content_summary", ""),
        parent_feedback=data.get("parent_feedback", ""),
        teacher_name=data.get("teacher_name", user.display_name),
        follow_up=data.get("follow_up", ""),
        created_by_id=user.id,
    )
    db.session.add(visit)
    safe_commit()

    # ── 家访→问题学生关联：如果该学生是重点关注的active问题学生，自动更新干预记录 ──
    _link_problem_student(student, visit)

    flash("家访记录已保存", "success")
    return redirect(url_for("home_visit.index"))


@home_visit_bp.route("/<int:vid>/delete", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def delete(vid):
    """删除家访记录"""
    visit = HomeVisit.query.get_or_404(vid)
    if session.get("role") == "class_teacher" and visit.class_id != session.get("class_id"):
        flash("无权操作", "danger")
        return redirect(url_for("home_visit.index"))
    db.session.delete(visit)
    safe_commit()
    flash("家访记录已删除", "success")
    return redirect(url_for("home_visit.index"))


@home_visit_bp.route("/export")
@login_required
@require_role("ms_admin", "grade_leader")
def export():
    """导出Excel"""
    user = db.session.get(User, session.get("user_id"))
    visits = HomeVisit.query
    if user.role == "grade_leader" and user.grade_id:
        visits = visits.filter(HomeVisit.grade_id == user.grade_id)
    visits = visits.order_by(HomeVisit.visit_date.desc()).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "家访记录"
    ws.append(["日期", "学生姓名", "班级", "家访方式", "教师", "家访内容", "家长反馈", "后续跟进"])

    for v in visits:
        ws.append([
            v.visit_date.strftime("%Y-%m-%d"),
            v.student.name if v.student else "",
            v.student.class_.name if v.student and v.student.class_ else "",
            v.visit_type,
            v.teacher_name,
            v.content_summary,
            v.parent_feedback,
            v.follow_up,
        ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name=f"家访记录_{datetime.now().strftime('%Y%m%d')}.xlsx")


# ── 家访↔问题学生自动关联 ─────────────────────────────
def _link_problem_student(student, visit):
    """家访后自动关联问题学生记录

    如果该学生是 active/monitoring 状态的问题学生，则：
    1. 更新其 intervention 字段，记录家访信息
    2. 如果之前是 active 状态，尝试转为 monitoring
    """
    problems = ProblemStudent.query.filter(
        ProblemStudent.student_id == student.id,
        ProblemStudent.status.in_(["active", "monitoring"]),
    ).all()

    if not problems:
        return 0

    for ps in problems:
        # 追加家访记录到干预措施
        line = f"\n[{visit.visit_date}] {visit.visit_type}：{visit.content_summary[:60]}{'...' if len(visit.content_summary) > 60 else ''}"
        if ps.intervention:
            ps.intervention = (ps.intervention or "") + line
        else:
            ps.intervention = f"家访记录：{line}"

        # 首次家访后转为 monitoring（持续观察）
        if ps.status == "active":
            ps.status = "monitoring"

    safe_commit()
    print(f"[home_visit] 已关联 {len(problems)} 条问题学生记录（学生 {student.name}）")
    return len(problems)
