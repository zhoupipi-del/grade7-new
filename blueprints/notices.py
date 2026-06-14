"""通知公告模块 — 发布通知/回执追踪"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from models import db, Student, Class, Grade, User, Notice, NoticeReceipt
from decorators import login_required, require_role, scope_query
from datetime import datetime
from utils.db_utils import safe_commit
from blueprints.common import notify_parent
from blueprints.audit_log import audit_log

notices_bp = Blueprint("notices", __name__)


# ── 通知列表 ──
@notices_bp.route("/")
@login_required
def notice_list():
    notices = scope_query(Notice).order_by(Notice.created_at.desc()).all()
    role = session.get("role", "")
    return render_template("notices/list.html", notices=notices, role=role)


# ── 发布通知表单 ──
@notices_bp.route("/create")
@require_role("ms_admin", "grade_leader", "class_teacher")
def create_form():
    role = session.get("role", "")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")

    if role == "ms_admin":
        grades = Grade.query.order_by(Grade.sort_order).all()
        classes = Class.query.join(Grade).order_by(Grade.sort_order, Class.name).all()
    elif role == "grade_leader":
        grades = [Grade.query.get(grade_id)]
        classes = Class.query.filter_by(grade_id=grade_id).order_by(Class.name).all()
    else:
        grades = []
        classes = [Class.query.get(class_id)]

    return render_template("notices/create.html", grades=grades, classes=classes, role=role)


# ── 保存通知 ──
@notices_bp.route("/create", methods=["POST"])
@require_role("ms_admin", "grade_leader", "class_teacher")
@audit_log("create_notice", "Notice")
def create_notice():
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    grade_id = request.form.get("grade_id", type=int)
    class_id = request.form.get("class_id", type=int)
    require_receipt = bool(request.form.get("require_receipt"))

    if not title:
        flash("通知标题不能为空", "danger")
        return redirect(url_for("notices.create_form"))

    notice = Notice(
        title=title,
        content=content,
        class_id=class_id if class_id else None,
        grade_id=grade_id if grade_id else None,
        require_receipt=require_receipt,
        created_by=session.get("display_name", ""),
        created_by_id=session.get("user_id"),
    )
    db.session.add(notice)
    db.session.flush()

    # 如果需要回执，自动为相关学生创建回执记录
    if require_receipt:
        students = _get_target_students(notice)
        for s in students:
            receipt = NoticeReceipt(notice_id=notice.id, student_id=s.id)
            db.session.add(receipt)

    safe_commit()

    # 通知目标学生家长
    from_user_id = session.get("user_id")
    target_students = _get_target_students(notice)
    for stu in target_students:
        notify_parent(
            stu,
            title=f"新通知 — {title}",
            content=f"【{title}】\n"
                    f"发布人：{session.get('display_name', '老师')}\n"
                    f"内容预览：{content[:200] if content else '请登录系统查看'}",
            from_user_id=from_user_id,
        )

    flash("通知已发布", "success")
    return redirect(url_for("notices.notice_list"))


# ── 删除通知 ──
@notices_bp.route("/<int:nid>/delete", methods=["POST"])
@require_role("ms_admin", "grade_leader", "class_teacher")
def delete_notice(nid):
    notice = Notice.query.get_or_404(nid)
    db.session.delete(notice)
    safe_commit()
    flash("通知已删除", "success")
    return redirect(url_for("notices.notice_list"))


# ── 回执状态查看 ──
@notices_bp.route("/<int:nid>/receipts")
@login_required
def receipt_list(nid):
    notice = Notice.query.get_or_404(nid)
    receipts = NoticeReceipt.query.filter_by(notice_id=nid).all()

    # 补充未创建回执的学生（兼容未开启回执时的情况）
    student_map = {}
    for r in receipts:
        student_map[r.student_id] = r
    students = _get_target_students(notice)

    total = len(students)
    read_count = sum(1 for r in receipts if r.status in ("read", "signed"))
    signed_count = sum(1 for r in receipts if r.status == "signed")

    return render_template("notices/receipts.html",
                           notice=notice, students=students, receipts=receipts,
                           student_map=student_map,
                           total=total, read_count=read_count, signed_count=signed_count)


# ── 标记已读（API） ──
@notices_bp.route("/<int:nid>/mark_read", methods=["POST"])
@login_required
def mark_read(nid):
    notice = Notice.query.get_or_404(nid)
    student_id = request.json.get("student_id") if request.is_json else request.form.get("student_id", type=int)

    if not student_id:
        return jsonify({"ok": False, "msg": "缺少 student_id"}), 400

    receipt = NoticeReceipt.query.filter_by(notice_id=nid, student_id=student_id).first()
    if not receipt:
        # 自动创建回执记录
        receipt = NoticeReceipt(notice_id=nid, student_id=student_id)

    if receipt.status == "unread":
        receipt.status = "read"
        receipt.read_at = datetime.utcnow()
        db.session.add(receipt)
        safe_commit()

    return jsonify({"ok": True, "status": receipt.status})


# ── 标记已签收（API） ──
@notices_bp.route("/<int:nid>/mark_signed", methods=["POST"])
@login_required
def mark_signed(nid):
    notice = Notice.query.get_or_404(nid)
    student_id = request.json.get("student_id") if request.is_json else request.form.get("student_id", type=int)
    signed_by = request.json.get("signed_by") if request.is_json else request.form.get("signed_by", session.get("display_name", ""))

    if not student_id:
        return jsonify({"ok": False, "msg": "缺少 student_id"}), 400

    receipt = NoticeReceipt.query.filter_by(notice_id=nid, student_id=student_id).first()
    if not receipt:
        receipt = NoticeReceipt(notice_id=nid, student_id=student_id)

    now = datetime.utcnow()
    if receipt.status == "unread":
        receipt.read_at = now
    receipt.status = "signed"
    receipt.signed_at = now
    receipt.signed_by = signed_by
    db.session.add(receipt)
    safe_commit()

    return jsonify({"ok": True, "status": receipt.status})


# ── 辅助：获取通知目标学生 ──
def _get_target_students(notice):
    q = Student.query.filter_by(is_active=True)
    if notice.class_id:
        q = q.filter_by(class_id=notice.class_id)
    elif notice.grade_id:
        q = q.filter_by(grade_id=notice.grade_id)
    return q.order_by(Student.class_id, Student.student_no).all()
