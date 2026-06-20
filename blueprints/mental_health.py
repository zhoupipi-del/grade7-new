"""心理健康评估 — 评估记录管理/问题分析/干预跟踪"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from models import db, Student, Class, Grade, User, MentalHealthAssessment, MentalHealthQuestion, MentalHealthAnswer
from models import DisciplineRecord, Score, Exam, Subject, LeaveRequest, Attendance, InterventionRecord
from decorators import login_required, require_role
from datetime import date, datetime, timedelta
from utils import get_local_now
from utils.db_utils import safe_commit
import json

mental_health_bp = Blueprint("mental_health", __name__, url_prefix="/mental-health")

# ── 评估类型选项 ──
ASSESSMENT_TYPE_CHOICES = [
    ("questionnaire", "问卷测评"),
    ("interview", "访谈评估"),
    ("observation", "观察记录"),
    ("parent_feedback", "家长反馈"),
    ("teacher_feedback", "教师反馈"),
]

# ── 风险等级选项 ──
RISK_LEVEL_CHOICES = [
    ("low", "低风险"),
    ("medium", "中风险"),
    ("high", "高风险"),
]


@mental_health_bp.before_request
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher", "parent", "student")
def check_login():
    pass


@mental_health_bp.route("/")
def index():
    """心理健康评估列表"""
    role = session.get("role", "")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")

    # 确定查询范围
    q = MentalHealthAssessment.query
    if role == "grade_leader" and grade_id:
        q = q.filter_by(grade_id=grade_id)
    elif role in ("class_teacher", "teacher") and class_id:
        q = q.filter_by(class_id=class_id)
    elif role == "parent":
        # 家长只能看自己孩子的评估
        bound_student_id = session.get("bound_student_id")
        if bound_student_id:
            q = q.filter_by(student_id=bound_student_id)
        else:
            q = q.filter_by(id=-1)  # 无孩子，不显示
    elif role == "student":
        student_id = session.get("student_id")
        if student_id:
            q = q.filter_by(student_id=student_id)
        else:
            q = q.filter_by(id=-1)

    assessments = q.order_by(MentalHealthAssessment.created_at.desc()).all()

    # 统计
    stats = {
        "total": len(assessments),
        "high": sum(1 for a in assessments if a.risk_level == "high"),
        "medium": sum(1 for a in assessments if a.risk_level == "medium"),
        "low": sum(1 for a in assessments if a.risk_level == "low"),
        "need_intervention": sum(1 for a in assessments if a.need_intervention),
    }

    return render_template("mental_health/index.html",
                           assessments=assessments,
                           stats=stats,
                           assessment_types=ASSESSMENT_TYPE_CHOICES,
                           risk_levels=RISK_LEVEL_CHOICES)


@mental_health_bp.route("/create", methods=["GET", "POST"])
@require_role("ms_admin", "grade_leader", "class_teacher")
def create():
    """创建新的心理健康评估"""
    if request.method == "POST":
        student_id = request.form.get("student_id", type=int)
        assessment_type = request.form.get("assessment_type", "")
        scale_name = request.form.get("scale_name", "")
        conclusion = request.form.get("conclusion", "")
        recommendations = request.form.get("recommendations", "")
        need_intervention = request.form.get("need_intervention") == "on"
        intervention_plan = request.form.get("intervention_plan", "")

        if not student_id:
            flash("请选择学生", "danger")
            return redirect(url_for("mental_health.create"))

        student = Student.query.get_or_404(student_id)

        assessment = MentalHealthAssessment(
            student_id=student_id,
            class_id=student.class_id,
            grade_id=student.grade_id,
            assessment_type=assessment_type,
            scale_name=scale_name,
            conclusion=conclusion,
            recommendations=recommendations,
            need_intervention=need_intervention,
            intervention_plan=intervention_plan,
            assessed_by=session.get("user_id"),
        )

        db.session.add(assessment)
        safe_commit()

        flash("评估记录已创建", "success")
        return redirect(url_for("mental_health.detail", aid=assessment.id))

    # GET请求，显示创建表单
    role = session.get("role", "")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")

    # 获取可选学生列表
    students_q = Student.query.filter_by(is_active=True)
    if role == "grade_leader" and grade_id:
        students_q = students_q.filter_by(grade_id=grade_id)
    elif role in ("class_teacher", "teacher") and class_id:
        students_q = students_q.filter_by(class_id=class_id)

    students = students_q.order_by(Student.class_id, Student.name).all()

    # 获取可用量表列表
    scales = db.session.query(MentalHealthQuestion.scale_name.distinct()).all()
    scale_names = [s[0] for s in scales if s[0]]

    return render_template("mental_health/form.html",
                           students=students,
                           assessment_types=ASSESSMENT_TYPE_CHOICES,
                           scale_names=scale_names,
                           assessment=None)


@mental_health_bp.route("/<int:aid>")
def detail(aid):
    """查看评估详情"""
    assessment = MentalHealthAssessment.query.get_or_404(aid)

    # 权限检查
    role = session.get("role", "")
    if role == "grade_leader" and assessment.grade_id != session.get("grade_id"):
        flash("无权查看此评估", "danger")
        return redirect(url_for("mental_health.index"))
    elif role in ("class_teacher", "teacher") and assessment.class_id != session.get("class_id"):
        flash("无权查看此评估", "danger")
        return redirect(url_for("mental_health.index"))
    elif role == "parent":
        bound_student_id = session.get("bound_student_id")
        if assessment.student_id != bound_student_id:
            flash("无权查看此评估", "danger")
            return redirect(url_for("mental_health.index"))
    elif role == "student":
        student_id = session.get("student_id")
        if assessment.student_id != student_id:
            flash("无权查看此评估", "danger")
            return redirect(url_for("mental_health.index"))

    # 获取答案详情
    answers = MentalHealthAnswer.query.filter_by(assessment_id=aid).all()

    # ── 辅助判断数据：帮助评估人员全面了解学生情况 ──
    sid = assessment.student_id
    today = date.today()

    # 1. 近期违纪记录（本学期）
    discipline_records = DisciplineRecord.query.filter_by(
        student_id=sid
    ).order_by(DisciplineRecord.created_at.desc()).limit(10).all()

    # 2. 近期成绩（最近一次考试的各科分数）
    latest_exam = Exam.query.order_by(Exam.exam_date.desc()).first()
    recent_scores = []
    if latest_exam:
        recent_scores = Score.query.filter_by(
            student_id=sid, exam_id=latest_exam.id
        ).all()
        # 关联科目名
        subjects = {s.id: s.name for s in Subject.query.all()}

    # 3. 近期考勤概况（近30天）
    thirty_days_ago = today - timedelta(days=30)
    attendance_records = Attendance.query.filter(
        Attendance.student_id == sid,
        Attendance.record_date >= thirty_days_ago
    ).order_by(Attendance.record_date.desc()).limit(20).all()
    att_stats = {"present": 0, "absent": 0, "late": 0, "leave": 0}
    for a in attendance_records:
        key = a.status if a.status in att_stats else "present"
        att_stats[key] = att_stats.get(key, 0) + 1

    # 4. 请假记录（近30天已批准）
    leave_records = LeaveRequest.query.filter(
        LeaveRequest.student_id == sid,
        LeaveRequest.start_date >= thirty_days_ago,
        LeaveRequest.status == "approved"
    ).order_by(LeaveRequest.start_date.desc()).limit(10).all()

    return render_template("mental_health/detail.html",
                           assessment=assessment,
                           answers=answers,
                           discipline_records=discipline_records,
                           recent_scores=recent_scores,
                           latest_exam=latest_exam,
                           subjects=subjects if latest_exam else {},
                           attendance_records=attendance_records,
                           att_stats=att_stats,
                           leave_records=leave_records)


@mental_health_bp.route("/<int:aid>/edit", methods=["GET", "POST"])
@require_role("ms_admin", "grade_leader", "class_teacher")
def edit(aid):
    """编辑评估记录"""
    assessment = MentalHealthAssessment.query.get_or_404(aid)

    # 权限检查
    role = session.get("role", "")
    if role == "grade_leader" and assessment.grade_id != session.get("grade_id"):
        flash("无权编辑此评估", "danger")
        return redirect(url_for("mental_health.index"))
    elif role in ("class_teacher", "teacher") and assessment.class_id != session.get("class_id"):
        flash("无权编辑此评估", "danger")
        return redirect(url_for("mental_health.index"))

    if request.method == "POST":
        assessment.assessment_type = request.form.get("assessment_type", assessment.assessment_type)
        assessment.scale_name = request.form.get("scale_name", assessment.scale_name)
        assessment.conclusion = request.form.get("conclusion", "")
        assessment.recommendations = request.form.get("recommendations", "")
        assessment.need_intervention = request.form.get("need_intervention") == "on"
        assessment.intervention_plan = request.form.get("intervention_plan", "")
        assessment.updated_at = get_local_now()

        safe_commit()

        flash("评估记录已更新", "success")
        return redirect(url_for("mental_health.detail", aid=aid))

    # GET请求，显示编辑表单
    students_q = Student.query.filter_by(is_active=True)
    role = session.get("role", "")
    if role == "grade_leader" and session.get("grade_id"):
        students_q = students_q.filter_by(grade_id=session.get("grade_id"))
    elif role in ("class_teacher", "teacher") and session.get("class_id"):
        students_q = students_q.filter_by(class_id=session.get("class_id"))

    students = students_q.order_by(Student.class_id, Student.name).all()

    scales = db.session.query(MentalHealthQuestion.scale_name.distinct()).all()
    scale_names = [s[0] for s in scales if s[0]]

    return render_template("mental_health/form.html",
                           students=students,
                           assessment_types=ASSESSMENT_TYPE_CHOICES,
                           scale_names=scale_names,
                           assessment=assessment)


@mental_health_bp.route("/<int:aid>/delete", methods=["POST"])
@require_role("ms_admin", "grade_leader")
def delete(aid):
    """删除评估记录"""
    assessment = MentalHealthAssessment.query.get_or_404(aid)

    # 权限检查
    role = session.get("role", "")
    if role == "grade_leader" and assessment.grade_id != session.get("grade_id"):
        flash("无权删除此评估", "danger")
        return redirect(url_for("mental_health.index"))

    db.session.delete(assessment)
    safe_commit()

    flash("评估记录已删除", "info")
    return redirect(url_for("mental_health.index"))


@mental_health_bp.route("/questions")
@require_role("ms_admin")
def questions():
    """问题库管理"""
    scales = db.session.query(MentalHealthQuestion.scale_name.distinct()).all()
    scale_names = [s[0] for s in scales if s[0]]

    selected_scale = request.args.get("scale", scale_names[0] if scale_names else "")

    # 获取所有活跃问题（用于按量表分组展示）
    all_questions = MentalHealthQuestion.query.filter_by(is_active=True).order_by(
        MentalHealthQuestion.scale_name, MentalHealthQuestion.dimension, MentalHealthQuestion.question_no
    ).all()
    questions_by_scale = {}
    for q in all_questions:
        questions_by_scale.setdefault(q.scale_name, []).append(q)

    # 当前选中量表的问题（用于详细列表展示）
    questions_q = MentalHealthQuestion.query.filter_by(is_active=True)
    if selected_scale:
        questions_q = questions_q.filter_by(scale_name=selected_scale)
    questions = questions_q.order_by(MentalHealthQuestion.dimension, MentalHealthQuestion.question_no).all()

    return render_template("mental_health/questions.html",
                           questions=questions,
                           questions_by_scale=questions_by_scale,
                           scale_names=scale_names,
                           selected_scale=selected_scale,
                           dimensions=MentalHealthQuestion.__table__.columns.keys())


@mental_health_bp.route("/api/assessments")
@login_required
def api_assessments():
    """API：获取评估列表（JSON）"""
    role = session.get("role", "")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")

    q = MentalHealthAssessment.query
    if role == "grade_leader" and grade_id:
        q = q.filter_by(grade_id=grade_id)
    elif role in ("class_teacher", "teacher") and class_id:
        q = q.filter_by(class_id=class_id)

    assessments = q.order_by(MentalHealthAssessment.created_at.desc()).limit(100).all()

    result = []
    for a in assessments:
        result.append({
            "id": a.id,
            "student_name": a.student.name if a.student else "",
            "class_name": a.student.class_.name if a.student and a.student.class_ else "",
            "assessment_type": a.assessment_type,
            "scale_name": a.scale_name,
            "risk_level": a.risk_level,
            "total_score": a.total_score,
            "need_intervention": a.need_intervention,
            "assessment_date": a.assessment_date.isoformat() if a.assessment_date else "",
            "created_at": a.created_at.isoformat() if a.created_at else "",
        })

    return jsonify(result)


# ================================================================
# 绿洲干预追踪 — 心理健康干预全生命周期管理
# ================================================================

MH_INTERVENTION_TYPES = [
    ("心理谈话", "心理谈话"),
    ("家长联动", "家长联动"),
    ("心理辅导", "心理辅导"),
    ("危机干预", "危机干预"),
    ("转介专业机构", "转介专业机构"),
    ("其他", "其他"),
]

EFFECT_RATINGS = [
    ("显著好转", "显著好转"),
    ("略有好转", "略有好转"),
    ("无变化", "无变化"),
    ("恶化", "恶化"),
]


def _mh_scope_filter(query, model=InterventionRecord):
    """统一 scope 过滤：按角色限定干预记录可见范围"""
    role = session.get("role", "")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")
    if role == "ms_admin":
        return query
    elif role == "grade_leader" and grade_id:
        return query.join(Student).filter(Student.grade_id == grade_id)
    elif role in ("class_teacher", "teacher") and class_id:
        return query.join(Student).filter(Student.class_id == class_id)
    return query.filter(model.id < 0)  # 无权看任何


@mental_health_bp.route("/interventions")
@require_role("ms_admin", "grade_leader", "class_teacher")
def intervention_list():
    """干预追踪列表"""
    q = _mh_scope_filter(InterventionRecord.query)
    
    # 筛选
    status_filter = request.args.get("status", "")
    if status_filter:
        q = q.filter(InterventionRecord.status == status_filter)
    
    risk_filter = request.args.get("risk", "")
    if risk_filter:
        q = q.filter(InterventionRecord.mh_risk_before == risk_filter)
    
    records = q.order_by(InterventionRecord.intervention_date.desc()).limit(200).all()
    
    # 统计
    all_records = _mh_scope_filter(InterventionRecord.query).all()
    stats = {
        "total": len(all_records),
        "tracking": sum(1 for r in all_records if r.status == "tracking"),
        "completed": sum(1 for r in all_records if r.status == "completed"),
        "effective": sum(1 for r in all_records if r.is_effective),
        "improved": sum(1 for r in all_records if r.mh_risk_improved is True),
    }
    
    return render_template("mental_health/interventions.html",
                           records=records,
                           stats=stats,
                           intervention_types=MH_INTERVENTION_TYPES,
                           effect_ratings=EFFECT_RATINGS,
                           risk_levels=RISK_LEVEL_CHOICES,
                           status_filter=status_filter,
                           risk_filter=risk_filter)


@mental_health_bp.route("/interventions/create", methods=["POST"])
@require_role("ms_admin", "grade_leader", "class_teacher")
def intervention_create():
    """创建心理健康干预记录"""
    data = request.get_json(force=True, silent=True) or request.form.to_dict()
    
    # 解析 student_id（兼容 int 和 str 两种格式）
    raw_sid = data.get("student_id")
    try:
        student_id = int(raw_sid) if raw_sid else 0
    except (ValueError, TypeError):
        student_id = 0
    
    if not student_id:
        return jsonify({"status": "error", "message": "缺少 student_id"}), 400
    
    student = Student.query.get_or_404(student_id)
    
    # 权限检查
    role = session.get("role", "")
    if role == "grade_leader" and student.grade_id != session.get("grade_id"):
        return jsonify({"status": "error", "message": "无权操作此学生"}), 403
    elif role in ("class_teacher", "teacher") and student.class_id != session.get("class_id"):
        return jsonify({"status": "error", "message": "无权操作此学生"}), 403
    
    # 解析 assessment_id
    raw_aid = data.get("assessment_id")
    try:
        assessment_id = int(raw_aid) if raw_aid else None
    except (ValueError, TypeError):
        assessment_id = None
    
    mh_risk_before = None
    if assessment_id:
        assessment = MentalHealthAssessment.query.get(assessment_id)
        if assessment:
            mh_risk_before = assessment.risk_level
    
    # 如果没有指定 assessment_id，尝试取最新的
    if not assessment_id or not mh_risk_before:
        latest = MentalHealthAssessment.query.filter_by(
            student_id=student_id
        ).order_by(MentalHealthAssessment.created_at.desc()).first()
        if latest:
            assessment_id = latest.id
            mh_risk_before = latest.risk_level
    
    # 解析日期（JSON传字符串，需转 date 对象）
    raw_date = data.get("intervention_date")
    if raw_date:
        try:
            if isinstance(raw_date, str):
                intervention_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
            else:
                intervention_date = raw_date
        except (ValueError, TypeError):
            intervention_date = get_local_now().date()
    else:
        intervention_date = get_local_now().date()
    
    raw_fup = data.get("follow_up_date")
    follow_up_date = None
    if raw_fup:
        try:
            if isinstance(raw_fup, str):
                follow_up_date = datetime.strptime(raw_fup, "%Y-%m-%d").date()
            else:
                follow_up_date = raw_fup
        except (ValueError, TypeError):
            follow_up_date = None
    
    rec = InterventionRecord(
        student_id=student_id,
        teacher_id=session.get("user_id", 0),
        assessment_id=assessment_id,
        mh_risk_before=mh_risk_before,
        intervention_type=data.get("intervention_type", "心理谈话"),
        notes=data.get("notes", ""),
        parent_feedback=data.get("parent_feedback", ""),
        intervention_date=intervention_date,
        follow_up_date=follow_up_date,
    )
    db.session.add(rec)
    safe_commit()
    
    return jsonify({
        "status": "ok",
        "intervention_id": rec.id,
        "mh_risk_before": mh_risk_before,
        "message": "干预记录已创建",
    })


@mental_health_bp.route("/interventions/<int:int_id>/followup", methods=["POST"])
@require_role("ms_admin", "grade_leader", "class_teacher")
def intervention_followup(int_id):
    """更新随访结果"""
    rec = InterventionRecord.query.get_or_404(int_id)
    
    # 权限检查
    role = session.get("role", "")
    if role == "grade_leader" and rec.student.grade_id != session.get("grade_id"):
        return jsonify({"status": "error", "message": "无权操作"}), 403
    elif role in ("class_teacher", "teacher") and rec.student.class_id != session.get("class_id"):
        return jsonify({"status": "error", "message": "无权操作"}), 403
    
    data = request.get_json(force=True, silent=True) or request.form.to_dict()
    
    rec.effect_rating = data.get("effect_rating", "")
    rec.follow_up_notes = data.get("follow_up_notes", "")
    rec.parent_feedback = data.get("parent_feedback", "") or rec.parent_feedback
    rec.follow_up_done = True
    rec.follow_up_date = get_local_now().date()
    rec.mh_risk_after = data.get("mh_risk_after", "")
    rec.status = "completed"
    rec.updated_at = get_local_now()
    safe_commit()
    
    return jsonify({
        "status": "ok",
        "mh_risk_improved": rec.mh_risk_improved,
        "message": "随访记录已更新",
    })


@mental_health_bp.route("/interventions/<int:student_id>/timeline")
@require_role("ms_admin", "grade_leader", "class_teacher")
def intervention_timeline(student_id):
    """学生干预时间线"""
    student = Student.query.get_or_404(student_id)
    
    # 权限检查
    role = session.get("role", "")
    if role == "grade_leader" and student.grade_id != session.get("grade_id"):
        flash("无权查看", "danger")
        return redirect(url_for("mental_health.intervention_list"))
    elif role in ("class_teacher", "teacher") and student.class_id != session.get("class_id"):
        flash("无权查看", "danger")
        return redirect(url_for("mental_health.intervention_list"))
    
    # 获取该学生所有干预记录
    records = InterventionRecord.query.filter_by(
        student_id=student_id
    ).order_by(InterventionRecord.intervention_date.asc()).all()
    
    # 获取最新评估
    latest_assessment = MentalHealthAssessment.query.filter_by(
        student_id=student_id
    ).order_by(MentalHealthAssessment.created_at.desc()).first()
    
    # 风险变化趋势数据（供 ECharts 折线图）
    risk_trend = []
    for r in records:
        if r.mh_risk_before:
            risk_trend.append({
                "date": r.intervention_date.isoformat() if r.intervention_date else "",
                "risk": r.mh_risk_before,
                "type": "干预前",
                "label": r.intervention_type,
            })
        if r.mh_risk_after and r.follow_up_done:
            risk_trend.append({
                "date": r.follow_up_date.isoformat() if r.follow_up_date else "",
                "risk": r.mh_risk_after,
                "type": "随访后",
                "label": r.effect_rating or "",
            })
    
    risk_order = {"low": 1, "medium": 2, "high": 3}
    risk_trend.sort(key=lambda x: (x["date"], risk_order.get(x["risk"], 0)))
    
    return render_template("mental_health/intervention_timeline.html",
                           student=student,
                           records=records,
                           latest_assessment=latest_assessment,
                           risk_trend=json.dumps(risk_trend),
                           intervention_types=MH_INTERVENTION_TYPES,
                           effect_ratings=EFFECT_RATINGS,
                           risk_levels=RISK_LEVEL_CHOICES)


@mental_health_bp.route("/interventions/api/list")
@require_role("ms_admin", "grade_leader", "class_teacher")
def intervention_api_list():
    """API: 干预记录列表（JSON）"""
    q = _mh_scope_filter(InterventionRecord.query)
    records = q.order_by(InterventionRecord.intervention_date.desc()).limit(100).all()
    return jsonify([r.to_dict() for r in records])


@mental_health_bp.route("/api/students")
@require_role("ms_admin", "grade_leader", "class_teacher")
def api_search_students():
    """API: 搜索学生（按权限scope过滤），供干预创建Modal使用"""
    q = Student.query.filter_by(is_active=True)
    role = session.get("role", "")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")
    if role == "grade_leader" and grade_id:
        q = q.filter_by(grade_id=grade_id)
    elif role in ("class_teacher", "teacher") and class_id:
        q = q.filter_by(class_id=class_id)
    
    keyword = request.args.get("q", "").strip()
    if keyword:
        q = q.filter(Student.name.contains(keyword))
    
    students = q.order_by(Student.class_id, Student.name).limit(50).all()
    result = []
    for s in students:
        # 取最新MH评估
        latest = MentalHealthAssessment.query.filter_by(
            student_id=s.id
        ).order_by(MentalHealthAssessment.created_at.desc()).first()
        result.append({
            "id": s.id,
            "name": s.name,
            "class_name": s.class_.name if s.class_ else "",
            "risk_level": latest.risk_level if latest else None,
            "total_score": latest.total_score if latest else None,
            "assessment_id": latest.id if latest else None,
        })
    return jsonify(result)


