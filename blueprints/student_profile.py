"""学生画像统一门户 — 聚合多维数据，一张页面看清一个学生"""
import json as json_mod
from datetime import date, datetime, timedelta
from collections import defaultdict

from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for
from sqlalchemy import func

from models import (
    db, Student, Class, Grade, User,
    DisciplineRecord, LeaveRequest, Attendance,
    Score, Exam, Subject, WingsScore,
    RiskRecord, HomeVisit, FlagEvaluation,
    MentalHealthAssessment, PsychSurvey,
    EndTermComment, TeacherNote,
)
from utils import get_local_now
from decorators import login_required, require_role

student_profile_bp = Blueprint("student_profile", __name__)


def _check_access(sid):
    """权限检查：德育处全部 / 年级组长本年级 / 班主任本班"""
    student = Student.query.get_or_404(sid)
    role = session.get("role", "")
    if role == "ms_admin":
        return student
    if role == "grade_leader":
        grade_id = session.get("grade_id")
        if student.grade_id != grade_id:
            flash("无权查看该学生", "danger")
            return None
        return student
    if role in ("class_teacher", "teacher"):
        class_id = session.get("class_id")
        if student.class_id != class_id:
            flash("无权查看该学生", "danger")
            return None
        return student
    flash("无权查看", "danger")
    return None


# ── 主页：学生画像 ──
@student_profile_bp.route("/<int:sid>")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def detail(sid):
    student = _check_access(sid)
    if student is None:
        return redirect(url_for("ms.index") if session.get("role") == "ms_admin"
                        else url_for("grade.index") if session.get("role") == "grade_leader"
                        else url_for("class.index"))

    today = date.today()
    thirty_days_ago = today - timedelta(days=30)
    role = session.get("role", "")
    user_id = session.get("user_id")

    # ── 1. 基本信息 ──
    class_info = Class.query.get(student.class_id)
    grade_info = Grade.query.get(student.grade_id)

    # ── 2. 违纪统计 ──
    discipline_all = DisciplineRecord.query.filter_by(
        student_id=sid
    ).order_by(DisciplineRecord.created_at.desc()).all()
    discipline_total = len(discipline_all)
    discipline_active = sum(1 for d in discipline_all if d.status == "active")
    discipline_points = sum(d.points for d in discipline_all)

    # ── 3. 考勤统计 ──
    attendance_30d = Attendance.query.filter(
        Attendance.student_id == sid,
        Attendance.record_date >= thirty_days_ago
    ).all()
    att_present = sum(1 for a in attendance_30d if a.status == "present")
    att_late = sum(1 for a in attendance_30d if a.status == "late")
    att_absent = sum(1 for a in attendance_30d if a.status == "absent")
    att_leave = sum(1 for a in attendance_30d if a.status == "leave")
    att_total = len(attendance_30d)
    att_rate = round(att_present / att_total * 100, 1) if att_total > 0 else 0

    # ── 4. 请假统计 ──
    leaves = LeaveRequest.query.filter_by(
        student_id=sid
    ).order_by(LeaveRequest.created_at.desc()).all()
    leave_total = len(leaves)
    leave_approved = sum(1 for l in leaves if l.status in ("class_approved", "grade_approved"))
    leave_days = sum(
        (l.end_date - l.start_date).days + 1
        for l in leaves if l.status in ("class_approved", "grade_approved")
    )

    # ── 5. 最近考试成绩 ──
    latest_exam = Exam.query.order_by(Exam.exam_date.desc()).first()
    latest_scores = []
    if latest_exam:
        latest_scores = Score.query.filter_by(
            student_id=sid, exam_id=latest_exam.id
        ).all()

    # 成绩趋势（最近8次考试）- 优化: 一次批量查询取代逐考试查询
    # 同时计算每次考试的班级排名
    recent_exams = Exam.query.order_by(Exam.exam_date.desc()).limit(8).all()
    exam_ids = [e.id for e in recent_exams]
    all_trend_scores = Score.query.filter(
        Score.student_id == sid,
        Score.exam_id.in_(exam_ids)
    ).all()
    scores_by_exam = {}
    for s in all_trend_scores:
        scores_by_exam.setdefault(s.exam_id, []).append(s)

    # 批量查询每次考试的班级排名
    score_trend = []
    for exam in reversed(recent_exams):
        scores = scores_by_exam.get(exam.id, [])
        if scores:
            avg_score = round(sum(s.score for s in scores) / len(scores), 1)
            # 计算班级排名：获取该班级该次考试所有学生的总分，找排名
            from models import Student as S
            class_stu_ids = [s.id for s in Student.query.filter_by(
                class_id=student.class_id, is_active=True
            ).all()]
            class_scores = db.session.query(
                Score.student_id,
                func.avg(Score.score).label('avg_score')
            ).filter(
                Score.exam_id == exam.id,
                Score.student_id.in_(class_stu_ids)
            ).group_by(Score.student_id).order_by(func.avg(Score.score).desc()).all()
            rank = None
            for idx, (stu_id, _) in enumerate(class_scores, 1):
                if stu_id == sid:
                    rank = idx
                    break
            score_trend.append({
                "exam_name": exam.name,
                "exam_date": exam.exam_date.strftime("%m/%d") if exam.exam_date else "",
                "avg_score": avg_score,
                "rank": rank,
                "subject_count": len(scores),
            })

    # ── 6. 五翼评价 ──
    wings = WingsScore.query.filter_by(student_id=sid).order_by(
        WingsScore.created_at.desc()
    ).all()
    wings_latest = {}
    wings_history = []
    for w in wings:
        wings_history.append({
            "dimension": w.dimension,
            "score": w.score,
            "scorer": w.scorer_name or "",
            "date": w.created_at.strftime("%m/%d") if w.created_at else "",
        })
        if w.dimension not in wings_latest:
            wings_latest[w.dimension] = w.score

    # ── 7. AI 预警 ──
    risk_latest = RiskRecord.query.filter_by(
        student_id=sid
    ).order_by(RiskRecord.scan_date.desc()).first()
    risk_history = RiskRecord.query.filter_by(
        student_id=sid
    ).order_by(RiskRecord.scan_date.desc()).limit(10).all()

    # 序列化为 JSON 安全的列表（包含 warning_details 供模板展示预警类型）
    risk_history_json = []
    for r in risk_history:
        ws = []
        if r.warning_details:
            try:
                ws = json_mod.loads(r.warning_details)
            except Exception:
                pass
        risk_history_json.append({
            "id": r.id,
            "scan_date": r.scan_date.isoformat() if r.scan_date else "",
            "risk_level": r.risk_level,
            "warning_count": r.warning_count or 0,
            "is_processed": r.is_processed,
            "disposal_action": r.disposal_action or "",
            "warning_details": ws,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        })

    risk_level = risk_latest.risk_level if risk_latest else "green"
    risk_warnings = []
    if risk_latest and risk_latest.warning_details:
        try:
            risk_warnings = json_mod.loads(risk_latest.warning_details)
        except Exception:
            pass

    # ── 8. 心理评估 ──
    psych_latest = PsychSurvey.query.filter_by(
        student_id=sid, survey_type="MSSMHS-55", is_valid=True
    ).order_by(PsychSurvey.completed_at.desc()).first()
    mh_assessments = MentalHealthAssessment.query.filter_by(
        student_id=sid
    ).order_by(MentalHealthAssessment.created_at.desc()).limit(5).all()

    # ── 8.5 流动红旗历史排名 ──
    flag_history = FlagEvaluation.query.filter_by(
        class_id=student.class_id
    ).order_by(FlagEvaluation.created_at.desc()).limit(10).all()
    # 计算该生所在班级每次的排名
    flag_rank_history = []
    for ev in reversed(flag_history):
        # 获取同年级同周期所有班级排名
        same_period = FlagEvaluation.query.filter_by(
            period_type=ev.period_type,
            period_label=ev.period_label,
            grade_id=ev.grade_id,
            status="published"
        ).order_by(FlagEvaluation.final_score.desc()).all()
        rank = None
        for idx, fev in enumerate(same_period, 1):
            if fev.class_id == student.class_id:
                rank = idx
                break
        flag_rank_history.append({
            "period_label": ev.period_label,
            "final_score": ev.final_score,
            "rank": rank,
            "total_classes": len(same_period),
            "is_published": ev.status == "published"
        })

    # ── 9. 家访记录 ──
    home_visits = HomeVisit.query.filter_by(
        student_id=sid
    ).order_by(HomeVisit.visit_date.desc()).all()

    # ── 10. 期末评语 ──
    comments = EndTermComment.query.filter_by(
        student_id=sid, status="published"
    ).order_by(EndTermComment.created_at.desc()).limit(3).all()

    # ── 11. 班主任手记 ──
    notes = TeacherNote.query.filter_by(
        student_id=sid
    ).order_by(TeacherNote.created_at.desc()).all()

    # ── 12. 构建事件时间轴 ──
    timeline = _build_timeline(sid, discipline_all, leaves, risk_history, home_visits, mh_assessments)

    return render_template(
        "student_profile/detail.html",
        student=student,
        class_info=class_info,
        grade_info=grade_info,
        discipline_all=discipline_all,
        discipline_total=discipline_total,
        discipline_active=discipline_active,
        discipline_points=discipline_points,
        att_present=att_present, att_late=att_late,
        att_absent=att_absent, att_leave=att_leave,
        att_total=att_total, att_rate=att_rate,
        leaves=leaves, leave_total=leave_total,
        leave_approved=leave_approved, leave_days=leave_days,
        latest_exam=latest_exam, latest_scores=latest_scores,
        score_trend=score_trend,
        wings_latest=wings_latest, wings_history=wings_history,
        risk_latest=risk_latest, risk_level=risk_level,
        risk_warnings=risk_warnings, risk_history=risk_history_json,
        psych_latest=psych_latest, mh_assessments=mh_assessments,
        flag_rank_history=flag_rank_history,
        home_visits=home_visits, comments=comments,
        notes=notes, timeline=timeline,
        today=today, role=role,
    )


# ── 班主任手记 CRUD ──
@student_profile_bp.route("/<int:sid>/notes/add", methods=["POST"])
@login_required
@require_role("class_teacher")
def add_note(sid):
    student = _check_access(sid)
    if student is None:
        return jsonify({"code": 1, "msg": "无权操作"}), 403

    content = request.form.get("content", "").strip()
    category = request.form.get("category", "observation")
    if not content:
        flash("请输入备注内容", "danger")
        return redirect(url_for("student_profile.detail", sid=sid))

    note = TeacherNote(
        student_id=sid,
        teacher_id=session.get("user_id"),
        content=content,
        category=category,
    )
    db.session.add(note)
    db.session.commit()
    flash("手记已保存", "success")
    return redirect(url_for("student_profile.detail", sid=sid))


@student_profile_bp.route("/<int:sid>/notes/<int:nid>/edit", methods=["POST"])
@login_required
@require_role("class_teacher")
def edit_note(sid, nid):
    student = _check_access(sid)
    if student is None:
        return jsonify({"code": 1, "msg": "无权操作"}), 403

    note = TeacherNote.query.get_or_404(nid)
    if note.student_id != sid or note.teacher_id != session.get("user_id"):
        flash("无权编辑此手记", "danger")
        return redirect(url_for("student_profile.detail", sid=sid))

    content = request.form.get("content", "").strip()
    if content:
        note.content = content
        note.category = request.form.get("category", note.category)
        db.session.commit()
        flash("手记已更新", "success")
    return redirect(url_for("student_profile.detail", sid=sid))


@student_profile_bp.route("/<int:sid>/notes/<int:nid>/delete", methods=["POST"])
@login_required
@require_role("class_teacher")
def delete_note(sid, nid):
    student = _check_access(sid)
    if student is None:
        return jsonify({"code": 1, "msg": "无权操作"}), 403

    note = TeacherNote.query.get_or_404(nid)
    if note.student_id != sid or note.teacher_id != session.get("user_id"):
        flash("无权删除此手记", "danger")
        return redirect(url_for("student_profile.detail", sid=sid))

    db.session.delete(note)
    db.session.commit()
    flash("手记已删除", "success")
    return redirect(url_for("student_profile.detail", sid=sid))


# ── AI预警处置 ──
@student_profile_bp.route("/<int:sid>/risk/<int:rid>/process", methods=["POST"])
@login_required
@require_role("class_teacher", "grade_leader")
def process_risk(sid, rid):
    student = _check_access(sid)
    if student is None:
        flash("无权操作", "danger")
        return redirect(url_for("student_profile.detail", sid=sid))

    risk = RiskRecord.query.get_or_404(rid)
    if risk.student_id != sid:
        flash("预警记录不匹配", "danger")
        return redirect(url_for("student_profile.detail", sid=sid))

    action = request.form.get("action", "")
    if action not in ("talk", "home_visit", "notify_parent", "monitor", "resolved"):
        flash("无效的处置类型", "danger")
        return redirect(url_for("student_profile.detail", sid=sid))

    risk.is_processed = True
    risk.processed_by = session.get("user_id")
    risk.processed_at = get_local_now()
    risk.process_note = request.form.get("note", "")
    risk.disposal_action = action
    db.session.commit()

    # 同时添加一条手记
    action_labels = {
        "talk": "谈话",
        "home_visit": "家访",
        "notify_parent": "通知家长",
        "monitor": "持续观察",
        "resolved": "已解决",
    }
    note = TeacherNote(
        student_id=sid,
        teacher_id=session.get("user_id"),
        content=f"[AI预警处置] {action_labels.get(action, action)}: {request.form.get('note', '')}",
        category="intervention",
    )
    db.session.add(note)
    db.session.commit()

    flash("预警已标记处理", "success")
    return redirect(url_for("student_profile.detail", sid=sid))


# ── 成绩趋势 API（Chart.js 用） ──
@student_profile_bp.route("/<int:sid>/api/trend")
@login_required
def api_trend(sid):
    student = _check_access(sid)
    if student is None:
        return jsonify({"code": 1, "msg": "无权查看"}), 403

    exams = Exam.query.order_by(Exam.exam_date.asc()).all()
    subjects = Subject.query.order_by(Subject.sort_order).all()

    # 总分趋势
    total_labels = []
    total_data = []
    for exam in exams:
        scores = Score.query.filter_by(student_id=sid, exam_id=exam.id).all()
        if scores:
            total_labels.append(exam.name[:6])
            total_data.append(round(sum(s.score for s in scores) / len(scores), 1))

    # 各科趋势
    subject_trends = {}
    for subj in subjects:
        subj_data = []
        for exam in exams:
            s = Score.query.filter_by(student_id=sid, exam_id=exam.id, subject_id=subj.id).first()
            subj_data.append(s.score if s else None)
        if any(x is not None for x in subj_data):
            subject_trends[subj.name] = {"labels": [e.name[:6] for e in exams], "data": subj_data}

    # 考勤月度统计
    six_months_ago = date.today() - timedelta(days=180)
    att_records = Attendance.query.filter(
        Attendance.student_id == sid,
        Attendance.record_date >= six_months_ago
    ).all()
    monthly_att = defaultdict(lambda: {"present": 0, "late": 0, "absent": 0, "leave": 0, "total": 0})
    for a in att_records:
        month_key = a.record_date.strftime("%m月")
        monthly_att[month_key][a.status] = monthly_att[month_key].get(a.status, 0) + 1
        monthly_att[month_key]["total"] += 1

    att_labels = sorted(monthly_att.keys(), key=lambda x: int(x.replace("月", "")))
    att_present_data = []
    att_late_data = []
    att_absent_data = []
    for m in att_labels:
        d = monthly_att[m]
        total = d["total"] or 1
        att_present_data.append(round(d["present"] / total * 100, 1))
        att_late_data.append(round(d["late"] / total * 100, 1))
        att_absent_data.append(round(d["absent"] / total * 100, 1))

    return jsonify({
        "code": 0,
        "score_trend": {"labels": total_labels, "data": total_data},
        "subject_trends": subject_trends,
        "attendance": {
            "labels": att_labels,
            "present": att_present_data,
            "late": att_late_data,
            "absent": att_absent_data,
        },
    })


# ── 事件时间轴构建 ──
def _build_timeline(sid, disciplines, leaves, risks, visits, assessments):
    """将违纪/请假/AI预警/家访/心理评估混排为统一时间轴"""
    items = []

    for d in disciplines[:20]:
        items.append({
            "date": d.created_at,
            "type": "discipline",
            "icon": "warning",
            "color": "danger",
            "title": f"违纪: {d.type}",
            "detail": d.description[:80],
            "badge": f"-{d.points}分" if d.points else "",
        })

    for l in leaves[:20]:
        items.append({
            "date": l.created_at,
            "type": "leave",
            "icon": "calendar",
            "color": "info",
            "title": f"请假: {l.reason[:30]}",
            "detail": f"{l.start_date} ~ {l.end_date} ({l.status})",
            "badge": l.status,
        })

    for r in risks[:15]:
        items.append({
            "date": r.created_at,
            "type": "risk",
            "icon": "alert",
            "color": "warning" if r.risk_level == "yellow" else "danger",
            "title": f"AI预警: {r.risk_level}",
            "detail": f"触发{r.warning_count}项预警" + (f" | 已处理" if r.is_processed else " | 待处理"),
            "badge": r.risk_level,
        })

    for v in visits[:10]:
        items.append({
            "date": v.created_at or get_local_now(),
            "type": "home_visit",
            "icon": "home",
            "color": "success",
            "title": f"家访: {v.visit_type}",
            "detail": (v.content_summary or "")[:80],
            "badge": v.visit_type,
        })

    for a in assessments[:10]:
        items.append({
            "date": a.created_at,
            "type": "mental_health",
            "icon": "health",
            "color": "secondary",
            "title": f"心理评估: {a.risk_level}",
            "detail": (a.conclusion or "")[:80] if a.conclusion else "",
            "badge": a.risk_level,
        })

    items.sort(key=lambda x: x["date"], reverse=True)
    return items[:50]
