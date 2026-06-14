"""心理健康评估 — 评估记录管理/问题分析/干预跟踪"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from models import db, Student, Class, Grade, User, MentalHealthAssessment, MentalHealthQuestion, MentalHealthAnswer
from models import DisciplineRecord, Score, Exam, Subject, LeaveRequest, Attendance
from decorators import login_required, require_role
from datetime import date, datetime, timedelta
from utils.db_utils import safe_commit

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
        assessment.updated_at = datetime.utcnow()

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

    questions_q = MentalHealthQuestion.query.filter_by(is_active=True)
    if selected_scale:
        questions_q = questions_q.filter_by(scale_name=selected_scale)

    questions = questions_q.order_by(MentalHealthQuestion.dimension, MentalHealthQuestion.question_no).all()

    return render_template("mental_health/questions.html",
                           questions=questions,
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
