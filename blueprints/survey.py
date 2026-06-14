"""问卷与心理 — 心理筛查/家长问卷"""
from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for
from models import db, Student, PsychSurvey, MentalHealthAssessment
from decorators import login_required, require_role
import json
from datetime import date
from utils.db_utils import safe_commit
from blueprints.common import notify_parent, notify_class_teacher

survey_bp = Blueprint("survey", __name__)


# ── 辅助：自动创建心理健康评估 ──
def _auto_create_mental_health(stu, total_score, survey_id=None):
    """问卷筛查高风险时，自动创建心理健康评估记录，并通知班主任+家长"""
    # 状态机守卫：如果提供了 survey_id，检查问卷是否已标记为 COMPLETED
    if survey_id:
        survey = PsychSurvey.query.get(survey_id)
        if survey and getattr(survey, 'verify_status', None) != 'COMPLETED':
            return None
    # 检查是否已存在同一问卷来源的评估
    existing = MentalHealthAssessment.query.filter_by(
        student_id=stu.id,
        scale_name="MSSMHS-55",
        assessment_type="questionnaire"
    ).first()
    if existing:
        old_risk = existing.risk_level
        # 更新已有记录
        if total_score >= 160:
            existing.risk_level = "high"
        elif total_score >= 120:
            existing.risk_level = "medium"
        else:
            existing.risk_level = "low"
        existing.total_score = total_score
        existing.conclusion = (
            f"MSSMHS-55心理健康筛查总分{total_score}，"
            f"评定为{'⚠️高风险' if existing.risk_level == 'high' else '⚡中风险' if existing.risk_level == 'medium' else '✅低风险'}"
        )
        existing.need_intervention = (existing.risk_level in ("high", "medium"))
        safe_commit()
        # 高风险升级时通知
        if existing.risk_level == "high" and old_risk != "high":
            _send_mental_health_notification(stu, existing)
        return existing

    risk_level = "high" if total_score >= 160 else "medium" if total_score >= 120 else "low"

    # 幂等性守卫：同一问卷对同一学生的评估只创建一次（upsert 之上再加一层保障）
    from blueprints.linkage_utils import try_linkage, sk_survey, tk_assessment
    if survey_id and not try_linkage(
        "survey_to_assessment",
        sk_survey(survey_id),
        tk_assessment(stu.id, "MSSMHS-55"),
    ):
        return existing  # 已处理过，返回 None 或已有记录

    assessment = MentalHealthAssessment(
        student_id=stu.id,
        class_id=stu.class_id,
        grade_id=stu.grade_id,
        assessment_type="questionnaire",
        scale_name="MSSMHS-55",
        total_score=int(total_score),
        risk_level=risk_level,
        assessment_date=date.today(),
        conclusion=(
            f"MSSMHS-55心理健康筛查总分{total_score}，"
            f"评定为{'⚠️高风险（≥160分）' if risk_level == 'high' else '⚡中风险（120-159分）' if risk_level == 'medium' else '✅低风险（<120分）'}"
        ),
        recommendations="建议关注学生心理状态，结合日常表现综合研判，必要时安排专业心理咨询",
        need_intervention=(risk_level in ("high", "medium")),
        intervention_plan="由班主任持续关注，心理老师定期回访" if risk_level == "high" else None,
        assessed_by=1,  # 系统自动创建，assessed_by=1 为系统账号
        status="draft",
    )
    db.session.add(assessment)
    safe_commit()
    # 高风险时通知班主任+家长
    if risk_level == "high":
        _send_mental_health_notification(stu, assessment)
    return assessment


def _send_mental_health_notification(stu, assessment):
    """心理健康高风险通知：班主任 + 家长（优先使用消息模板）"""
    from_user_id = 1  # 系统账号
    class_name = stu.class_.name if stu.class_ else "未知班级"

    # 尝试使用消息模板（新增模板：心理筛查通知）
    template_vars = {
        "student_name": stu.name,
        "class_name": class_name,
        "date": str(assessment.assessment_date) if assessment.assessment_date else "",
        "score": str(assessment.total_score or "未评估"),
        "reason": f"MSSMHS-55心理筛查得分{assessment.total_score}分，评定为{assessment.risk_level}风险",
    }

    # 默认通知文本（模板不存在时使用）
    fallback_title = f"⚠️ 心理筛查高风险 — {stu.name}"
    fallback_content = (
        f"学生 {stu.name}（{class_name}）"
        f"在MSSMHS-55心理筛查中得分 {assessment.total_score} 分，评定为高风险。\n"
        f"结论：{assessment.conclusion}\n"
        f"建议：{assessment.recommendations}"
    )

    # 通知班主任（尝试用模板）
    notify_class_teacher(stu, fallback_title, fallback_content,
                         from_user_id=from_user_id,
                         template_name="表扬信",
                         template_vars=template_vars)
    # 通知家长
    notify_parent(stu, fallback_title, fallback_content,
                  from_user_id=from_user_id,
                  template_name="表扬信",
                  template_vars=template_vars)


# ── 心理筛查列表 ──
@survey_bp.route("/psych")
@login_required
def psych_list():
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")
    q = PsychSurvey.query.filter_by(survey_type="MSSMHS-55", is_valid=True, verify_status="COMPLETED")
    if session.get("role") == "class_teacher" and class_id:
        q = q.filter_by(class_id=class_id)
    elif session.get("role") == "grade_leader" and grade_id:
        q = q.filter_by(grade_id=grade_id)
    surveys = q.order_by(PsychSurvey.total_score.desc()).limit(200).all()
    return render_template("survey/psych_list.html", surveys=surveys)


@survey_bp.route("/psych/form")
@login_required
def psych_form():
    return render_template("survey/psych_form.html")


@survey_bp.route("/psych/submit", methods=["POST"])
@login_required
def psych_submit():
    data = request.get_json()
    answers = data.get("answers", [])
    sid = session.get("student_id") or session.get("bound_student_id")
    student = Student.query.get(sid) if sid else None
    if not student:
        return jsonify({"error": "未绑定学生"}), 400
    total_score = sum(item["score"] for item in answers)
    survey = PsychSurvey(
        student_id=student.id,
        class_id=student.class_id,
        grade_id=student.grade_id,
        answers_json=json.dumps(answers, ensure_ascii=False),
        total_score=total_score,
        verify_status="COMPLETED",
    )
    db.session.add(survey)
    safe_commit()

    # 自动触发：高风险（≥160）创建心理健康评估
    if total_score >= 120:
        try:
            _auto_create_mental_health(student, total_score, survey.id)
        except Exception as e:
            current_app = __import__("flask").current_app
            if current_app:
                current_app.logger.warning(f"自动创建心理健康评估失败(student={student.id}): {e}")

    return jsonify({"ok": True, "id": survey.id})


# ── 心理筛查统计 ──
@survey_bp.route("/psych/stats")
@login_required
def psych_stats():
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")
    q = PsychSurvey.query.filter_by(survey_type="MSSMHS-55", is_valid=True, verify_status="COMPLETED")
    if session.get("role") == "class_teacher" and class_id:
        q = q.filter_by(class_id=class_id)
    elif session.get("role") == "grade_leader" and grade_id:
        q = q.filter_by(grade_id=grade_id)
    surveys = q.order_by(PsychSurvey.total_score.desc()).all()
    high_risk = sum(1 for s in surveys if s.total_score and s.total_score >= 160)
    medium_risk = sum(1 for s in surveys if s.total_score and 120 <= s.total_score < 160)
    low_risk = sum(1 for s in surveys if s.total_score and s.total_score < 120)
    high_risk_list = [s for s in surveys if s.total_score and s.total_score >= 160]
    return render_template("survey/psych_stats.html",
                           surveys=surveys,
                           high_risk=high_risk,
                           medium_risk=medium_risk,
                           low_risk=low_risk,
                           high_risk_list=high_risk_list)


# ── 家长问卷调查（PCE-55）──
@survey_bp.route("/parent")
@login_required
def parent_survey():
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")
    q = PsychSurvey.query.filter_by(survey_type="PCE-55", is_valid=True)
    if session.get("role") == "class_teacher" and class_id:
        q = q.filter_by(class_id=class_id)
    elif session.get("role") == "grade_leader" and grade_id:
        q = q.filter_by(grade_id=grade_id)
    surveys = q.order_by(PsychSurvey.total_score.desc()).all()
    return render_template("survey/parent_survey.html", surveys=surveys)


@survey_bp.route("/analysis")
@login_required
def survey_analysis():
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")
    # 综合分析：合并MSSMHS和PCE
    q = PsychSurvey.query.filter_by(is_valid=True).order_by(PsychSurvey.completed_at.desc())
    if session.get("role") == "class_teacher" and class_id:
        q = q.filter_by(class_id=class_id)
    elif session.get("role") == "grade_leader" and grade_id:
        q = q.filter_by(grade_id=grade_id)
    surveys = q.limit(100).all()
    mssmhs = PsychSurvey.query.filter_by(survey_type="MSSMHS-55", is_valid=True).count()
    pce = PsychSurvey.query.filter_by(survey_type="PCE-55", is_valid=True).count()
    return render_template("survey/analysis.html", surveys=surveys,
                           mssmhs_count=mssmhs, pce_count=pce)


# ── 批量同步高风险问卷 → 心理健康评估 ──
@survey_bp.route("/psych/sync-to-assessment", methods=["POST"])
@require_role("ms_admin", "grade_leader")
def sync_to_assessment():
    """一键同步：扫描所有MSSMHS-55高风险/中风险问卷，自动创建心理健康评估记录"""
    grade_id = session.get("grade_id")
    q = PsychSurvey.query.filter_by(survey_type="MSSMHS-55", is_valid=True, verify_status="COMPLETED")
    if grade_id:
        q = q.filter_by(grade_id=grade_id)

    # 只处理中风险及以上（>=120）
    surveys = q.filter(PsychSurvey.total_score >= 120).all()

    created = 0
    updated = 0
    for survey in surveys:
        student = Student.query.get(survey.student_id)
        if not student:
            continue
        existing = MentalHealthAssessment.query.filter_by(
            student_id=student.id,
            scale_name="MSSMHS-55",
            assessment_type="questionnaire"
        ).first()
        result = _auto_create_mental_health(student, survey.total_score)
        if result:
            if existing:
                updated += 1
            else:
                created += 1

    flash(f"同步完成：新增 {created} 条，更新 {updated} 条心理健康评估记录", "success")
    return redirect(url_for("survey.psych_stats"))
