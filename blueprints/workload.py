"""教师工作量统计"""
from flask import Blueprint, render_template, request, send_file, session
from utils import get_local_now
from datetime import datetime, timedelta
from io import BytesIO
import openpyxl

from decorators import login_required, require_role
from models import db, User, DisciplineRecord, RoutineScore, Task, HomeVisit, LeaveRequest, EndTermComment, WingsScore, QualityScore

workload_bp = Blueprint("workload", __name__, url_prefix="/workload")


@workload_bp.route("/")
@login_required
@require_role("ms_admin", "grade_leader")
def index():
    """教师工作量仪表板"""
    user = db.session.get(User, session.get("user_id"))
    days = request.args.get("days", 30, type=int)

    since = get_local_now() - timedelta(days=days)
    grade_id = user.grade_id if user.role == "grade_leader" else None

    # gather stats per teacher
    teachers = User.query.filter(User.role.in_(["class_teacher", "grade_leader", "ms_admin"]))
    if grade_id:
        teachers = teachers.filter(User.grade_id == grade_id)
    teachers = teachers.all()

    stats = []
    for t in teachers:
        # DisciplineRecord: created_by = user.id
        d_query = DisciplineRecord.query.filter(DisciplineRecord.created_by == t.id)
        d_query = d_query.filter(DisciplineRecord.created_at >= since)
        # RoutineScore: inspector field stores the name
        r_query = RoutineScore.query.filter(RoutineScore.inspector == t.display_name)
        r_query = r_query.filter(RoutineScore.created_at >= since)
        # Task: from_user_id = user.id
        t_query = Task.query.filter(Task.from_user_id == t.id)
        t_query = t_query.filter(Task.created_at >= since)
        # HomeVisit: created_by_id = user.id
        h_query = HomeVisit.query.filter(HomeVisit.created_by_id == t.id)
        h_query = h_query.filter(HomeVisit.created_at >= since)

        if grade_id:
            d_query = d_query.filter(DisciplineRecord.grade_id == grade_id)
            r_query = r_query.filter(RoutineScore.grade_id == grade_id)
            h_query = h_query.filter(HomeVisit.grade_id == grade_id)

        d_count = d_query.count()
        r_count = r_query.count()
        ta_count = t_query.count()
        h_count = h_query.count()

        # 新增维度
        # 请假审批工作量 (班主任审批 + 年级组长审批)
        leave_count = LeaveRequest.query.filter(
            LeaveRequest.class_approved_by == t.id,
            LeaveRequest.class_approved_at >= since,
        ).count()
        leave_count += LeaveRequest.query.filter(
            LeaveRequest.grade_approved_by == t.id,
            LeaveRequest.grade_approved_at >= since,
        ).count()

        # 期末评语撰写量
        comment_count = EndTermComment.query.filter(
            EndTermComment.created_by_id == t.id,
            EndTermComment.created_at >= since,
        ).count()

        # 五翼评分工作量
        wings_count = WingsScore.query.filter(
            WingsScore.scorer_id == t.id,
            WingsScore.created_at >= since,
        ).count()

        # 综合素质评分工作量
        quality_count = QualityScore.query.filter(
            QualityScore.scorer_id == t.id,
            QualityScore.scorer_type == "teacher",
            QualityScore.created_at >= since,
        ).count()

        if grade_id:
            leave_count = LeaveRequest.query.filter(
                LeaveRequest.grade_id == grade_id,
                LeaveRequest.class_approved_at >= since,
            ).filter(
                (LeaveRequest.class_approved_by == t.id) | (LeaveRequest.grade_approved_by == t.id)
            ).count()
            comment_count = EndTermComment.query.filter_by(
                created_by_id=t.id, grade_id=grade_id
            ).filter(EndTermComment.created_at >= since).count()
            wings_count = WingsScore.query.filter_by(
                scorer_id=t.id, grade_id=grade_id
            ).filter(WingsScore.created_at >= since).count()
            quality_count = QualityScore.query.filter_by(
                scorer_id=t.id, scorer_type="teacher", grade_id=grade_id
            ).filter(QualityScore.created_at >= since).count()

        total = d_count + r_count + ta_count + h_count + leave_count + comment_count + wings_count + quality_count

        stats.append({
            "name": t.display_name,
            "username": t.username,
            "role": t.role,
            "discipline": d_count,
            "routine": r_count,
            "tasks": ta_count,
            "home_visits": h_count,
            "leaves_approved": leave_count,
            "comments": comment_count,
            "wings_scores": wings_count,
            "quality_scores": quality_count,
            "total": total,
        })

    stats.sort(key=lambda x: x["total"], reverse=True)

    # summary
    summary = {
        "total_discipline": sum(s["discipline"] for s in stats),
        "total_routine": sum(s["routine"] for s in stats),
        "total_tasks": sum(s["tasks"] for s in stats),
        "total_home_visits": sum(s["home_visits"] for s in stats),
        "total_leaves": sum(s["leaves_approved"] for s in stats),
        "total_comments": sum(s["comments"] for s in stats),
        "total_wings": sum(s["wings_scores"] for s in stats),
        "total_quality": sum(s["quality_scores"] for s in stats),
        "teacher_count": len(stats),
        "days": days,
    }

    return render_template("workload/index.html", stats=stats, summary=summary, days=days)


@workload_bp.route("/detail")
@login_required
@require_role("ms_admin", "grade_leader")
def detail():
    """教师详情"""
    username = request.args.get("username", "")
    teacher = User.query.filter_by(username=username).first()
    if not teacher:
        return "教师未找到", 404

    days = request.args.get("days", 30, type=int)
    since = get_local_now() - timedelta(days=days)

    disciplines = DisciplineRecord.query.filter(
        DisciplineRecord.created_by == teacher.id,
        DisciplineRecord.created_at >= since
    ).order_by(DisciplineRecord.created_at.desc()).all()

    routines = RoutineScore.query.filter(
        RoutineScore.inspector == teacher.display_name,
        RoutineScore.created_at >= since
    ).order_by(RoutineScore.created_at.desc()).all()

    tasks = Task.query.filter(
        Task.from_user_id == teacher.id,
        Task.created_at >= since
    ).order_by(Task.created_at.desc()).all()

    visits = HomeVisit.query.filter(
        HomeVisit.created_by_id == teacher.id,
        HomeVisit.created_at >= since
    ).order_by(HomeVisit.visit_date.desc()).all()

    return render_template("workload/detail.html",
                           teacher=teacher, days=days,
                           disciplines=disciplines, routines=routines,
                           tasks=tasks, visits=visits)


@workload_bp.route("/export")
@login_required
@require_role("ms_admin", "grade_leader")
def export():
    """导出Excel"""
    user = db.session.get(User, session.get("user_id"))
    grade_id = user.grade_id if user.role == "grade_leader" else None

    teachers = User.query.filter(User.role.in_(["class_teacher", "grade_leader"]))
    if grade_id:
        teachers = teachers.filter(User.grade_id == grade_id)
    teachers = teachers.all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "教师工作量"
    ws.append(["教师", "用户名", "角色", "违纪录入", "评分录入", "任务分配", "家访记录", "请假审批", "期末评语", "五翼评分", "素质评分", "合计"])

    for t in teachers:
        d = DisciplineRecord.query.filter_by(created_by=t.id).count() if grade_id is None else \
            DisciplineRecord.query.filter_by(created_by=t.id, grade_id=grade_id).count()
        r = RoutineScore.query.filter_by(inspector=t.display_name).count() if grade_id is None else \
            RoutineScore.query.filter_by(inspector=t.display_name, grade_id=grade_id).count()
        ta = Task.query.filter_by(from_user_id=t.id).count()
        h = HomeVisit.query.filter_by(created_by_id=t.id).count() if grade_id is None else \
            HomeVisit.query.filter_by(created_by_id=t.id, grade_id=grade_id).count()
        lv = LeaveRequest.query.filter(
            (LeaveRequest.class_approved_by == t.id) | (LeaveRequest.grade_approved_by == t.id)
        ).count() if grade_id is None else \
            LeaveRequest.query.filter_by(grade_id=grade_id).filter(
                (LeaveRequest.class_approved_by == t.id) | (LeaveRequest.grade_approved_by == t.id)
            ).count()
        cm = EndTermComment.query.filter_by(created_by_id=t.id).count() if grade_id is None else \
            EndTermComment.query.filter_by(created_by_id=t.id, grade_id=grade_id).count()
        wg = WingsScore.query.filter_by(scorer_id=t.id).count() if grade_id is None else \
            WingsScore.query.filter_by(scorer_id=t.id, grade_id=grade_id).count()
        qs = QualityScore.query.filter_by(scorer_id=t.id, scorer_type="teacher").count() if grade_id is None else \
            QualityScore.query.filter_by(scorer_id=t.id, scorer_type="teacher", grade_id=grade_id).count()
        total = d + r + ta + h + lv + cm + wg + qs
        ws.append([t.display_name, t.username, t.role, d, r, ta, h, lv, cm, wg, qs, total])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name=f"教师工作量_{datetime.now().strftime('%Y%m%d')}.xlsx")
