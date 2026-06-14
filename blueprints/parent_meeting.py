"""家长会管理模块"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from models import db, Grade, Class, Student, ParentMeeting, ParentMeetingSignin, User
from decorators import login_required, require_role
from datetime import datetime
import json
from utils.db_utils import safe_commit
from blueprints.common import notify_parent
from blueprints.audit_log import audit_log

parent_meeting_bp = Blueprint("parent_meeting", __name__, url_prefix="/parent-meeting")


# ── 列表 ──
@parent_meeting_bp.route("/")
@login_required
def index():
    q = ParentMeeting.query
    role = session.get("role", "")
    if role == "grade_leader":
        q = q.filter_by(grade_id=session.get("grade_id"))
    elif role in ("class_teacher", "teacher"):
        # 只看本班所在年级的家长会
        gid = session.get("grade_id")
        if gid:
            q = q.filter_by(grade_id=gid)
    meetings = q.order_by(ParentMeeting.meeting_date.desc()).all()
    return render_template("parent_meeting/index.html", meetings=meetings)


# ── 创建/编辑 ──
@parent_meeting_bp.route("/create", methods=["GET", "POST"])
@login_required
@require_role("ms_admin", "grade_leader")
@audit_log("create_meeting", "ParentMeeting")
def create():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        meeting_date = request.form.get("meeting_date", "")
        start_time = request.form.get("start_time", "")
        end_time = request.form.get("end_time", "")
        location = request.form.get("location", "")
        grade_id = request.form.get("grade_id", type=int)
        target_classes = request.form.getlist("target_classes")
        description = request.form.get("description", "")
        organizer = session.get("display_name", "")

        if not title or not meeting_date or not grade_id:
            flash("请填写必要信息", "danger")
            return redirect(url_for("parent_meeting.create"))

        pm = ParentMeeting(
            title=title,
            meeting_date=datetime.strptime(meeting_date, "%Y-%m-%d").date(),
            start_time=start_time or None,
            end_time=end_time or None,
            location=location,
            grade_id=grade_id,
            target_classes=json.dumps([int(c) for c in target_classes]),
            description=description,
            organizer=organizer,
            created_by=organizer,
        )
        db.session.add(pm)
        safe_commit()

        # 通知目标学生家长
        from_user_id = session.get("user_id")
        try:
            class_ids = json.loads(pm.target_classes or "[]")
            target_students = Student.query.filter(
                Student.class_id.in_(class_ids),
                Student.is_active == True
            ).all()
            for stu in target_students:
                notify_parent(
                    stu,
                    title=f"家长会通知 — {title}",
                    content=f"【{pm.title}】\n"
                            f"时间：{pm.meeting_date}\n"
                            f"地点：{pm.location or '待定'}\n"
                            f"请家长准时参加。",
                    from_user_id=from_user_id,
                )
        except Exception:
            pass

        flash(f"家长会「{title}」已创建", "success")
        return redirect(url_for("parent_meeting.detail", mid=pm.id))

    grades = Grade.query.order_by(Grade.sort_order).all()
    classes = Class.query.filter_by(is_active=True).all()
    return render_template("parent_meeting/create.html", grades=grades, classes=classes)


@parent_meeting_bp.route("/<int:mid>")
@login_required
def detail(mid):
    pm = ParentMeeting.query.get_or_404(mid)
    signins = ParentMeetingSignin.query.filter_by(meeting_id=mid).order_by(ParentMeetingSignin.signin_time).all()

    # 统计
    try:
        class_ids = json.loads(pm.target_classes or "[]")
    except Exception:
        class_ids = []
    total_students = Student.query.filter(Student.class_id.in_(class_ids), Student.is_active==True).count()
    signed_count = len(signins)
    late_count = sum(1 for s in signins if s.is_late)

    # 手动签到可选学生
    students_for_signin = Student.query.filter(Student.class_id.in_(class_ids), Student.is_active==True).order_by(Student.student_no).all()

    return render_template("parent_meeting/detail.html",
                           meeting=pm, signins=signins,
                           total_students=total_students,
                           signed_count=signed_count,
                           late_count=late_count,
                           students_for_signin=students_for_signin)


# ── 签到 ──
@parent_meeting_bp.route("/<int:mid>/signin", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def signin(mid):
    student_id = request.form.get("student_id", type=int)
    parent_name = request.form.get("parent_name", "").strip()
    phone = request.form.get("phone", "")
    is_late = request.form.get("is_late") == "on"
    notes = request.form.get("notes", "")

    if not student_id or not parent_name:
        flash("请填写完整信息", "danger")
        return redirect(url_for("parent_meeting.detail", mid=mid))

    existing = ParentMeetingSignin.query.filter_by(meeting_id=mid, student_id=student_id).first()
    if existing:
        flash("该学生已签到", "warning")
        return redirect(url_for("parent_meeting.detail", mid=mid))

    si = ParentMeetingSignin(
        meeting_id=mid,
        student_id=student_id,
        parent_name=parent_name,
        phone=phone,
        is_late=is_late,
        notes=notes,
    )
    db.session.add(si)
    safe_commit()
    flash("签到成功", "success")
    return redirect(url_for("parent_meeting.detail", mid=mid))


# ── 批量签到 ──
@parent_meeting_bp.route("/<int:mid>/batch_signin", methods=["GET", "POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def batch_signin(mid):
    pm = ParentMeeting.query.get_or_404(mid)

    if request.method == "POST":
        student_ids = request.form.getlist("student_ids")
        parent_name = request.form.get("parent_name", "").strip() or "家长"
        is_late = request.form.get("is_late") == "on"
        notes = request.form.get("notes", "")

        count = 0
        for sid in student_ids:
            existing = ParentMeetingSignin.query.filter_by(meeting_id=mid, student_id=sid).first()
            if not existing:
                si = ParentMeetingSignin(
                    meeting_id=mid,
                    student_id=int(sid),
                    parent_name=parent_name,
                    is_late=is_late,
                    notes=notes,
                )
                db.session.add(si)
                count += 1
        safe_commit()
        flash(f"已批量签到 {count} 人", "success")
        return redirect(url_for("parent_meeting.detail", mid=mid))

    try:
        class_ids = json.loads(pm.target_classes or "[]")
    except Exception:
        class_ids = []
    students = Student.query.filter(Student.class_id.in_(class_ids), Student.is_active==True).order_by(Student.student_no).all()

    # 已签到的学生ID列表
    signed_student_ids = [s.student_id for s in ParentMeetingSignin.query.filter_by(meeting_id=mid).all()]

    return render_template("parent_meeting/batch_signin.html",
                           meeting=pm, students=students,
                           signed_student_ids=signed_student_ids)


# ── 删除家长会 ──
@parent_meeting_bp.route("/<int:mid>/delete", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader")
def delete_meeting(mid):
    pm = ParentMeeting.query.get_or_404(mid)
    # 删除签到记录
    ParentMeetingSignin.query.filter_by(meeting_id=mid).delete()
    db.session.delete(pm)
    safe_commit()
    flash(f"家长会「{pm.title}」已删除", "success")
    return redirect(url_for("parent_meeting.index"))
