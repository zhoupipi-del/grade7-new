"""年级组工作台 — 接收任务/分配班主任/年级数据/审批"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from sqlalchemy.orm import joinedload
from models import db, Student, Class, Grade, User, Task, TaskFeedback
from models import DisciplineRecord, RoutineScore, Attendance, LeaveRequest, ProblemStudent
from models import Message
from blueprints.discipline_utils import check_escalation, send_discipline_notifications, deduct_quality_score
from blueprints.common import notify_parent
from blueprints.audit_log import audit_log
from decorators import login_required, require_role, scope_query
from utils.db_utils import safe_commit
from datetime import date, datetime, timedelta

grade_bp = Blueprint("grade", __name__)


@grade_bp.before_request
@login_required
@require_role("grade_leader")
def check_role():
    pass


# ── 年级工作台首页 ──
@grade_bp.route("/")
def dashboard():
    grade_id = session.get("grade_id")
    stats = {
        "student_count": Student.query.filter_by(grade_id=grade_id, is_active=True).count(),
        "class_count": Class.query.filter_by(grade_id=grade_id, is_active=True).count(),
        "discipline_week": DisciplineRecord.query.filter(
            DisciplineRecord.grade_id == grade_id, DisciplineRecord.status == "active"
        ).count(),
        "pending_tasks": Task.query.filter_by(target_type="grade", target_id=grade_id,
                                               status="pending").count(),
    }
    classes = Class.query.filter_by(grade_id=grade_id).all()
    recent_disciplines = DisciplineRecord.query.filter_by(grade_id=grade_id).order_by(
        DisciplineRecord.created_at.desc()).limit(10).all()
    return render_template("grade/dashboard.html", stats=stats, classes=classes,
                           recent_disciplines=recent_disciplines)


# ── 任务中心 ──
@grade_bp.route("/tasks")
def task_list():
    grade_id = session.get("grade_id")
    tasks = Task.query.filter(
        (Task.target_type == "grade") & (Task.target_id == grade_id)
    ).order_by(Task.created_at.desc()).all()
    classes = Class.query.filter_by(grade_id=grade_id, is_active=True).order_by(Class.name).all()
    return render_template("grade/tasks.html", tasks=tasks, classes=classes)


@grade_bp.route("/tasks/<int:tid>/assign", methods=["POST"])
def assign_task(tid):
    """年级组长将德育处任务分配给班主任（支持多选）"""
    from utils.db_utils import safe_commit
    task = Task.query.get_or_404(tid)
    class_ids = request.form.getlist("class_ids")
    if not class_ids:
        flash("请选择目标班级", "danger")
        return redirect(url_for("grade.task_list"))
    for cid in class_ids:
        # 创建子任务分发给班主任
        sub_task = Task(
            title=task.title,
            content=task.content,
            from_role="grade_leader",
            from_user_id=session.get("user_id"),
            target_type="class",
            target_id=int(cid),
            deadline=task.deadline,
        )
        db.session.add(sub_task)
    # 更新母任务状态
    task.status = "assigned"
    safe_commit()
    flash(f"已分配给 {len(class_ids)} 个班级", "success")
    return redirect(url_for("grade.task_list"))


@grade_bp.route("/tasks/<int:tid>/feedback", methods=["POST"])
def task_feedback(tid):
    from utils.db_utils import safe_commit
    fb = TaskFeedback(
        task_id=tid,
        user_id=session.get("user_id"),
        content=request.form["content"],
    )
    db.session.add(fb)
    # 如果年级组想关闭任务
    task = Task.query.get(tid)
    if task and request.form.get("action") == "close":
        task.status = "done"
        task.finished_at = datetime.utcnow()
    safe_commit()
    flash("反馈已提交", "success")
    return redirect(url_for("grade.task_list"))


# ── 纪律管理 — 本年级 ──
@grade_bp.route("/discipline")
def discipline_list():
    grade_id = session.get("grade_id")
    page = request.args.get("page", 1, type=int)
    class_filter = request.args.get("class_id", type=int)
    level_filter = request.args.get("level", type=str)  # warning / minor / major
    q = DisciplineRecord.query.filter_by(grade_id=grade_id)
    if class_filter:
        q = q.filter_by(class_id=class_filter)
    if level_filter:
        q = q.filter_by(type=level_filter)
    records = q.options(
        joinedload(DisciplineRecord.student).joinedload(Student.class_)
    ).order_by(DisciplineRecord.created_at.desc()).paginate(page=page, per_page=20)
    classes = Class.query.filter_by(grade_id=grade_id).all()
    students = Student.query.filter_by(grade_id=grade_id, is_active=True).options(
        joinedload(Student.class_)
    ).order_by(Student.class_id, Student.student_no).all()
    return render_template("grade/discipline.html", records=records, classes=classes,
                           students=students, class_filter=class_filter, level_filter=level_filter)


# ── 常规评分 — 本年级 ──
@grade_bp.route("/routine")
def routine_overview():
    grade_id = session.get("grade_id")
    today = date.today()
    scores = RoutineScore.query.filter_by(grade_id=grade_id).order_by(
        RoutineScore.record_date.desc()).limit(100).all()
    classes = Class.query.filter_by(grade_id=grade_id).all()
    return render_template("grade/routine.html", scores=scores, classes=classes)


# ── 考勤总览 ──
@grade_bp.route("/attendance")
def attendance_overview():
    grade_id = session.get("grade_id")
    today = date.today()
    records = Attendance.query.filter_by(grade_id=grade_id, record_date=today).all()
    classes = Class.query.filter_by(grade_id=grade_id).all()
    return render_template("grade/attendance.html", records=records, classes=classes)


# ── 请假审批 ──
@grade_bp.route("/leaves")
def leave_list():
    grade_id = session.get("grade_id")
    leaves = LeaveRequest.query.filter_by(grade_id=grade_id).options(
        joinedload(LeaveRequest.student).joinedload(Student.class_)
    ).order_by(
        LeaveRequest.created_at.desc()).limit(50).all()
    return render_template("grade/leaves.html", leaves=leaves)


@grade_bp.route("/leaves/<int:lid>/approve", methods=["POST"])
@audit_log("approve_leave_grade", "LeaveRequest")
def approve_leave(lid):
    leave = LeaveRequest.query.get_or_404(lid)
    if leave.grade_id != session.get("grade_id") or leave.status != "class_approved":
        flash("无法审批", "danger")
        return redirect(url_for("grade.leave_list"))
    action = request.form.get("action")
    if action == "approve":
        leave.status = "grade_approved"
        leave.grade_approved_by = session.get("user_id")
        leave.grade_approved_at = date.today()
    else:
        leave.status = "rejected"
    safe_commit()

    # ── 请假批准后自动创建考勤记录 ──
    if leave.status == "grade_approved":
        _create_leave_attendance(leave)

    # 通知家长
    student = Student.query.get(leave.student_id)
    if student:
        from_user_id = session.get("user_id")
        action_label = "已通过（年级审批）" if leave.status == "grade_approved" else "已被驳回"
        notify_parent(
            student,
            title=f"请假审批结果 — {student.name}",
            content=f"您孩子 {student.name} 的请假申请{action_label}。\n"
                    f"请假时间：{leave.start_date} ~ {leave.end_date}\n"
                    f"请假原因：{leave.reason}",
            from_user_id=from_user_id,
        )

    flash("审批完成", "success")
    return redirect(url_for("grade.leave_list"))


# ── 批量请假审批 ──
@grade_bp.route("/leaves/batch-approve", methods=["POST"])
@audit_log("batch_approve_leaves", "LeaveRequest")
def batch_approve_leaves():
    """批量审批请假（JSON API）"""
    data = request.get_json(force=True)
    leave_ids = data.get("leave_ids", [])
    action = data.get("action", "approve")

    if not leave_ids:
        return jsonify({"code": 1, "msg": "未选择任何记录"})

    grade_id = session.get("grade_id")
    today = date.today()
    approved_count = 0
    rejected_ids = []
    approved_leaves = []

    for lid in leave_ids:
        leave = LeaveRequest.query.get(int(lid))
        if not leave:
            continue
        if leave.grade_id != grade_id or leave.status != "class_approved":
            rejected_ids.append(lid)
            continue

        if action == "approve":
            leave.status = "grade_approved"
            leave.grade_approved_by = session.get("user_id")
            leave.grade_approved_at = today
        else:
            leave.status = "rejected"

        db.session.flush()  # 确保每条都提交到事务中
        approved_leaves.append(leave)
        approved_count += 1

    safe_commit()

    # ── 批量审批后自动创建考勤记录 ──
    att_count = 0
    for leave in approved_leaves:
        if leave.status == "grade_approved":
            att_count += _create_leave_attendance(leave)

    # 通知家长
    from_user_id = session.get("user_id")
    for leave in approved_leaves:
        student = Student.query.get(leave.student_id)
        if student:
            action_label = "已通过（年级审批）" if leave.status == "grade_approved" else "已被驳回"
            notify_parent(
                student,
                title=f"请假审批结果 — {student.name}",
                content=f"您孩子 {student.name} 的请假申请{action_label}。\n"
                        f"请假时间：{leave.start_date} ~ {leave.end_date}\n"
                        f"请假原因：{leave.reason}",
                from_user_id=from_user_id,
            )

    if rejected_ids:
        return jsonify({
            "code": 0,
            "msg": f"已处理 {approved_count} 条（{len(rejected_ids)} 条状态不符跳过）",
            "approved": approved_count,
            "skipped": len(rejected_ids),
        })
    else:
        return jsonify({
            "code": 0,
            "msg": f"已成功{('审批通过' if action=='approve' else '驳回')} {approved_count} 条请假申请",
            "approved": approved_count,
            "skipped": 0,
        })


# ── 问题学生 — 本年级 ──
@grade_bp.route("/problem-students")
def problem_list():
    grade_id = session.get("grade_id")
    records = ProblemStudent.query.filter_by(grade_id=grade_id).order_by(
        ProblemStudent.level, ProblemStudent.updated_at.desc()).all()
    return render_template("grade/problem_list.html", records=records)


# ══════════════════════════════════════════
#  年级组录入功能（对全年级各班操作）
# ══════════════════════════════════════════

# ── 违纪录入 ──
@grade_bp.route("/discipline/add", methods=["POST"])
@audit_log("add_discipline_grade", "DisciplineRecord")
def add_discipline():
    from utils.db_utils import safe_commit
    grade_id = session.get("grade_id")
    student_id = request.form.get("student_id", type=int)
    student = Student.query.get(student_id)
    if not student or student.grade_id != grade_id:
        flash("学生不存在或不在本年级", "danger")
        return redirect(url_for("grade.discipline_list"))
    record = DisciplineRecord(
        student_id=student.id,
        class_id=student.class_id,
        grade_id=grade_id,
        type=request.form["type"],
        category=request.form.get("category", ""),
        description=request.form["description"],
        action_taken=request.form.get("action_taken", ""),
        points=request.form.get("points", 0, type=int),
        created_by=session.get("user_id"),
        verify_status="VERIFIED",
    )
    db.session.add(record)
    # 积分累计自动升级 + 通知（同一个事务）
    check_escalation(student, session.get("user_id"))
    send_discipline_notifications(record, student)
    deduct_quality_score(record, student, session.get("user_id"))

    safe_commit()
    flash(f"已记录 {student.name} 违纪", "success")
    return redirect(url_for("grade.discipline_list"))


@grade_bp.route("/discipline/<int:rid>/delete", methods=["POST"])
def delete_discipline(rid):
    record = DisciplineRecord.query.get_or_404(rid)
    if record.grade_id != session.get("grade_id"):
        flash("无权操作", "danger")
        return redirect(url_for("grade.discipline_list"))
    db.session.delete(record)
    safe_commit()
    flash("违纪记录已删除", "success")
    return redirect(url_for("grade.discipline_list"))


@grade_bp.route("/discipline/<int:rid>/resolve", methods=["POST"])
def resolve_discipline(rid):
    from utils.db_utils import safe_commit
    record = DisciplineRecord.query.get_or_404(rid)
    if record.grade_id != session.get("grade_id"):
        flash("无权操作", "danger")
        return redirect(url_for("grade.discipline_list"))
    record.status = "resolved"
    record.resolved_at = datetime.utcnow()
    safe_commit()
    flash("已标记为已解决", "success")
    return redirect(url_for("grade.discipline_list"))


# ── 常规评分录入 ──
@grade_bp.route("/routine/add", methods=["POST"])
def add_routine():
    grade_id = session.get("grade_id")
    class_id = request.form.get("class_id", type=int)
    cls = Class.query.get(class_id)
    if not cls or cls.grade_id != grade_id:
        flash("班级不存在或不在本年级", "danger")
        return redirect(url_for("grade.routine_overview"))
    record_date = request.form.get("record_date", str(date.today()))
    score = RoutineScore(
        class_id=class_id,
        grade_id=grade_id,
        category=request.form["category"],
        score=request.form.get("score", 0, type=int),
        note=request.form.get("note", ""),
        inspector=session.get("display_name", ""),
        record_date=date.fromisoformat(record_date) if record_date else date.today(),
    )
    db.session.add(score)
    safe_commit()
    flash("评分已录入", "success")
    return redirect(url_for("grade.routine_overview"))


@grade_bp.route("/routine/<int:sid>/delete", methods=["POST"])
def delete_routine(sid):
    s = RoutineScore.query.get_or_404(sid)
    if s.grade_id != session.get("grade_id"):
        flash("无权操作", "danger")
        return redirect(url_for("grade.routine_overview"))
    db.session.delete(s)
    safe_commit()
    flash("评分已删除", "success")
    return redirect(url_for("grade.routine_overview"))


# ── 考勤录入 ──
@grade_bp.route("/attendance/record", methods=["POST"])
def record_attendance():
    grade_id = session.get("grade_id")
    class_id = request.form.get("class_id", type=int)
    cls = Class.query.get(class_id)
    if not cls or cls.grade_id != grade_id:
        flash("班级不存在或不在本年级", "danger")
        return redirect(url_for("grade.attendance_overview"))
    record_date_str = request.form.get("record_date", str(date.today()))
    record_date_obj = date.fromisoformat(record_date_str)
    # 批量处理该班学生考勤
    students = Student.query.filter_by(class_id=class_id, is_active=True).all()
    count = 0
    for s in students:
        status_key = f"status_{s.id}"
        if status_key in request.form:
            status_val = request.form[status_key]
            note_key = f"note_{s.id}"
            note_val = request.form.get(note_key, "")
            # 检查是否已有今日记录
            existing = Attendance.query.filter_by(
                student_id=s.id, record_date=record_date_obj
            ).first()
            if existing:
                existing.status = status_val
                existing.note = note_val
            else:
                att = Attendance(
                    student_id=s.id,
                    class_id=class_id,
                    grade_id=grade_id,
                    status=status_val,
                    record_date=record_date_obj,
                    note=note_val,
                )
                db.session.add(att)
            count += 1
    safe_commit()
    flash(f"已录入 {cls.name} {count} 名学生考勤", "success")
    return redirect(url_for("grade.attendance_overview"))


# ── 请假→考勤自动创建 ─────────────────────────────
def _create_leave_attendance(leave):
    """请假批准后，自动创建对应日期的考勤记录（status=leave）

    只在年级组长最终审批通过（grade_approved）时调用。
    跳过已有考勤记录的日期（避免覆盖手动录入）。
    返回创建的记录数。
    """
    if leave.status != "grade_approved":
        return 0

    # 获取日期范围内已有的考勤日期
    existing_dates = set(
        r[0] for r in db.session.query(Attendance.record_date).filter(
            Attendance.student_id == leave.student_id,
            Attendance.record_date >= leave.start_date,
            Attendance.record_date <= leave.end_date,
        ).all()
    )

    count = 0
    current = leave.start_date
    while current <= leave.end_date:
        if current not in existing_dates:
            att = Attendance(
                student_id=leave.student_id,
                class_id=leave.class_id,
                grade_id=leave.grade_id,
                status="leave",
                record_date=current,
                note=f"请假：{leave.reason[:50]}",
            )
            db.session.add(att)
            count += 1
        current += timedelta(days=1)

    if count > 0:
        safe_commit()
        print(f"[grade] 请假#{leave.id} 批准，已自动创建 {count} 条考勤记录")

    return count
