"""学生标签管理"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from functools import wraps

from decorators import login_required, require_role
from models import db, Student, Class, User
from utils.db_utils import safe_commit

tags_bp = Blueprint("tags", __name__, url_prefix="/tags")


@tags_bp.route("/")
@login_required
def index():
    """标签管理页"""
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login_page"))
    user = db.session.get(User, user_id)
    students = Student.query.filter(Student.is_active == True)

    if user.role == "class_teacher" and user.class_id:
        students = students.filter(Student.class_id == user.class_id)
    elif user.role == "grade_leader" and user.grade_id:
        students = students.filter(Student.grade_id == user.grade_id)

    # filter
    tag_filter = request.args.get("tag", "")
    class_id = request.args.get("class_id", "", type=int)
    search = request.args.get("search", "")
    page = request.args.get("page", 1, type=int)
    per_page = 30

    if tag_filter:
        students = students.filter(Student.tags.contains(tag_filter))
    if class_id:
        students = students.filter(Student.class_id == class_id)
    if search:
        students = students.filter(
            db.or_(Student.name.contains(search), Student.student_no.contains(search))
        )

    pagination = students.order_by(Student.class_id, Student.student_no).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # 优化: 只查 tags 列, 不加载完整 Student 对象
    tag_rows = db.session.query(Student.tags).filter(
        Student.tags.isnot(None), Student.tags != ""
    ).all()
    all_tags = set()
    for (tags_str,) in tag_rows:
        if tags_str:
            for t in tags_str.split(","):
                t = t.strip()
                if t:
                    all_tags.add(t)

    return render_template("tags/index.html",
                           pagination=pagination, all_tags=sorted(all_tags),
                           tag_filter=tag_filter,
                           class_id=class_id, search=search)


@tags_bp.route("/update", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def update():
    """更新学生标签"""
    student_id = request.form.get("student_id", type=int)
    tags_str = request.form.get("tags", "").strip()
    # clean: dedupe, strip whitespace
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]
    tags_str = ",".join(dict.fromkeys(tags))  # dedupe preserve order

    student = Student.query.get_or_404(student_id)
    if session.get("role") == "class_teacher" and student.class_id != session.get("class_id"):
        flash("无权操作该学生", "danger")
        return redirect(request.form.get("next", url_for("tags.index")))
    student.tags = tags_str
    safe_commit()
    flash("标签已更新", "success")

    # stay on same page with filters
    return redirect(request.form.get("next", url_for("tags.index")))


@tags_bp.route("/batch-tag", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def batch_tag():
    """批量添加标签"""
    student_ids = request.form.getlist("student_ids", type=int)
    add_tag = request.form.get("add_tag", "").strip()
    remove_tag = request.form.get("remove_tag", "").strip()

    if not student_ids:
        flash("未选择学生", "warning")
        return redirect(url_for("tags.index"))

    count = 0
    for sid in student_ids:
        student = Student.query.get(sid)
        if not student:
            continue
        # 班主任只能操作本班学生
        if session.get("role") == "class_teacher" and student.class_id != session.get("class_id"):
            continue
        tags = [t.strip() for t in student.tags.split(",") if t.strip()]

        if add_tag and add_tag not in tags:
            tags.append(add_tag)
        if remove_tag and remove_tag in tags:
            tags.remove(remove_tag)

        student.tags = ",".join(tags)
        count += 1

    safe_commit()
    flash(f"已更新 {count} 名学生的标签", "success")
    return redirect(request.form.get("next", url_for("tags.index")))
