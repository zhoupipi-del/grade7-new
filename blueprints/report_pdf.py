"""PDF 报告单 API — 学生个人报告 + 班级批量报告
单生报告：德育报告单（AI评语 + 成绩走势折线图 + 五维雷达图）
批量报告：全班学生报告合并为单一 PDF
"""
from io import BytesIO

from flask import (
    Blueprint, render_template, request, send_file, session, flash, redirect, url_for
)
from models import Student

from decorators import login_required, require_role

report_pdf_bp = Blueprint("report_pdf", __name__)


@report_pdf_bp.route("/")
@login_required
def index():
    """重定向到班级选择页"""
    return redirect(url_for("report_pdf.class_select"))


def _check_student_access(student_id):
    """权限检查：ms_admin全量 / grade_leader本年级 / class_teacher本班 / parent自己孩子"""
    student = Student.query.get(student_id)
    if not student:
        return None, "学生不存在"

    role = session.get("role", "")

    # 管理员全通
    if role == "ms_admin":
        return student, None

    # 年级组长：同年级
    if role == "grade_leader":
        grade_id = session.get("grade_id")
        if student.grade_id != grade_id:
            return None, "无权查看该学生报告"
        return student, None

    # 班主任：同班级
    if role in ("class_teacher", "teacher"):
        class_id = session.get("class_id")
        if student.class_id != class_id:
            return None, "无权查看该学生报告"
        return student, None

    # 家长：只能看自己孩子
    if role == "parent":
        parent_student_ids = session.get("student_ids", [])
        if isinstance(parent_student_ids, str):
            # 兼容逗号分隔字符串
            parent_student_ids = [int(x) for x in parent_student_ids.split(",") if x.strip()]
        if student_id not in parent_student_ids:
            return None, "无权查看该学生报告"
        return student, None

    return None, "无权查看"


@report_pdf_bp.route("/class-select")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher", "teacher")
def class_select():
    """班级选择页 — ms_admin全量 / grade_leader本年级 / class_teacher本班"""
    from models import Class, Grade, Student
    from sqlalchemy import func as safunc
    role = session.get("role", "")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")

    if role == "ms_admin":
        classes = Class.query.order_by(Class.grade_id, Class.name).all()
    elif role in ("class_teacher", "teacher"):
        # 班主任只看自己班级
        classes = Class.query.filter_by(id=class_id).all()
    else:
        classes = Class.query.filter_by(grade_id=grade_id).order_by(Class.name).all()

    # 预计算每班学生数（避免模板中 c.students|length 对懒加载失败）
    class_ids = [c.id for c in classes]
    if class_ids:
        from models import db
        rows = db.session.query(
            Student.class_id, safunc.count(Student.id)
        ).filter(Student.class_id.in_(class_ids)).group_by(Student.class_id).all()
        student_count_map = {row[0]: int(row[1]) for row in rows}
    else:
        student_count_map = {}

    grades = Grade.query.order_by(Grade.name).all()
    return render_template("report_pdf/class_select.html",
                           classes=classes, grades=grades,
                           student_count_map=student_count_map,
                           role=role, grade_id=grade_id)


@report_pdf_bp.route("/student/<int:student_id>")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher", "teacher", "parent")
def student_report(student_id):
    """下载单个学生的德育报告单 PDF

    Query params:
        semester: 学期（可选，默认自动推断当前学期）
    """
    student, error = _check_student_access(student_id)
    if error:
        flash(error, "danger")
        return redirect(url_for("student_profile.detail", sid=student_id))

    semester = request.args.get("semester", None)

    try:
        from utils.pdf_utils import generate_student_report_pdf
        pdf_bytes, filename = generate_student_report_pdf(student_id, semester)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("student_profile.detail", sid=student_id))
    except Exception as e:
        flash(f"PDF 生成失败: {e}", "danger")
        return redirect(url_for("student_profile.detail", sid=student_id))

    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@report_pdf_bp.route("/class/<int:class_id>")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher", "teacher")
def class_reports(class_id):
    """下载全班学生的德育报告单合集 PDF

    Query params:
        semester: 学期（可选，默认自动推断当前学期）
    """
    from models import Class

    # 权限检查
    role = session.get("role", "")
    cls = Class.query.get(class_id)
    if not cls:
        flash("班级不存在", "danger")
        return redirect(request.referrer or url_for("class.student_list"))

    if role == "grade_leader":
        grade_id = session.get("grade_id")
        if cls.grade_id != grade_id:
            flash("无权查看该班级报告", "danger")
            return redirect(url_for("class.student_list"))

    if role in ("class_teacher", "teacher"):
        own_class_id = session.get("class_id")
        if class_id != own_class_id:
            flash("无权查看该班级报告", "danger")
            return redirect(url_for("class.student_list"))

    semester = request.args.get("semester", None)

    try:
        from utils.pdf_utils import generate_class_reports_pdf
        pdf_bytes, filename = generate_class_reports_pdf(class_id, semester)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(request.referrer or url_for("class.student_list"))
    except Exception as e:
        flash(f"PDF 生成失败: {e}", "danger")
        return redirect(request.referrer or url_for("class.student_list"))

    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )
