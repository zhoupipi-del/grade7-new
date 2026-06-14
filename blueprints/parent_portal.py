"""家长端门户 — 查看孩子考勤/违纪/成绩/通知/评语 + 家长会签到"""
from flask import (
    Blueprint, render_template, session, redirect, url_for,
    jsonify, request, flash
)
from models import (
    db, Student, Class, Grade, Attendance, DisciplineRecord,
    Exam, Score, Subject, Notice, NoticeReceipt,
    EndTermComment, ParentMeeting, ParentMeetingSignin, User, LeaveRequest,
    DisciplineAppeal, RiskRecord, QualityIndicator, QualityScore
)
from decorators import login_required, require_role
from datetime import date, datetime
import json as json_mod
from blueprints.discipline_utils import send_appeal_notifications

parent_portal_bp = Blueprint("parent_portal", __name__, url_prefix="/parent")


# ── 家长首页仪表板 ────────────────────────────────────────────────
@parent_portal_bp.route("/")
@login_required
@require_role("parent")
def dashboard():
    student = _get_my_student()
    if not student:
        return render_template("parent_portal/no_student.html")

    class_obj = Class.query.get(student.class_id)
    grade_obj = Grade.query.get(student.grade_id)

    # 今日考勤
    today = date.today()
    today_att = Attendance.query.filter_by(
        student_id=student.id, record_date=today
    ).first()

    # 本月违纪次数
    month_start = date(today.year, today.month, 1)
    discipline_count = DisciplineRecord.query.filter(
        DisciplineRecord.student_id == student.id,
        DisciplineRecord.created_at >= month_start
    ).count()

    # 未读通知数
    unread_count = NoticeReceipt.query.filter_by(
        student_id=student.id, status="unread"
    ).count()

    # AI风险预警最新状态
    latest_risk = RiskRecord.query.filter_by(
        student_id=student.id
    ).order_by(RiskRecord.scan_date.desc()).first()

    # 最新期末评语
    latest_comment = EndTermComment.query.filter_by(
        student_id=student.id, status="published"
    ).order_by(EndTermComment.created_at.desc()).first()

    # 最近5条考勤记录
    recent_att = Attendance.query.filter_by(
        student_id=student.id
    ).order_by(Attendance.record_date.desc()).limit(5).all()

    # 最近5条违纪记录
    recent_disc = DisciplineRecord.query.filter_by(
        student_id=student.id
    ).order_by(DisciplineRecord.created_at.desc()).limit(5).all()

    # ── 成长数据（五翼 + 成绩趋势） ──
    wings_scores = {}
    indicators = QualityIndicator.query.filter_by(parent_id=0, is_active=True).all()
    for ind in indicators:
        qs = QualityScore.query.filter_by(
            student_id=student.id, indicator_id=ind.id
        ).order_by(QualityScore.created_at.desc()).first()
        if qs:
            wings_scores[ind.name] = qs.score

    # 本月出勤统计
    att_month = Attendance.query.filter(
        Attendance.student_id == student.id,
        Attendance.record_date >= month_start,
    ).all()
    att_present = sum(1 for a in att_month if a.status == "present")
    att_total = len(att_month)

    # 请假统计
    leave_count = LeaveRequest.query.filter(
        LeaveRequest.student_id == student.id
    ).count()
    leave_approved = LeaveRequest.query.filter(
        LeaveRequest.student_id == student.id,
        LeaveRequest.status == "grade_approved"
    ).count()

    return render_template(
        "parent_portal/dashboard.html",
        student=student,
        class_obj=class_obj,
        grade_obj=grade_obj,
        today_att=today_att,
        discipline_count=discipline_count,
        unread_count=unread_count,
        latest_risk=latest_risk,
        latest_comment=latest_comment,
        recent_att=recent_att,
        recent_disc=recent_disc,
        wings_scores=wings_scores,
        att_present=att_present,
        att_total=att_total,
        leave_count=leave_count,
        leave_approved=leave_approved,
        today=today,
    )


# ── 考勤记录 ──────────────────────────────────────────────────────
@parent_portal_bp.route("/attendance")
@login_required
@require_role("parent")
def attendance():
    student = _get_my_student()
    if not student:
        return redirect(url_for("parent_portal.dashboard"))

    # 按月份筛选
    year = request.args.get("year", default=date.today().year, type=int)
    month = request.args.get("month", default=date.today().month, type=int)

    from calendar import monthrange
    _, last_day = monthrange(year, month)
    start = date(year, month, 1)
    end = date(year, month, last_day)

    records = Attendance.query.filter(
        Attendance.student_id == student.id,
        Attendance.record_date >= start,
        Attendance.record_date <= end,
    ).order_by(Attendance.record_date).all()

    # 统计
    stats = {
        "present": sum(1 for r in records if r.status == "present"),
        "late": sum(1 for r in records if r.status == "late"),
        "early": sum(1 for r in records if r.status == "early"),
        "absent": sum(1 for r in records if r.status == "absent"),
        "leave": sum(1 for r in records if r.status == "leave"),
        "total": len(records),
    }

    return render_template(
        "parent_portal/attendance.html",
        student=student,
        records=records,
        stats=stats,
        year=year,
        month=month,
    )


# ── 违纪记录 ──────────────────────────────────────────────────────
@parent_portal_bp.route("/discipline")
@login_required
@require_role("parent")
def discipline():
    student = _get_my_student()
    if not student:
        return redirect(url_for("parent_portal.dashboard"))

    page = request.args.get("page", 1, type=int)
    per_page = 20

    q = DisciplineRecord.query.filter_by(
        student_id=student.id
    ).order_by(DisciplineRecord.created_at.desc())

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    records = pagination.items

    return render_template(
        "parent_portal/discipline.html",
        student=student,
        records=records,
        pagination=pagination,
    )


# ── 成绩查询 ──────────────────────────────────────────────────────
@parent_portal_bp.route("/scores")
@login_required
@require_role("parent")
def scores():
    student = _get_my_student()
    if not student:
        return redirect(url_for("parent_portal.dashboard"))

    # 获取所有考试
    from sqlalchemy import distinct
    exam_ids = db.session.query(distinct(Score.exam_id)).filter(
        Score.student_id == student.id
    ).all()
    exam_ids = [e[0] for e in exam_ids]

    exams = Exam.query.filter(Exam.id.in_(exam_ids)).order_by(
        Exam.exam_date.desc()
    ).all()

    # 当前选中考试
    exam_id = request.args.get("exam_id", type=int)
    if not exam_id and exams:
        exam_id = exams[0].id

    scores = []
    subjects = {}
    total_score = 0
    total_full = 0
    if exam_id:
        scores = Score.query.filter_by(
            student_id=student.id, exam_id=exam_id
        ).all()
        # 优化: 批量预加载所有涉及的科目，避免N+1
        subject_ids = {s.subject_id for s in scores if s.subject_id}
        if subject_ids:
            subject_map = {sub.id: sub for sub in Subject.query.filter(Subject.id.in_(subject_ids)).all()}
        else:
            subject_map = {}
        for s in scores:
            sub = subject_map.get(s.subject_id)
            if sub:
                subjects[s.subject_id] = sub
                total_score += s.score or 0
                total_full += sub.full_score or 100

    avg_score = round(total_score, 1) if scores else 0
    avg_full = round(total_full, 1) if scores else 0

    return render_template(
        "parent_portal/scores.html",
        student=student,
        exams=exams,
        scores=scores,
        subjects=subjects,
        exam_id=exam_id,
        total_score=total_score,
        total_full=total_full,
        avg_score=avg_score,
        avg_full=avg_full,
    )


# ── 通知公告 ──────────────────────────────────────────────────────
@parent_portal_bp.route("/notices")
@login_required
@require_role("parent")
def notices():
    student = _get_my_student()
    if not student:
        return redirect(url_for("parent_portal.dashboard"))

    # 获取发给该学生的通知回执
    page = request.args.get("page", 1, type=int)
    per_page = 15

    q = NoticeReceipt.query.filter_by(
        student_id=student.id
    ).join(NoticeReceipt.notice).order_by(
        Notice.created_at.desc()
    )

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    receipts = pagination.items

    return render_template(
        "parent_portal/notices.html",
        student=student,
        receipts=receipts,
        pagination=pagination,
    )


@parent_portal_bp.route("/notices/<int:nid>/read", methods=["POST"])
@login_required
@require_role("parent")
def mark_notice_read(nid):
    """标记通知已读"""
    student = _get_my_student()
    if not student:
        return jsonify({"error": "未绑定学生"}), 400

    receipt = NoticeReceipt.query.filter_by(
        notice_id=nid, student_id=student.id
    ).first()

    if receipt and receipt.status == "unread":
        receipt.status = "read"
        receipt.read_at = datetime.utcnow()
        safe_commit()

    return jsonify({"ok": True})


@parent_portal_bp.route("/notices/<int:nid>/sign", methods=["POST"])
@login_required
@require_role("parent")
def sign_notice(nid):
    """签收通知（回执）"""
    student = _get_my_student()
    if not student:
        return jsonify({"error": "未绑定学生"}), 400

    receipt = NoticeReceipt.query.filter_by(
        notice_id=nid, student_id=student.id
    ).first()

    if receipt:
        receipt.status = "signed"
        receipt.signed_at = datetime.utcnow()
        receipt.signed_by = session.get("display_name", "")
        safe_commit()
        return jsonify({"ok": True})

    return jsonify({"error": "回执不存在"}), 404


# ── 期末评语 ──────────────────────────────────────────────────────
@parent_portal_bp.route("/comments")
@login_required
@require_role("parent")
def comments():
    student = _get_my_student()
    if not student:
        return redirect(url_for("parent_portal.dashboard"))

    comments = EndTermComment.query.filter_by(
        student_id=student.id, status="published"
    ).order_by(EndTermComment.created_at.desc()).all()

    return render_template(
        "parent_portal/comments.html",
        student=student,
        comments=comments,
    )


# ── 家长会签到 ────────────────────────────────────────────────────
@parent_portal_bp.route("/meeting")
@login_required
@require_role("parent")
def meeting():
    student = _get_my_student()
    if not student:
        return redirect(url_for("parent_portal.dashboard"))

    # 获取该班级/年级的家长会
    meetings = ParentMeeting.query.filter(
        ParentMeeting.grade_id == student.grade_id,
    ).order_by(ParentMeeting.meeting_date.desc()).all()

    # 标记是否已签到
    signed_meetings = {}
    for m in meetings:
        signin = ParentMeetingSignin.query.filter_by(
            meeting_id=m.id, student_id=student.id
        ).first()
        if signin:
            signed_meetings[m.id] = signin

    return render_template(
        "parent_portal/meeting.html",
        student=student,
        meetings=meetings,
        signed_meetings=signed_meetings,
    )


@parent_portal_bp.route("/meeting/<int:mid>/signin", methods=["POST"])
@login_required
@require_role("parent")
def meeting_signin(mid):
    """家长会签到"""
    student = _get_my_student()
    if not student:
        return jsonify({"error": "未绑定学生"}), 400

    # 检查是否已签到
    existing = ParentMeetingSignin.query.filter_by(
        meeting_id=mid, student_id=student.id
    ).first()
    if existing:
        return jsonify({"error": "已签到"}), 400

    parent_name = request.form.get("parent_name", "").strip()
    phone = request.form.get("phone", "").strip()
    is_late = request.form.get("is_late") == "on"

    if not parent_name:
        return jsonify({"error": "请输入家长姓名"}), 400

    signin = ParentMeetingSignin(
        meeting_id=mid,
        student_id=student.id,
        parent_name=parent_name,
        phone=phone,
        is_late=is_late,
    )
    db.session.add(signin)
    safe_commit()

    return jsonify({"ok": True})


# ── 请假申请 ──────────────────────────────────────────────────────
@parent_portal_bp.route("/leave/apply", methods=["GET", "POST"])
@login_required
@require_role("parent")
def leave_apply():
    student = _get_my_student()
    if not student:
        return redirect(url_for("parent_portal.dashboard"))

    if request.method == "POST":
        reason = request.form.get("reason", "").strip()
        start_date = request.form.get("start_date", "")
        end_date = request.form.get("end_date", "")
        if not reason or not start_date or not end_date:
            flash("请填写完整的请假信息", "warning")
            return redirect(url_for("parent_portal.leave_apply"))
        try:
            sd = date.fromisoformat(start_date)
            ed = date.fromisoformat(end_date)
        except ValueError:
            flash("日期格式不正确", "warning")
            return redirect(url_for("parent_portal.leave_apply"))
        if ed < sd:
            flash("结束日期不能早于开始日期", "warning")
            return redirect(url_for("parent_portal.leave_apply"))

        leave = LeaveRequest(
            student_id=student.id,
            class_id=student.class_id,
            grade_id=student.grade_id,
            applicant_id=session.get("user_id"),
            reason=reason,
            start_date=sd,
            end_date=ed,
        )
        db.session.add(leave)
        safe_commit()
        flash("请假申请已提交，请等待班主任审批", "success")
        return redirect(url_for("parent_portal.leave_list"))

    return render_template("parent_portal/leave_apply.html", student=student)


@parent_portal_bp.route("/leaves")
@login_required
@require_role("parent")
def leave_list():
    student = _get_my_student()
    if not student:
        return redirect(url_for("parent_portal.dashboard"))

    leaves = LeaveRequest.query.filter_by(
        student_id=student.id
    ).order_by(LeaveRequest.created_at.desc()).all()

    return render_template("parent_portal/leaves.html", student=student, leaves=leaves)


# ── 纪律申诉 ──────────────────────────────────────────────────────
@parent_portal_bp.route("/appeal/<int:discipline_id>", methods=["GET", "POST"])
@login_required
@require_role("parent")
def appeal(discipline_id):
    """家长提交申诉"""
    from utils.db_utils import safe_commit
    student = _get_my_student()
    if not student:
        return redirect(url_for("parent_portal.dashboard"))

    record = DisciplineRecord.query.get_or_404(discipline_id)
    if record.student_id != student.id:
        flash("无权对此记录申诉", "danger")
        return redirect(url_for("parent_portal.discipline"))

    # 检查已有申诉
    existing = DisciplineAppeal.query.filter_by(
        discipline_id=discipline_id, applicant_id=session.get("user_id")
    ).first()

    if request.method == "POST":
        if existing:
            flash("您已提交过申诉，请等待处理", "warning")
            return redirect(url_for("parent_portal.appeals"))

        reason = request.form.get("reason", "").strip()
        if not reason:
            flash("请填写申诉理由", "warning")
            return redirect(url_for("parent_portal.appeal", discipline_id=discipline_id))

        appeal_obj = DisciplineAppeal(
            discipline_id=discipline_id,
            student_id=student.id,
            class_id=record.class_id,
            grade_id=record.grade_id,
            applicant_id=session.get("user_id"),
            reason=reason,
        )
        db.session.add(appeal_obj)
        # 标记违纪记录为申诉中
        if record.status == "active":
            record.status = "appealed"
        # 发送通知（与申诉记录同一个事务）
        send_appeal_notifications(appeal_obj, student, record)

        safe_commit()
        flash("申诉已提交，请等待德育处复核", "success")
        return redirect(url_for("parent_portal.appeals"))

    return render_template(
        "parent_portal/appeal_form.html",
        student=student,
        record=record,
        existing=existing,
    )


@parent_portal_bp.route("/appeals")
@login_required
@require_role("parent")
def appeals():
    """家长查看我的申诉列表"""
    student = _get_my_student()
    if not student:
        return redirect(url_for("parent_portal.dashboard"))

    appeals = DisciplineAppeal.query.filter_by(
        student_id=student.id
    ).order_by(DisciplineAppeal.created_at.desc()).all()

    return render_template(
        "parent_portal/appeals.html",
        student=student,
        appeals=appeals,
    )


# ── 内部工具函数 ─────────────────────────────────────────────────
def _get_my_student():
    """获取当前家长绑定的学生"""
    student_id = session.get("bound_student_id")
    if not student_id:
        return None
    return Student.query.get(student_id)


# ── 成绩趋势 API ─────────────────────────────────────
@parent_portal_bp.route("/api/scores/trend")
@login_required
@require_role("parent")
def scores_trend():
    """返回当前学生跨考试的成绩趋势 JSON"""
    student = _get_my_student()
    if not student:
        return jsonify({"labels": [], "totals": [], "subjects": {}})
    exam_ids = db.session.query(Score.exam_id).filter(
        Score.student_id == student.id
    ).distinct().all()
    exam_ids = [e[0] for e in exam_ids]
    if not exam_ids:
        return jsonify({"labels": [], "totals": [], "subjects": {}})
    exams = Exam.query.filter(Exam.id.in_(exam_ids)).order_by(Exam.exam_date.asc()).all()
    exam_id_list = [ex.id for ex in exams]

    # 优化: 一次批量查询所有成绩，替代N次逐考试查询
    all_scores = Score.query.filter(
        Score.student_id == student.id,
        Score.exam_id.in_(exam_id_list)
    ).all()

    # 按考试分组
    scores_by_exam = {}
    need_subject_ids = set()
    for s in all_scores:
        scores_by_exam.setdefault(s.exam_id, []).append(s)
        if s.subject_id:
            need_subject_ids.add(s.subject_id)

    # 预加载所有科目
    if need_subject_ids:
        subject_map = {sub.id: sub for sub in Subject.query.filter(Subject.id.in_(need_subject_ids)).all()}
    else:
        subject_map = {}

    labels = []
    totals = []
    subjects = {}
    for ex in exams:
        scs = scores_by_exam.get(ex.id, [])
        if not scs:
            continue
        labels.append(ex.name[:8])
        total = round(sum(s.score for s in scs if s.score is not None), 1)
        totals.append(total)
        for s in scs:
            sub = subject_map.get(s.subject_id)
            if sub:
                subjects.setdefault(sub.name, []).append(
                    round(s.score, 1) if s.score is not None else None
                )
    return jsonify({
        "labels": labels,
        "totals": totals,
        "subjects": subjects,
    })


# ── AI风险预警（家长端）──────────────────────────────────────────
@parent_portal_bp.route("/risk")
@login_required
@require_role("parent")
def risk():
    """家长查看子女的AI风险预警"""
    student = _get_my_student()
    if not student:
        return redirect(url_for("parent_portal.dashboard"))

    # 最新一次扫描结果
    latest = RiskRecord.query.filter_by(
        student_id=student.id
    ).order_by(RiskRecord.scan_date.desc()).first()

    # 近30天历史
    from datetime import timedelta
    thirty_days_ago = date.today() - timedelta(days=30)
    history = RiskRecord.query.filter(
        RiskRecord.student_id == student.id,
        RiskRecord.scan_date >= thirty_days_ago,
    ).order_by(RiskRecord.scan_date.desc()).all()

    # 解析最新预警详情
    warnings = []
    if latest and latest.warning_details:
        try:
            warnings = json_mod.loads(latest.warning_details)
        except (json_mod.JSONDecodeError, TypeError):
            pass

    # 解析 XGBoost 特征归因
    feature_attr = None
    if latest and latest.feature_attribution:
        try:
            feature_attr = json_mod.loads(latest.feature_attribution)
        except (json_mod.JSONDecodeError, TypeError):
            pass

    return render_template(
        "parent_portal/risk.html",
        student=student,
        latest=latest,
        history=history,
        warnings=warnings,
        feature_attr=feature_attr,
    )
