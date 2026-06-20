"""AI德育大秘评语引擎
功能一: 班级月度德育处方 — 吃 FlagArchiveReport 快照 + FlagEvaluation 三维数据
功能二: 高风险学生考前心理安抚话术 — 吃 InterventionRecord 轨迹 + MentalHealthAssessment 十维数据

统一使用 utils/llm_client.call_llm() 获得熔断保护（非本地实现）
"""
from flask import Blueprint, render_template, request, jsonify, session, current_app
from models import (
    db, Student, Class, Grade, FlagArchiveReport, FlagEvaluation,
    InterventionRecord, MentalHealthAssessment,
    AIPrescriptionRecord, AIPsychComfortRecord, User
)
from decorators import login_required, require_role
from utils.llm_client import call_llm, LLMAvailabilityError
from utils import get_local_now
import json
import re
import traceback

ai_prescription_bp = Blueprint("ai_prescription", __name__)


# ==================================================================
#  System Prompts — 工业级 Prompt 工程
# ==================================================================

CLASS_PRESCRIPTION_SYSTEM_PROMPT = """你是一位拥有20年初中德育管理经验的资深德育顾问。你的任务是根据班级的流动红旗评价快照数据（三维评分、违纪扣分、考勤异常、排名变化），生成一份《班级月度德育处方》。

[核心要求]
1. 必须基于提供的数据进行分析，严禁编造数据。
2. 处方分为五个部分：总体诊断、优势分析、短板预警、风险预警、行动建议。
3. 语气专业但接地气，像一位老德育主任在给班主任手把手指导。
4. 行动建议必须具体可执行，包含时间节点和责任主体。
5. 如果该班获得了流动红旗，要在处方中给予肯定；如果未获得，要分析差距和追赶策略。
6. 三维评分（自评/年级组/德育处）如有差异，要点出差异原因。

[输出格式]
必须输出严格的 JSON 格式，不要任何 Markdown 包裹，直接返回以下结构：
{
  "diagnosis": "总体诊断（100-150字，概括班级本周期德育整体表现，含得分和排名）",
  "strengths": ["优势1（30-50字）", "优势2（30-50字）"],
  "weaknesses": ["短板1（30-50字）", "短板2（30-50字）"],
  "risk_warning": "风险预警（80-120字，指出需要关注的系统性问题；如无重大风险则写'本周期未见明显系统性风险'）",
  "action_plan": [
    {"action": "具体行动措施", "timeline": "时间节点", "owner": "责任主体"},
    {"action": "具体行动措施", "timeline": "时间节点", "owner": "责任主体"}
  ],
  "encouragement": "给班主任的一句话鼓励（30-50字，有温度有力量）"
}"""


PSYCH_COMFORT_SYSTEM_PROMPT = """你是一位拥有15年青少年心理咨询经验的资深心理专家，特别擅长考前心理危机干预。你的任务是根据学生的心理健康评估数据（多维因子得分）、干预记录轨迹和家长反馈，为高风险学生定制一份《考前心理安抚精细化话术指南》。

[核心要求]
1. 话术必须基于学生的真实心理评估数据，严禁泛泛而谈和套话。
2. 话术要区分"对学生说的话"和"对家长说的话"两个场景。
3. 对学生的话术要温暖、有力量、能引发共鸣，避免说教和空洞鼓励。
4. 对家长的话术要专业、有操作性，帮助家长成为支持者而非施压者。
5. 必须点出学生最突出的1-2个心理风险因子，并给出针对性的安抚策略。
6. 如果学生有干预记录，要在话术中体现对干预效果的肯定和延续。
7. 如果学生有家长反馈，要在家长指导中回应家长的关注点。

[输出格式]
必须输出严格的 JSON 格式，不要任何 Markdown 包裹，直接返回以下结构：
{
  "student_profile": "学生心理画像（80-120字，基于多维因子描绘学生的心理状态轮廓）",
  "key_factors": [
    {"factor": "突出风险因子名称", "score": "得分", "analysis": "该因子的具体表现和影响（30-50字）"}
  ],
  "student_script": {
    "opening": "开场白（温暖破冰，50-80字）",
    "empathy": "共情段落（让学生感到被理解，80-120字）",
    "empowerment": "赋能段落（激发学生内在力量，80-120字）",
    "closing": "收尾段落（给予安全感和后续支持承诺，50-80字）"
  },
  "parent_guide": {
    "communication_tips": ["沟通要点1（30-50字）", "沟通要点2（30-50字）", "沟通要点3（30-50字）"],
    "avoid_list": ["应避免行为1（20-30字）", "应避免行为2（20-30字）"],
    "support_actions": ["支持行动1（30-50字）", "支持行动2（30-50字）"]
  },
  "follow_up": "后续跟进建议（50-80字，建议下一次评估或干预的时间点和重点）"
}"""


# MSSMHS-55 维度名称映射（数字键 -> 中文名）
MSSMHS_DIMENSIONS = {
    1: "强迫症状", 2: "偏执", 3: "敌对", 4: "人际关系紧张敏感",
    5: "抑郁", 6: "焦虑", 7: "学习压力", 8: "适应不良",
    9: "情绪不平衡", 10: "心理不平衡"
}


# ==================================================================
#  辅助函数
# ==================================================================

def _get_scope_filters():
    """获取当前用户的角色数据范围过滤条件"""
    role = session.get("role")
    class_id = session.get("class_id")
    grade_id = session.get("grade_id")
    if role == "class_teacher":
        return {"class_id": class_id, "grade_id": None}
    elif role == "grade_leader":
        return {"class_id": None, "grade_id": grade_id}
    return {"class_id": None, "grade_id": None}


def _parse_json_response(raw_text):
    """安全解析 LLM 返回的 JSON（含 regex 降级提取）"""
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError(f"LLM 返回非 JSON 格式: {raw_text[:200]}")


def _build_class_context(class_id, period_type, period_label):
    """构建班级德育处方上下文数据"""
    # 1. 获取该班级的归档快照
    archive = FlagArchiveReport.query.filter_by(
        class_id=class_id, period_type=period_type, period_label=period_label
    ).first()

    if not archive:
        return None

    # 2. 获取同年级所有班级的排名信息
    grade_archives = FlagArchiveReport.query.filter_by(
        grade_id=archive.grade_id, period_type=period_type, period_label=period_label
    ).order_by(FlagArchiveReport.rank.asc()).all()

    # 3. 获取 FlagEvaluation 三维评分
    evaluation = FlagEvaluation.query.filter_by(
        class_id=class_id, period_type=period_type, period_label=period_label
    ).first()

    # 4. 获取班级/年级信息
    class_obj = Class.query.get(class_id)
    grade_obj = Grade.query.get(archive.grade_id)

    # 5. 解析快照数据
    snapshot = archive.snapshot_data

    context = {
        "class_name": class_obj.name if class_obj else "未知班级",
        "grade_name": grade_obj.name if grade_obj else "未知年级",
        "period_label": period_label,
        "period_type": period_type,
        "final_score": archive.final_score,
        "rank": archive.rank,
        "total_classes": len(grade_archives),
        "has_flag": archive.has_flag,
        "base_score": archive.base_score,
        "discipline_deduction": archive.discipline_deduction,
        "attendance_deduction": archive.attendance_deduction,
        "snapshot": snapshot,
        "evaluation": None,
        "grade_ranking": []
    }

    # 三维评分明细
    if evaluation:
        context["evaluation"] = {
            "self_score": evaluation.self_score,
            "grade_score": evaluation.grade_score,
            "ms_score": evaluation.ms_score,
            "self_weight": evaluation.self_weight,
            "grade_weight": evaluation.grade_weight,
            "ms_weight": evaluation.ms_weight,
            "discipline_points": evaluation.discipline_points,
            "attendance_exceptions": evaluation.attendance_exceptions,
        }

    # 年级排名对比列表
    for ga in grade_archives:
        cls = Class.query.get(ga.class_id)
        context["grade_ranking"].append({
            "rank": ga.rank,
            "class_name": cls.name if cls else f"班级{ga.class_id}",
            "final_score": ga.final_score,
            "has_flag": ga.has_flag,
            "is_current": ga.class_id == class_id
        })

    return context


def _format_class_prompt(ctx):
    """将班级上下文格式化为 LLM 提示"""
    parts = []
    parts.append(f"班级: {ctx['class_name']}")
    parts.append(f"年级: {ctx['grade_name']}")
    parts.append(f"评价周期: {ctx['period_label']} ({ctx['period_type']})")
    parts.append(f"最终得分: {ctx['final_score']}分")
    parts.append(f"年级排名: 第{ctx['rank']}名 / 共{ctx['total_classes']}个班")
    parts.append(f"是否获得流动红旗: {'是' if ctx['has_flag'] else '否'}")
    parts.append(f"加权底分(扣分前): {ctx['base_score']}")
    parts.append(f"违纪扣分: {ctx['discipline_deduction']}")
    parts.append(f"考勤扣分: {ctx['attendance_deduction']}")

    # 三维评分
    ev = ctx.get("evaluation")
    if ev:
        parts.append(f"\n[三维评分明细]")
        parts.append(f"  班主任自评均分: {ev['self_score']} (权重{ev['self_weight']})")
        parts.append(f"  年级组评级均分: {ev['grade_score']} (权重{ev['grade_weight']})")
        parts.append(f"  德育处评级均分: {ev['ms_score']} (权重{ev['ms_weight']})")
        parts.append(f"  违纪扣分总额: {ev['discipline_points']}")
        parts.append(f"  考勤异常次数: {ev['attendance_exceptions']}")

    # 快照数据
    snap = ctx.get("snapshot", {})
    if snap:
        parts.append(f"\n[深度快照数据]")
        if snap.get("discipline_events"):
            events = snap["discipline_events"]
            parts.append(f"  违纪事件明细({len(events)}条):")
            for evt in events[:10]:
                parts.append(f"    - {evt}")

        if snap.get("routine_details"):
            parts.append(f"  常规评分明细: {json.dumps(snap['routine_details'], ensure_ascii=False)[:300]}")

        if snap.get("attendance_details"):
            parts.append(f"  考勤明细: {json.dumps(snap['attendance_details'], ensure_ascii=False)[:200]}")

    # 年级排名对比
    ranking = ctx.get("grade_ranking", [])
    if ranking:
        parts.append(f"\n[年级排名对比]")
        for r in ranking:
            marker = " <== 本班" if r["is_current"] else ""
            flag = " [红旗]" if r["has_flag"] else ""
            parts.append(f"  第{r['rank']}名: {r['class_name']} ({r['final_score']}分){flag}{marker}")

    return "\n".join(parts)


def _build_psych_context(student):
    """构建学生心理安抚上下文数据"""
    # 1. 最新心理健康评估
    mh = MentalHealthAssessment.query.filter_by(
        student_id=student.id
    ).order_by(MentalHealthAssessment.created_at.desc()).first()

    # 2. 干预记录
    interventions = InterventionRecord.query.filter_by(
        student_id=student.id
    ).order_by(InterventionRecord.created_at.desc()).all()

    context = {
        "student_name": student.name,
        "gender": student.gender or "未知",
        "class_name": student.class_.name if student.class_ else "未知",
        "mental_health": None,
        "interventions": [],
        "intervention_count": len(interventions)
    }

    # 心理评估数据
    if mh:
        # 解析维度得分
        dim_scores = {}
        if mh.dimension_scores:
            try:
                raw = json.loads(mh.dimension_scores)
                if isinstance(raw, dict):
                    for k, v in raw.items():
                        dim_name = MSSMHS_DIMENSIONS.get(int(k), k) if str(k).isdigit() else k
                        dim_scores[dim_name] = v
                elif isinstance(raw, list):
                    for i, v in enumerate(raw):
                        dim_name = MSSMHS_DIMENSIONS.get(i + 1, f"维度{i+1}")
                        dim_scores[dim_name] = v
            except (json.JSONDecodeError, TypeError):
                dim_scores = {"原始数据": str(mh.dimension_scores)[:200]}

        context["mental_health"] = {
            "scale_name": mh.scale_name or "MSSMHS-55",
            "total_score": mh.total_score,
            "risk_level": mh.risk_level,
            "dimension_scores": dim_scores,
            "conclusion": mh.conclusion,
            "recommendations": mh.recommendations,
            "need_intervention": mh.need_intervention,
            "intervention_plan": mh.intervention_plan,
            "assessment_date": mh.assessment_date.isoformat() if mh.assessment_date else None,
        }

    # 干预记录
    for iv in interventions:
        context["interventions"].append({
            "type": iv.intervention_type,
            "status": iv.status,
            "effect_rating": iv.effect_rating,
            "risk_before": iv.risk_before,
            "risk_after": iv.risk_after,
            "mh_risk_before": iv.mh_risk_before,
            "mh_risk_after": iv.mh_risk_after,
            "notes": iv.notes[:200] if iv.notes else "",
            "parent_feedback": iv.parent_feedback[:200] if iv.parent_feedback else "",
            "intervention_date": iv.intervention_date.isoformat() if iv.intervention_date else None,
            "follow_up_done": iv.follow_up_done,
            "follow_up_notes": iv.follow_up_notes[:200] if iv.follow_up_notes else "",
        })

    return context


def _format_psych_prompt(ctx):
    """将学生心理上下文格式化为 LLM 提示"""
    parts = []
    parts.append(f"学生姓名: {ctx['student_name']}")
    parts.append(f"性别: {ctx['gender']}")
    parts.append(f"班级: {ctx['class_name']}")

    # 心理评估数据
    mh = ctx.get("mental_health")
    if mh:
        parts.append(f"\n[心理健康评估]")
        parts.append(f"  量表: {mh['scale_name']}")
        parts.append(f"  总分: {mh['total_score']}")
        parts.append(f"  风险等级: {mh['risk_level']}")
        parts.append(f"  评估日期: {mh['assessment_date']}")

        if mh["dimension_scores"]:
            parts.append(f"\n[多维因子得分]")
            for dim, score in mh["dimension_scores"].items():
                parts.append(f"  {dim}: {score}")

        if mh.get("conclusion"):
            parts.append(f"\n[评估结论] {mh['conclusion'][:200]}")
        if mh.get("recommendations"):
            parts.append(f"[建议措施] {mh['recommendations'][:200]}")
        if mh.get("intervention_plan"):
            parts.append(f"[干预计划] {mh['intervention_plan'][:200]}")
    else:
        parts.append("\n[心理健康评估] 暂无评估数据")

    # 干预记录
    ivs = ctx.get("interventions", [])
    if ivs:
        parts.append(f"\n[干预记录] 共{len(ivs)}条")
        for i, iv in enumerate(ivs, 1):
            parts.append(f"\n  --- 干预{i} ---")
            parts.append(f"  类型: {iv['type']}")
            parts.append(f"  状态: {iv['status']}")
            parts.append(f"  效果评价: {iv['effect_rating'] or '未评价'}")
            parts.append(f"  干预日期: {iv['intervention_date']}")

            if iv.get("mh_risk_before") and iv.get("mh_risk_after"):
                parts.append(f"  心理风险变化: {iv['mh_risk_before']} -> {iv['mh_risk_after']}")
            elif iv.get("risk_before") is not None and iv.get("risk_after") is not None:
                parts.append(f"  AI风险变化: {iv['risk_before']} -> {iv['risk_after']}")

            if iv.get("notes"):
                parts.append(f"  干预详情: {iv['notes']}")
            if iv.get("parent_feedback"):
                parts.append(f"  家长反馈: {iv['parent_feedback']}")
            if iv.get("follow_up_done"):
                parts.append(f"  随访完成: {iv.get('follow_up_notes', '是')}")
    else:
        parts.append("\n[干预记录] 暂无干预记录")

    return "\n".join(parts)


# ==================================================================
#  路由
# ==================================================================

@ai_prescription_bp.route("/")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def index():
    """AI 评语引擎首页"""
    return render_template("ai_prescription/index.html")


@ai_prescription_bp.route("/class-prescription")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def class_prescription():
    """班级月度德育处方页面"""
    scope = _get_scope_filters()

    # 获取可用班级
    if scope["class_id"]:
        classes = Class.query.filter_by(id=scope["class_id"], is_active=True).order_by(Class.name).all()
    elif scope["grade_id"]:
        classes = Class.query.filter_by(grade_id=scope["grade_id"], is_active=True).order_by(Class.name).all()
    else:
        classes = Class.query.filter_by(is_active=True).order_by(Class.name).all()

    # 获取可用周期（从归档表中提取）
    period_rows = db.session.query(
        FlagArchiveReport.period_type, FlagArchiveReport.period_label
    ).distinct().order_by(FlagArchiveReport.period_label.desc()).all()

    period_options = [{"period_type": pt, "period_label": pl} for pt, pl in period_rows]

    return render_template("ai_prescription/class_prescription.html",
                           classes=classes, periods=period_options)


@ai_prescription_bp.route("/api/class-prescription", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def api_class_prescription():
    """生成班级月度德育处方"""
    data = request.get_json(silent=True) or {}
    class_id = data.get("class_id")
    period_type = data.get("period_type", "month")
    period_label = data.get("period_label")

    if not class_id or not period_label:
        return jsonify({"status": "error", "message": "请选择班级和评价周期"}), 400

    # 数据隔离
    scope = _get_scope_filters()
    if scope["class_id"] and int(class_id) != scope["class_id"]:
        return jsonify({"status": "error", "message": "无权访问该班级"}), 403

    class_obj = Class.query.get(class_id)
    if not class_obj:
        return jsonify({"status": "error", "message": "班级不存在"}), 404

    if scope["grade_id"] and class_obj.grade_id != scope["grade_id"]:
        return jsonify({"status": "error", "message": "无权访问该班级"}), 403

    # 构建上下文
    ctx = _build_class_context(class_id, period_type, period_label)
    if not ctx:
        return jsonify({
            "status": "error",
            "message": f"未找到 {period_label} 的归档数据，请先在流动红旗模块完成归档"
        }), 404

    # 格式化提示
    user_prompt = _format_class_prompt(ctx)

    # 调用 LLM
    try:
        raw = call_llm(
            CLASS_PRESCRIPTION_SYSTEM_PROMPT,
            user_prompt,
            temperature=0.7,
            max_tokens=2048,
            response_format={"type": "json_object"},
            timeout=60
        )
        prescription = _parse_json_response(raw)

        return jsonify({
            "status": "success",
            "data": prescription,
            "context": {
                "class_name": ctx["class_name"],
                "period_label": ctx["period_label"],
                "final_score": ctx["final_score"],
                "rank": ctx["rank"],
                "has_flag": ctx["has_flag"]
            }
        })

    except LLMAvailabilityError as e:
        return jsonify({"status": "error", "message": str(e)}), 503
    except (json.JSONDecodeError, ValueError) as e:
        current_app.logger.error(f"LLM返回非JSON: {str(e)[:200]}")
        return jsonify({"status": "error", "message": "AI返回格式异常，请重试"}), 500
    except RuntimeError as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    except Exception as e:
        current_app.logger.error(f"班级处方生成失败: {traceback.format_exc()}")
        return jsonify({"status": "error", "message": f"生成失败: {str(e)[:100]}"}), 500


@ai_prescription_bp.route("/psych-comfort")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def psych_comfort():
    """高风险学生考前心理安抚话术页面"""
    scope = _get_scope_filters()

    # 查询高风险学生
    mh_query = MentalHealthAssessment.query.filter(
        MentalHealthAssessment.risk_level == "high"
    )

    if scope["class_id"]:
        mh_query = mh_query.filter(MentalHealthAssessment.class_id == scope["class_id"])
    elif scope["grade_id"]:
        mh_query = mh_query.filter(MentalHealthAssessment.grade_id == scope["grade_id"])

    # 获取每个高风险学生的最新评估（去重）
    high_risk_students = []
    seen_student_ids = set()
    for mh in mh_query.order_by(MentalHealthAssessment.created_at.desc()).all():
        if mh.student_id in seen_student_ids:
            continue
        seen_student_ids.add(mh.student_id)

        stu = mh.student
        if not stu or not stu.is_active:
            continue

        iv_count = InterventionRecord.query.filter_by(student_id=stu.id).count()

        high_risk_students.append({
            "student_id": stu.id,
            "student_name": stu.name,
            "class_name": stu.class_.name if stu.class_ else "未知",
            "total_score": mh.total_score,
            "risk_level": mh.risk_level,
            "scale_name": mh.scale_name or "MSSMHS-55",
            "assessment_date": mh.assessment_date.isoformat() if mh.assessment_date else None,
            "intervention_count": iv_count,
            "need_intervention": mh.need_intervention
        })

    return render_template("ai_prescription/psych_comfort.html",
                           high_risk_students=high_risk_students)


@ai_prescription_bp.route("/history")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def history_page():
    """德育大秘历史档案馆页面"""
    return render_template("ai_prescription/history.html")


@ai_prescription_bp.route("/api/psych-comfort/<int:student_id>", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def api_psych_comfort(student_id):
    """生成单个学生的考前心理安抚话术"""
    stu = Student.query.get_or_404(student_id)

    # 数据隔离
    scope = _get_scope_filters()
    if scope["class_id"] and stu.class_id != scope["class_id"]:
        return jsonify({"status": "error", "message": "无权访问该学生"}), 403
    if scope["grade_id"] and stu.grade_id != scope["grade_id"]:
        return jsonify({"status": "error", "message": "无权访问该学生"}), 403

    # 构建上下文
    ctx = _build_psych_context(stu)

    if not ctx["mental_health"]:
        return jsonify({
            "status": "error",
            "message": "该学生暂无心理健康评估数据，无法生成安抚话术"
        }), 404

    # 格式化提示
    user_prompt = _format_psych_prompt(ctx)

    # 调用 LLM
    try:
        raw = call_llm(
            PSYCH_COMFORT_SYSTEM_PROMPT,
            user_prompt,
            temperature=0.7,
            max_tokens=4096,
            response_format={"type": "json_object"},
            timeout=90
        )
        comfort_data = _parse_json_response(raw)

        return jsonify({
            "status": "success",
            "data": comfort_data,
            "student_name": stu.name,
            "student_id": stu.id
        })

    except LLMAvailabilityError as e:
        return jsonify({"status": "error", "message": str(e)}), 503
    except (json.JSONDecodeError, ValueError) as e:
        current_app.logger.error(f"LLM返回非JSON: {str(e)[:200]}")
        return jsonify({"status": "error", "message": "AI返回格式异常，请重试"}), 500
    except RuntimeError as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    except Exception as e:
        current_app.logger.error(f"心理安抚话术生成失败: {traceback.format_exc()}")
        return jsonify({"status": "error", "message": f"生成失败: {str(e)[:100]}"}), 500


@ai_prescription_bp.route("/api/psych-comfort-batch", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader")
def api_psych_comfort_batch():
    """批量生成高风险学生心理安抚话术"""
    scope = _get_scope_filters()

    # 查询高风险学生（去重）
    mh_query = MentalHealthAssessment.query.filter(
        MentalHealthAssessment.risk_level == "high"
    )
    if scope["grade_id"]:
        mh_query = mh_query.filter(MentalHealthAssessment.grade_id == scope["grade_id"])

    seen = set()
    students = []
    for mh in mh_query.order_by(MentalHealthAssessment.created_at.desc()).all():
        if mh.student_id in seen:
            continue
        seen.add(mh.student_id)
        stu = mh.student
        if stu and stu.is_active:
            students.append(stu)

    if not students:
        return jsonify({"status": "error", "message": "未找到高风险学生"}), 404

    results = []
    success_count = 0
    fail_count = 0

    for stu in students:
        try:
            ctx = _build_psych_context(stu)
            if not ctx["mental_health"]:
                results.append({
                    "student_id": stu.id,
                    "student_name": stu.name,
                    "status": "error",
                    "message": "无心理评估数据"
                })
                fail_count += 1
                continue

            user_prompt = _format_psych_prompt(ctx)
            raw = call_llm(
                PSYCH_COMFORT_SYSTEM_PROMPT,
                user_prompt,
                temperature=0.7,
                max_tokens=4096,
                response_format={"type": "json_object"},
                timeout=90
            )
            comfort_data = _parse_json_response(raw)

            results.append({
                "student_id": stu.id,
                "student_name": stu.name,
                "status": "success",
                "data": comfort_data
            })
            success_count += 1

        except LLMAvailabilityError as e:
            # 熔断器打开，停止后续请求
            results.append({
                "student_id": stu.id,
                "student_name": stu.name,
                "status": "error",
                "message": str(e)
            })
            fail_count += 1
            break
        except Exception as e:
            results.append({
                "student_id": stu.id,
                "student_name": stu.name,
                "status": "error",
                "message": str(e)[:100]
            })
            fail_count += 1

    return jsonify({
        "status": "success" if fail_count == 0 else "partial",
        "total": len(students),
        "success": success_count,
        "failed": fail_count,
        "results": results
    })


# ==================================================================
#  持久化路由 — AI 输出落盘 & 历史回溯
# ==================================================================

@ai_prescription_bp.route("/api/save", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def api_save():
    """将 AI 生成结果写入持久化表（班级处方 / 心理安抚）

    请求体:
      type: "class_prescription" | "psych_comfort"
      class_id / student_id / period_type / period_label / assessment_id
      diagnosis_json / comfort_script_json  (完整 JSON 字符串)
    """
    data = request.get_json(silent=True) or {}
    record_type = data.get("type")
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"status": "error", "message": "用户未登录"}), 401

    try:
        if record_type == "class_prescription":
            # ── 班级处方落盘 ──
            class_id = data.get("class_id")
            period_type = data.get("period_type", "month")
            period_label = data.get("period_label")
            diagnosis_json = data.get("diagnosis_json")

            if not class_id or not period_label or not diagnosis_json:
                return jsonify({"status": "error", "message": "缺少必要参数"}), 400

            class_obj = Class.query.get(class_id)
            if not class_obj:
                return jsonify({"status": "error", "message": "班级不存在"}), 404

            # 数据隔离
            scope = _get_scope_filters()
            if scope["class_id"] and int(class_id) != scope["class_id"]:
                return jsonify({"status": "error", "message": "无权操作该班级"}), 403
            if scope["grade_id"] and class_obj.grade_id != scope["grade_id"]:
                return jsonify({"status": "error", "message": "无权操作该班级"}), 403

            # 重复覆盖更新（同周期+同班级）
            existing = AIPrescriptionRecord.query.filter_by(
                grade_id=class_obj.grade_id,
                class_id=class_id,
                period_type=period_type,
                period_label=period_label
            ).first()

            if existing:
                existing.diagnosis_json = diagnosis_json
                existing.created_at = get_local_now()
                existing.created_by = user_id
                record = existing
                action = "updated"
            else:
                record = AIPrescriptionRecord(
                    period_type=period_type,
                    period_label=period_label,
                    grade_id=class_obj.grade_id,
                    class_id=class_id,
                    diagnosis_json=diagnosis_json,
                    created_by=user_id
                )
                db.session.add(record)
                action = "created"

            db.session.commit()
            return jsonify({
                "status": "success",
                "action": action,
                "record_id": record.id,
                "message": "班级处方已保存" if action == "created" else "班级处方已更新"
            })

        elif record_type == "psych_comfort":
            # ── 心理安抚话术落盘 ──
            student_id = data.get("student_id")
            assessment_id = data.get("assessment_id")
            comfort_script_json = data.get("comfort_script_json")

            if not student_id or not comfort_script_json:
                return jsonify({"status": "error", "message": "缺少必要参数"}), 400

            stu = Student.query.get(student_id)
            if not stu:
                return jsonify({"status": "error", "message": "学生不存在"}), 404

            # 数据隔离
            scope = _get_scope_filters()
            if scope["class_id"] and stu.class_id != scope["class_id"]:
                return jsonify({"status": "error", "message": "无权操作该学生"}), 403
            if scope["grade_id"] and stu.grade_id != scope["grade_id"]:
                return jsonify({"status": "error", "message": "无权操作该学生"}), 403

            record = AIPsychComfortRecord(
                student_id=student_id,
                assessment_id=assessment_id,
                comfort_script_json=comfort_script_json,
                created_by=user_id
            )
            db.session.add(record)
            db.session.commit()

            return jsonify({
                "status": "success",
                "action": "created",
                "record_id": record.id,
                "message": "心理安抚话术已保存"
            })

        else:
            return jsonify({"status": "error", "message": "未知的保存类型"}), 400

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"AI记录保存失败: {traceback.format_exc()}")
        return jsonify({"status": "error", "message": f"保存失败: {str(e)[:100]}"}), 500


@ai_prescription_bp.route("/api/history/class")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def api_history_class():
    """查询班级处方历史列表"""
    scope = _get_scope_filters()
    grade_id = request.args.get("grade_id", type=int)
    class_id = request.args.get("class_id", type=int)
    period_label = request.args.get("period_label", "")

    query = AIPrescriptionRecord.query

    # 数据隔离
    if scope["class_id"]:
        query = query.filter(AIPrescriptionRecord.class_id == scope["class_id"])
    elif scope["grade_id"]:
        query = query.filter(AIPrescriptionRecord.grade_id == scope["grade_id"])

    # 过滤条件
    if grade_id and not scope["class_id"]:
        query = query.filter(AIPrescriptionRecord.grade_id == grade_id)
    if class_id:
        query = query.filter(AIPrescriptionRecord.class_id == class_id)
    if period_label:
        query = query.filter(AIPrescriptionRecord.period_label == period_label)

    records = query.order_by(AIPrescriptionRecord.created_at.desc()).limit(100).all()

    result = []
    for r in records:
        try:
            diagnosis = json.loads(r.diagnosis_json)
        except (json.JSONDecodeError, TypeError):
            diagnosis = {}

        result.append({
            "id": r.id,
            "period_type": r.period_type,
            "period_label": r.period_label,
            "grade_name": r.grade.name if r.grade else "",
            "class_name": r.class_.name if r.class_ else "",
            "diagnosis_summary": diagnosis.get("diagnosis", "")[:80],
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "creator_name": r.creator.display_name if r.creator else "",
        })

    return jsonify({"status": "success", "records": result})


@ai_prescription_bp.route("/api/history/psych")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def api_history_psych():
    """查询学生心理安抚历史列表"""
    scope = _get_scope_filters()
    student_id = request.args.get("student_id", type=int)
    class_id = request.args.get("class_id", type=int)

    query = AIPsychComfortRecord.query

    # 数据隔离 — 通过 student 表间接过滤
    if scope["class_id"] or scope["grade_id"]:
        query = query.join(Student, AIPsychComfortRecord.student_id == Student.id)
        if scope["class_id"]:
            query = query.filter(Student.class_id == scope["class_id"])
        elif scope["grade_id"]:
            query = query.filter(Student.grade_id == scope["grade_id"])

    if student_id:
        query = query.filter(AIPsychComfortRecord.student_id == student_id)
    if class_id:
        query = query.join(Student, AIPsychComfortRecord.student_id == Student.id)
        query = query.filter(Student.class_id == class_id)

    records = query.order_by(AIPsychComfortRecord.created_at.desc()).limit(100).all()

    result = []
    for r in records:
        try:
            script = json.loads(r.comfort_script_json)
        except (json.JSONDecodeError, TypeError):
            script = {}

        result.append({
            "id": r.id,
            "student_name": r.student.name if r.student else "",
            "class_name": r.student.class_.name if r.student and r.student.class_ else "",
            "student_profile": script.get("student_profile", "")[:80],
            "key_factors_count": len(script.get("key_factors", [])),
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "creator_name": r.creator.display_name if r.creator else "",
        })

    return jsonify({"status": "success", "records": result})


@ai_prescription_bp.route("/api/detail/<record_type>/<int:record_id>")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def api_detail(record_type, record_id):
    """获取单条历史记录完整 JSON"""
    scope = _get_scope_filters()

    if record_type == "class":
        record = AIPrescriptionRecord.query.get_or_404(record_id)
        # 数据隔离
        if scope["class_id"] and record.class_id != scope["class_id"]:
            return jsonify({"status": "error", "message": "无权访问"}), 403
        if scope["grade_id"] and record.grade_id != scope["grade_id"]:
            return jsonify({"status": "error", "message": "无权访问"}), 403

        return jsonify({
            "status": "success",
            "type": "class",
            "data": json.loads(record.diagnosis_json) if record.diagnosis_json else {},
            "meta": {
                "id": record.id,
                "period_label": record.period_label,
                "period_type": record.period_type,
                "class_name": record.class_.name if record.class_ else "",
                "grade_name": record.grade.name if record.grade else "",
                "created_at": record.created_at.isoformat() if record.created_at else "",
                "creator_name": record.creator.display_name if record.creator else "",
            }
        })

    elif record_type == "psych":
        record = AIPsychComfortRecord.query.get_or_404(record_id)
        # 数据隔离 — 通过 student 表
        if record.student:
            if scope["class_id"] and record.student.class_id != scope["class_id"]:
                return jsonify({"status": "error", "message": "无权访问"}), 403
            if scope["grade_id"] and record.student.grade_id != scope["grade_id"]:
                return jsonify({"status": "error", "message": "无权访问"}), 403

        return jsonify({
            "status": "success",
            "type": "psych",
            "data": json.loads(record.comfort_script_json) if record.comfort_script_json else {},
            "meta": {
                "id": record.id,
                "student_name": record.student.name if record.student else "",
                "class_name": record.student.class_.name if record.student and record.student.class_ else "",
                "created_at": record.created_at.isoformat() if record.created_at else "",
                "creator_name": record.creator.display_name if record.creator else "",
            }
        })

    else:
        return jsonify({"status": "error", "message": "未知记录类型"}), 400
