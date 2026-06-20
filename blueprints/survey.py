"""问卷与心理 — 心理筛查/家长问卷/多维分析"""
from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for
from models import db, Student, PsychSurvey, MentalHealthAssessment, Class as ClassModel
from decorators import login_required, require_role
import json
from datetime import date
from utils.db_utils import safe_commit
from blueprints.common import notify_parent, notify_class_teacher

survey_bp = Blueprint("survey", __name__)

# MSSMHS-55 的10个心理维度（每维度6题，满分30）
MSSMHS_DIMENSIONS = [
    "强迫症状", "偏执", "敌对", "人际敏感", "抑郁",
    "焦虑", "学习压力", "适应不良", "情绪不平衡", "心理不平衡"
]
MSSMHS_MAX_PER_DIM = 30  # 每维度满分


# ── 辅助：解析 dimensions_json ──
def _parse_dimensions(dim_json_str):
    """安全解析 dimensions_json 字符串，返回 dimensions dict"""
    if not dim_json_str:
        return None
    try:
        data = json.loads(dim_json_str)
        return data.get("dimensions") if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


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
@require_role("ms_admin", "grade_leader", "class_teacher")
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
@require_role("ms_admin", "grade_leader", "class_teacher")
def psych_form():
    return render_template("survey/psych_form.html")


@survey_bp.route("/psych/submit", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
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

    # 自动触发：中高风险（≥120）创建心理健康评估
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
@require_role("ms_admin", "grade_leader", "class_teacher")
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
@require_role("ms_admin", "grade_leader", "class_teacher")
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
@require_role("ms_admin", "grade_leader", "class_teacher")
def survey_analysis():
    """心理多维分析 — 雷达图 + AI白皮书"""
    role = session.get("role")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")

    # 获取筛选用的班级列表（角色决定范围）
    if role == "ms_admin":
        classes = ClassModel.query.order_by(ClassModel.name).all()
    elif role == "grade_leader" and grade_id:
        classes = ClassModel.query.filter_by(grade_id=grade_id).order_by(ClassModel.name).all()
    elif role == "class_teacher" and class_id:
        classes = ClassModel.query.filter_by(id=class_id).all()
    else:
        classes = ClassModel.query.order_by(ClassModel.name).all()

    # 统计
    mssmhs = PsychSurvey.query.filter_by(survey_type="MSSMHS-55", is_valid=True, verify_status="COMPLETED").count()
    pce = PsychSurvey.query.filter_by(survey_type="PCE-55", is_valid=True).count()

    return render_template("survey/analysis.html",
                           classes=classes, mssmhs_count=mssmhs, pce_count=pce)


@survey_bp.route("/analysis/dimension-data")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def dimension_data():
    """JSON API: 返回 MSSMHS-55 十维度聚合数据供 ECharts 雷达图渲染"""
    role = session.get("role")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")

    # 前端传入的筛选参数
    filter_class_id = request.args.get("class_id", type=int)
    filter_grade_id = request.args.get("grade_id", type=int)

    # 构建查询 — 仅 MSSMHS-55 有效且含 dimensions_json 的记录
    q = PsychSurvey.query.filter(
        PsychSurvey.survey_type == "MSSMHS-55",
        PsychSurvey.is_valid == True,
        PsychSurvey.verify_status == "COMPLETED",
        PsychSurvey.dimensions_json.isnot(None),
        PsychSurvey.dimensions_json != ""
    )

    # 权限 + 筛选
    if role == "class_teacher" and class_id:
        q = q.filter_by(class_id=class_id)
    elif role == "grade_leader" and grade_id:
        q = q.filter_by(grade_id=grade_id)

    if filter_class_id:
        q = q.filter_by(class_id=filter_class_id)
    elif filter_grade_id:
        q = q.filter_by(grade_id=filter_grade_id)

    surveys = q.all()
    if not surveys:
        return jsonify({
            "indicator": [d for d in MSSMHS_DIMENSIONS],
            "average": [0] * 10,
            "max": [0] * 10,
            "count": 0,
            "top_students": [],
            "risk_distribution": {"high": 0, "medium": 0, "low": 0},
            "class_comparison": []
        })

    # 批量预加载学生信息
    student_ids = list({s.student_id for s in surveys})
    students = Student.query.filter(Student.id.in_(student_ids)).all()
    student_map = {s.id: s for s in students}
    class_ids = list({s.class_id for s in surveys})
    class_infos = ClassModel.query.filter(ClassModel.id.in_(class_ids)).all()
    class_map = {c.id: c for c in class_infos}

    # 聚合各维度分数
    dim_sums = {d: 0.0 for d in MSSMHS_DIMENSIONS}
    dim_max = {d: 0.0 for d in MSSMHS_DIMENSIONS}
    dim_max_students = {d: None for d in MSSMHS_DIMENSIONS}  # 各维度最高分者

    risk_dist = {"high": 0, "medium": 0, "low": 0}

    for survey in surveys:
        dims = _parse_dimensions(survey.dimensions_json)
        if not dims:
            continue
        stu = student_map.get(survey.student_id)
        stu_info = {"id": survey.student_id, "name": stu.name if stu else "未知"}
        cls = class_map.get(survey.class_id)
        if cls:
            stu_info["class_name"] = cls.name

        for dim_name in MSSMHS_DIMENSIONS:
            score = float(dims.get(dim_name, 0))
            dim_sums[dim_name] += score
            if score > dim_max[dim_name]:
                dim_max[dim_name] = score
                dim_max_students[dim_name] = stu_info

        # 风险分布（双轨判定：总分 OR 因子均分）
        total = survey.total_score or 0
        factor_triggered = any(float(dims.get(d, 0)) >= 3.0 for d in MSSMHS_DIMENSIONS)
        if total >= 160:
            risk_dist["high"] += 1
        elif total >= 120 or factor_triggered:
            risk_dist["medium"] += 1
        else:
            risk_dist["low"] += 1

    valid_count = len(surveys)
    averages = [round(dim_sums[d] / valid_count, 2) for d in MSSMHS_DIMENSIONS]
    maxes = [round(dim_max[d], 2) for d in MSSMHS_DIMENSIONS]

    # 各维度最高分学生
    top_students = []
    for dim_name in MSSMHS_DIMENSIONS:
        info = dim_max_students[dim_name]
        if info:
            info["dimension"] = dim_name
            info["score"] = round(dim_max[dim_name], 1)
            top_students.append(info)

    # 班级维度对比（如果选了年级筛选或德育处角色，显示各班对比）
    class_comparison = []
    if (role == "ms_admin" or (role == "grade_leader" and grade_id)) and not filter_class_id:
        # 按班级分组统计
        class_dim_data = {}  # class_id -> {dim: sum}
        class_count = {}     # class_id -> count
        for survey in surveys:
            cid = survey.class_id
            if cid not in class_dim_data:
                class_dim_data[cid] = {d: 0.0 for d in MSSMHS_DIMENSIONS}
                class_count[cid] = 0
            dims = _parse_dimensions(survey.dimensions_json)
            if not dims:
                continue
            class_count[cid] += 1
            for dim_name in MSSMHS_DIMENSIONS:
                class_dim_data[cid][dim_name] += float(dims.get(dim_name, 0))

        for cid, counts in class_count.items():
            if counts == 0:
                continue
            cls = class_map.get(cid)
            class_comparison.append({
                "class_id": cid,
                "class_name": cls.name if cls else f"班级{cid}",
                "count": counts,
                "averages": [round(class_dim_data[cid][d] / counts, 2) for d in MSSMHS_DIMENSIONS]
            })
        class_comparison.sort(key=lambda x: x["class_name"])

    return jsonify({
        "indicator": MSSMHS_DIMENSIONS,
        "max_per_dim": MSSMHS_MAX_PER_DIM,
        "average": averages,
        "max": maxes,
        "count": valid_count,
        "top_students": top_students,
        "risk_distribution": risk_dist,
        "class_comparison": class_comparison,
    })


@survey_bp.route("/analysis/ai", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader")
def analysis_ai():
    """AI 宏观分析 — 调用 DeepSeek 生成心理健康白皮书"""
    try:
        from utils.llm_client import call_llm
        from utils import get_local_now
    except ImportError:
        return jsonify({"error": "LLM 客户端未就绪"}), 500

    role = session.get("role")
    grade_id = session.get("grade_id")

    # 获取完整聚合数据
    q = PsychSurvey.query.filter(
        PsychSurvey.survey_type == "MSSMHS-55",
        PsychSurvey.is_valid == True,
        PsychSurvey.verify_status == "COMPLETED",
        PsychSurvey.dimensions_json.isnot(None),
        PsychSurvey.dimensions_json != ""
    )
    if role == "grade_leader" and grade_id:
        q = q.filter_by(grade_id=grade_id)

    surveys = q.all()
    if not surveys:
        return jsonify({"error": "暂无有效问卷数据"}), 400

    # 聚合统计
    dim_sums = {d: 0.0 for d in MSSMHS_DIMENSIONS}
    dim_max = {d: 0.0 for d in MSSMHS_DIMENSIONS}
    valid_count = len(surveys)
    total_scores = []
    risk_dist = {"high": 0, "medium": 0, "low": 0}

    for survey in surveys:
        dims = _parse_dimensions(survey.dimensions_json)
        if not dims:
            continue
        for dim_name in MSSMHS_DIMENSIONS:
            score = float(dims.get(dim_name, 0))
            dim_sums[dim_name] += score
            if score > dim_max[dim_name]:
                dim_max[dim_name] = score
        total = survey.total_score or 0
        total_scores.append(total)
        if total >= 160:
            risk_dist["high"] += 1
        elif total >= 120:
            risk_dist["medium"] += 1
        else:
            risk_dist["low"] += 1

    dim_avg = {d: round(dim_sums[d] / valid_count, 2) for d in MSSMHS_DIMENSIONS}
    avg_total = round(sum(total_scores) / valid_count, 2) if total_scores else 0
    max_total = max(total_scores) if total_scores else 0
    min_total = min(total_scores) if total_scores else 0

    # 构建发送给 LLM 的分析数据摘要
    data_summary = (
        f"## 梨江中学 MSSMHS-55 心理筛查数据摘要\n\n"
        f"- 有效问卷数: {valid_count} 份\n"
        f"- 总分均值: {avg_total} / 275\n"
        f"- 总分范围: {min_total} ~ {max_total}\n"
        f"- 风险分布: 高风险 {risk_dist['high']} 人({risk_dist['high']/valid_count*100:.1f}%), "
        f"中风险 {risk_dist['medium']} 人({risk_dist['medium']/valid_count*100:.1f}%), "
        f"低风险 {risk_dist['low']} 人({risk_dist['low']/valid_count*100:.1f}%)\n\n"
        f"### 各维度均分（满分30分）\n"
    )
    for dim_name in MSSMHS_DIMENSIONS:
        avg = dim_avg[dim_name]
        pct = avg / 30 * 100
        level = "偏高" if pct > 50 else "中等" if pct > 30 else "正常"
        data_summary += f"- {dim_name}: {avg} ({level}, 占满分{pct:.1f}%)\n"
    data_summary += (
        f"\n### 各维度最高分\n"
    )
    for dim_name in MSSMHS_DIMENSIONS:
        data_summary += f"- {dim_name}: {round(dim_max[dim_name], 1)}\n"

    system_prompt = (
        "你是一位资深的学校心理健康教育顾问和数据分析师。"
        "请基于以下 MSSMHS-55（中学生心理健康量表）筛查数据，"
        "撰写一份专业、实用的《学生心理健康宏观分析报告》。\n\n"
        "要求:\n"
        "1. 使用 Markdown 格式输出\n"
        "2. 报告结构: 一、总体概况 → 二、维度分析（逐项解读10个维度）"
        " → 三、风险研判 → 四、针对性建议（给德育处和班主任的具体行动建议）\n"
        "3. 语言专业但不晦涩，适合中学校领导阅读\n"
        "4. 数据引用要具体，结合维度分值做判断\n"
        "5. 给出至少3条可操作的干预建议"
    )

    try:
        report = call_llm(system_prompt, data_summary, max_tokens=4096, timeout=60)
        return jsonify({"report": report})
    except Exception as e:
        return jsonify({"error": f"AI 分析生成失败: {str(e)}"}), 500


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
