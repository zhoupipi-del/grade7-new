"""
Psych Screening 业务逻辑层

核心引擎:
  1. MSSMHS-55 自动评分 + 风险定级
  2. 问卷→评估自动同步 (含状态机守卫)
  3. 十维度雷达图聚合
  4. DeepSeek AI 宏观分析白皮书
  5. 干预追踪全生命周期
  6. 统计仪表盘
"""

import json
import logging
import os
from datetime import date, datetime

import httpx
from core.db_utils import require_db_url
from core.event_bus import EventBus
from core.models import Class, Student, get_local_now
from modules.psych_screening.models import (
    InterventionRecord,
    MentalHealthAssessment,
    MentalHealthQuestion,
    PsychSurvey,
)

# risk_models 的 PsychSurvey 使用 dimension_scores (JSON) 而非 dimension_scores (Text)
# MentalHealthAssessment 使用 Integer total_score 和 uppercase status
from modules.psych_screening.schemas import MSSMHS_DIMENSIONS
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)

# ── DeepSeek 配置 ──
LLM_API_URL = os.getenv("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")


# ═══════════════════════════════════════════════════════════════
# MSSMHS-55 量表常量
# ═══════════════════════════════════════════════════════════════

MSSMHS_MAX_PER_DIM = 30  # 每维度满分 (6题 × 5分)
MSSMHS_MAX_TOTAL = 275  # 总分满分 (55题 × 5分)

# 评分：1=从无, 2=轻度, 3=中度, 4=偏重, 5=严重
MSSMHS_SCORE_LABELS = {
    1: "从无",
    2: "轻度",
    3: "中度",
    4: "偏重",
    5: "严重",
}


# ═══════════════════════════════════════════════════════════════
# MSSMHS-55 标准题目 (55 题 × 10 维度)
# ═══════════════════════════════════════════════════════════════

MSSMHS_QUESTIONS = [
    # 维度 1: 强迫症状 (题 1-6)
    ("强迫症状", "反复检查门窗/书包/作业，明知没必要却停不下来"),
    ("强迫症状", "头脑中反复出现一些无关紧要的想法或画面，难以摆脱"),
    ("强迫症状", "做事时必须遵循某种固定顺序，否则心慌不安"),
    ("强迫症状", "对自己的字迹/整洁度吹毛求疵，反复修改"),
    ("强迫症状", "计数强迫——下意识数楼层/台阶/路灯"),
    ("强迫症状", "明知某些想法不合理，但无法控制"),
    # 维度 2: 偏执 (题 7-12)
    ("偏执", "总觉得别人在背后议论自己"),
    ("偏执", "认为大多数人都不可信，防备心理过重"),
    ("偏执", "感觉别人针对你、故意让你难堪"),
    ("偏执", "别人对你态度稍有变化，就会反复揣测原因"),
    ("偏执", "总觉得别人占了便宜，自己吃了亏"),
    ("偏执", "对人不宽容，记仇，一件小事能记很久"),
    # 维度 3: 敌对 (题 13-18)
    ("敌对", "容易发脾气，控制不住怒气"),
    ("敌对", "有想打人或摔东西的冲动"),
    ("敌对", "经常与同学发生冲突或争吵"),
    ("敌对", "对老师/家长有抵触对抗心理"),
    ("敌对", "看到别人倒霉会幸灾乐祸"),
    ("敌对", "容易烦躁，一点小事就炸毛"),
    # 维度 4: 人际敏感 (题 19-24)
    ("人际敏感", "在人群中感到不自在，担心被人评价"),
    ("人际敏感", "觉得别人不理解你，没有真正懂你的人"),
    ("人际敏感", "与异性交往时感到紧张不自在"),
    ("人际敏感", "感到孤独，即使身边有人也觉得孤单"),
    ("人际敏感", "害怕被拒绝，不敢主动与人交往"),
    ("人际敏感", "太在意别人对自己的看法，活得很累"),
    # 维度 5: 抑郁 (题 25-30)
    ("抑郁", "感到生活没有意义，对未来不抱希望"),
    ("抑郁", "情绪低落，什么事都不想干"),
    ("抑郁", "食欲减退，体重明显下降"),
    ("抑郁", "入睡困难或早醒，睡眠质量很差"),
    ("抑郁", "感到自己毫无价值，是个失败者"),
    ("抑郁", "有过自伤或不想活的念头"),
    # 维度 6: 焦虑 (题 31-36)
    ("焦虑", "莫名心慌、心跳加快、手心出汗"),
    ("焦虑", "总担心考试考不好，晚上失眠"),
    ("焦虑", "一想到未来就心烦意乱"),
    ("焦虑", "坐立不安，没法安静下来"),
    ("焦虑", "总觉得会有不好的事发生"),
    ("焦虑", "紧张时胃痛、头痛、腹泻"),
    # 维度 7: 学习压力 (题 37-42)
    ("学习压力", "感到学习负担太重，喘不过气"),
    ("学习压力", "上课注意力难以集中，走神严重"),
    ("学习压力", "害怕老师提问，怕自己答不好被笑"),
    ("学习压力", "对学习提不起兴趣，一拿起书本就烦"),
    ("学习压力", "考试前紧张到手抖、大脑空白"),
    ("学习压力", "觉得无论如何努力都追不上别人"),
    # 维度 8: 适应不良 (题 43-48)
    ("适应不良", "不适应学校作息时间，总是睡不够"),
    ("适应不良", "不适应老师的教学方式，学不进去"),
    ("适应不良", "不喜欢现在的班级，融不进去"),
    ("适应不良", "对学校环境感到不舒适"),
    ("适应不良", "想转学或换班，不想待在现在的环境"),
    ("适应不良", "处理不好学习和生活之间的平衡"),
    # 维度 9: 情绪不平衡 (题 49-54)
    ("情绪不平衡", "情绪起伏很大，上一秒开心下一秒难过"),
    ("情绪不平衡", "会突然想大哭一场，不知道为什么"),
    ("情绪不平衡", "对家人忽冷忽热，态度反差大"),
    ("情绪不平衡", "有时很兴奋话很多，有时一句话不想说"),
    ("情绪不平衡", "容易受别人情绪影响，别人不高兴你也不高兴"),
    ("情绪不平衡", "不能很好地控制自己的情绪"),
    # 维度 10: 心理不平衡 (题 55-60 → 实际为 55 题，取前 6 维度的第 54 题结束)
    # 实际上 MSSMHS-55 每个维度 6 题，但最后一维度只有 4 题
    ("心理不平衡", "觉得别人什么都好，自己什么都不如人"),
    ("心理不平衡", "对别人比自己强感到不舒服"),
    ("心理不平衡", "觉得命运对自己不公平"),
    ("心理不平衡", "看到家庭条件好的同学会心生羡慕甚至嫉妒"),
    ("心理不平衡", "经常拿自己和别人比较，越比越难受"),
    ("心理不平衡", "认为自己的努力得不到应有的回报"),
]


# ═══════════════════════════════════════════════════════════════
# 1. 种子数据 — MSSMHS-55 题目库初始化
# ═══════════════════════════════════════════════════════════════


async def seed_mssmhs_questions(db: AsyncSession, school_id: int) -> int:
    """
    幂等初始化 MSSMHS-55 题目库。
    返回插入/更新的题目数量。
    """
    inserted = 0
    for idx, (dimension, text) in enumerate(MSSMHS_QUESTIONS):
        question_no = idx + 1
        # 检查是否已存在
        existing = await db.execute(
            select(MentalHealthQuestion).where(
                MentalHealthQuestion.school_id == school_id,
                MentalHealthQuestion.scale_name == "MSSMHS-55",
                MentalHealthQuestion.question_no == question_no,
            )
        )
        if existing.scalar_one_or_none():
            continue

        q = MentalHealthQuestion(
            school_id=school_id,
            scale_name="MSSMHS-55",
            dimension=dimension,
            question_no=question_no,
            question_text=text,
            option_type="likert5",
            reverse_scoring=False,
            sort_order=question_no,
            is_active=True,
        )
        db.add(q)
        inserted += 1

    if inserted > 0:
        await db.commit()
        logger.info(
            f"[psych_screening] Seeded {inserted} MSSMHS-55 questions for school {school_id}"
        )

    return inserted


# ═══════════════════════════════════════════════════════════════
# 2. 评分引擎 — 计算总分 + 维度分 + 风险定级
# ═══════════════════════════════════════════════════════════════


def calculate_scores(answers: list[dict]) -> dict:
    """
    根据答案列表计算:
      - total_score: 总分
      - dimensions: 10 维度分数字典
      - risk_level: low / medium / high
      - factor_triggered: 是否有维度均分 ≥ 3.0
    """
    # 按题号分组 → 维度映射
    dim_scores = {d: [] for d in MSSMHS_DIMENSIONS}
    for item in answers:
        qno = item.get("question_no", 0)
        score = item.get("score", 1)
        dim_idx = (qno - 1) // 6  # 每 6 题一个维度
        if 0 <= dim_idx < len(MSSMHS_DIMENSIONS):
            dim_scores[MSSMHS_DIMENSIONS[dim_idx]].append(score)

    total_score = sum(item.get("score", 1) for item in answers)
    dimensions = {d: sum(scores) for d, scores in dim_scores.items()}

    # 风险定级
    if total_score >= 160:
        risk_level = "high"
    elif total_score >= 120:
        risk_level = "medium"
    else:
        risk_level = "low"

    # 因子触发 (维度的均分达标)
    factor_triggered = False
    for d in MSSMHS_DIMENSIONS:
        scores = dim_scores[d]
        if scores and (sum(scores) / len(scores)) >= 3.0:
            factor_triggered = True
            break

    return {
        "total_score": total_score,
        "dimensions": dimensions,
        "risk_level": risk_level,
        "factor_triggered": factor_triggered,
    }


# ═══════════════════════════════════════════════════════════════
# 3. 问卷提交 + 自动评估同步
# ═══════════════════════════════════════════════════════════════


async def submit_survey(
    db: AsyncSession,
    student_id: int,
    school_id: int,
    answers: list[dict],
    survey_type: str = "MSSMHS-55",
) -> dict:
    """
    问卷提交全流程:
      1. 评分计算
      2. 落盘 PsychSurvey
      3. 中高风险 (≥120) 自动创建 MentalHealthAssessment
      4. CEP 风险升级检测 → ActiveCompositeAlert + SSE 弹窗
    """
    # 1. 评分
    result = calculate_scores(answers)

    # 2. 获取学生信息
    student = await db.execute(
        select(Student).where(
            Student.id == student_id,
            Student.school_id == school_id,
        )
    )
    student = student.scalar_one_or_none()
    if not student:
        raise ValueError(f"Student {student_id} not found")

    # ── CEP: 查询前次风险等级，用于升级检测 ──
    prev_risk = None
    prev_assessment_result = await db.execute(
        select(MentalHealthAssessment.risk_level)
        .where(
            MentalHealthAssessment.student_id == student_id,
            MentalHealthAssessment.school_id == school_id,
            MentalHealthAssessment.scale_name == "MSSMHS-55",
        )
        .order_by(MentalHealthAssessment.created_at.desc())
        .limit(1)
    )
    prev_row = prev_assessment_result.first()
    if prev_row:
        prev_risk = prev_row[0]

    # 3. 落盘问卷
    survey = PsychSurvey(
        school_id=school_id,
        student_id=student_id,
        class_id=student.class_id,
        grade_id=student.grade_id,
        survey_type=survey_type,
        answers_json=json.dumps(answers, ensure_ascii=False),
        total_score=result["total_score"],
        dimension_scores={"dimensions": result["dimensions"]},
        is_valid=True,
        verify_status="VERIFIED",
        completed_at=get_local_now(),
    )
    db.add(survey)
    await db.flush()

    # 4. 中高风险自动创建评估
    assessment_id = None
    risk_level = result["risk_level"]
    if result["total_score"] >= 120:
        assessment = await _auto_create_assessment(
            db,
            student,
            result["total_score"],
            result["dimensions"],
            risk_level,
            school_id,
            survey.id,
        )
        if assessment:
            assessment_id = assessment.id

    await db.commit()

    # ── EventBus: 心理风险变更事件泵入成长时间线 ──
    EventBus().publish(
        "psych.risk_changed",
        {
            "school_id": school_id,
            "student_id": student_id,
            "previous_level": prev_risk,
            "current_level": risk_level,
            "total_score": result["total_score"],
            "source": "psych_screening",
            "trigger": "submit_survey",
            "survey_id": survey.id,
            "occurred_at": get_local_now().isoformat(),
        },
    )

    # ── CEP 风险升级检测: 后台异步，不阻塞提交返回 ──
    new_risk = risk_level
    if _is_risk_escalation(prev_risk, new_risk):
        import asyncio

        asyncio.create_task(
            _cep_psych_risk_escalation(
                student_id=student_id,
                school_id=school_id,
                student_name=student.name,
                class_id=student.class_id,
                prev_risk=prev_risk,
                new_risk=new_risk,
                total_score=result["total_score"],
                survey_id=survey.id,
            )
        )
        logger.info(
            "[CEP-PSYCH] 风险升级检测触发 | student=%s %s→%s score=%s",
            student_id,
            prev_risk,
            new_risk,
            result["total_score"],
        )

    return {
        "status": "ok",
        "survey_id": survey.id,
        "total_score": result["total_score"],
        "risk_level": risk_level,
        "assessment_id": assessment_id,
        "message": (
            f"MSSMHS-55 筛查总分 {result['total_score']}，"
            f"风险等级: {'⚠️高风险' if risk_level == 'high' else '⚡中风险' if risk_level == 'medium' else '✅低风险'}"
        ),
    }


def _is_risk_escalation(prev: str | None, new: str) -> bool:
    """判断心理风险是否升级 (low→medium, low→high, medium→high)"""
    if not prev:
        return new in ("medium", "high")  # 首次筛查即中高风险
    risk_order = {"low": 0, "medium": 1, "high": 2}
    prev_val = risk_order.get(prev, -1)
    new_val = risk_order.get(new, -1)
    return new_val > prev_val


async def _cep_psych_risk_escalation(
    student_id: int,
    school_id: int,
    student_name: str,
    class_id: int | None,
    prev_risk: str | None,
    new_risk: str,
    total_score: float,
    survey_id: int,
) -> None:
    """
    CEP 心理风险升级 → 创建 ActiveCompositeAlert + Redis PUBLISH 弹窗

    独立 async session，不阻塞主事务。
    """
    import json as _json
    from datetime import datetime as _dt

    try:
        from core.redis_client import get_redis

        # 独立引擎 (安全: 从环境变量读取，无硬编码回退)
        _DB_URL = require_db_url()
        _engine = create_async_engine(_DB_URL, pool_pre_ping=True, pool_recycle=300, pool_size=2)
        _factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

        async with _factory() as db:
            from modules.growth.models import ActiveCompositeAlert

            risk_labels = {"low": "低风险", "medium": "中风险", "high": "高风险"}
            prev_label = risk_labels.get(prev_risk, "未知") if prev_risk else "首次筛查"
            new_label = risk_labels.get(new_risk, new_risk)

            # ── Wings 3.2: 分布式冷却锁 — 3天内同一学生不重复告警 ──
            COOLDOWN_TTL = 259_200  # 3 天
            redis = get_redis()
            if redis:
                cooldown_key = f"wings:cep:lock:psych_escalation:{student_id}"
                try:
                    acquired = await redis.set(cooldown_key, "1", ex=COOLDOWN_TTL, nx=True)
                except Exception:
                    acquired = False  # Redis 异常 → 放行（宁重复不丢失）
                if not acquired:
                    logger.info(
                        "[CEP-PSYCH] 冷却锁未获取, 3天内已触发过 | student=%s",
                        student_id,
                    )
                    return

            title = f"心理风险升级: {student_name} {prev_label}→{new_label} (MSSMHS-55: {total_score}分)"

            meta = _json.dumps(
                {
                    "module": "psych_screening",
                    "alert_source": "PSYCH_RISK_ESCALATION",
                    "student_id": student_id,
                    "student_name": student_name,
                    "class_id": class_id,
                    "prev_risk": prev_risk,
                    "new_risk": new_risk,
                    "total_score": total_score,
                    "survey_id": survey_id,
                    "risk_jump": f"{prev_risk}→{new_risk}",
                    "triggered_at": _dt.utcnow().isoformat(),
                },
                ensure_ascii=False,
                default=str,
            )

            alert = ActiveCompositeAlert(
                school_id=school_id,
                student_id=student_id,
                alert_type="PSYCH_RISK_ESCALATION",
                title=title[:200],
                reason_meta=meta,
                ai_prescription=(
                    f"## 心理风险升级预警\n\n"
                    f"**学生**: {student_name}\n"
                    f"**风险变化**: {prev_label} → {new_label}\n"
                    f"**MSSMHS-55 总分**: {total_score}\n\n"
                    f"### 处置建议\n"
                    f"1. 班主任立即约谈学生，了解近期心理状态变化\n"
                    f"2. 心理老师安排一对一访谈评估\n"
                    f"3. 评估是否需要家长联动干预\n"
                    f"4. 持续追踪 2 周内情绪行为变化\n"
                    if new_risk == "high"
                    else (
                        f"## 心理风险等级变化提醒\n\n"
                        f"**学生**: {student_name}\n"
                        f"**风险变化**: {prev_label} → {new_label}\n"
                        f"**MSSMHS-55 总分**: {total_score}\n\n"
                        f"### 处置建议\n"
                        f"1. 班主任关注学生日常情绪行为表现\n"
                        f"2. 择机与学生谈心，了解是否有压力源\n"
                        f"3. 观察 1-2 周，必要时安排心理面谈\n"
                    )
                ),
                is_resolved=False,
            )
            db.add(alert)
            await db.commit()
            await db.refresh(alert)

            logger.info(
                "[CEP-PSYCH] ActiveCompositeAlert 已创建 | alert_id=%s student=%s",
                alert.id,
                student_id,
            )

            # Redis PUBLISH 弹窗
            redis = get_redis()
            if redis:
                popup_data = {
                    "type": "composite_alert",
                    "alert_type": "PSYCH_RISK_ESCALATION",
                    "school_id": school_id,
                    "student_id": student_id,
                    "alert_id": alert.id,
                    "title": f"⚠️ 心理风险升级: {student_name}",
                    "summary": f"MSSMHS-55 筛查 {prev_label}→{new_label}，总分 {total_score}",
                    "risk_jump": f"{prev_risk}→{new_risk}",
                    "created_at": _dt.utcnow().isoformat(),
                }
                await redis.publish(
                    "wings:notifications:popup",
                    _json.dumps(popup_data, ensure_ascii=False),
                )
                logger.info("[CEP-PSYCH] SSE弹窗已广播 | student=%s", student_id)

    except Exception as e:
        logger.error("[CEP-PSYCH] 风险升级处理失败: %s", e, exc_info=True)


async def _auto_create_assessment(
    db: AsyncSession,
    student: Student,
    total_score: float,
    dimensions: dict,
    risk_level: str,
    school_id: int,
    survey_id: int = None,
) -> MentalHealthAssessment | None:
    """幂等创建 (或更新) 心理健康评估档案"""
    # 检查是否已存在同一问卷的评估
    existing = await db.execute(
        select(MentalHealthAssessment).where(
            MentalHealthAssessment.student_id == student.id,
            MentalHealthAssessment.scale_name == "MSSMHS-55",
            MentalHealthAssessment.assessment_type == "questionnaire",
            MentalHealthAssessment.school_id == school_id,
        )
    )
    existing = existing.scalar_one_or_none()

    if existing:
        existing.total_score = total_score
        existing.risk_level = risk_level
        existing.dimension_scores = {"dimensions": dimensions}
        existing.conclusion = (
            f"MSSMHS-55 心理健康筛查总分 {total_score}，"
            f"评定为 {'⚠️高风险 (≥160分)' if risk_level == 'high' else '⚡中风险 (120-159分)' if risk_level == 'medium' else '✅低风险 (<120分)'}"
        )
        existing.need_intervention = risk_level in ("high", "medium")
        existing.updated_at = get_local_now()
        await db.flush()
        return existing

    # 新建评估
    assessment = MentalHealthAssessment(
        school_id=school_id,
        student_id=student.id,
        class_id=student.class_id,
        grade_id=student.grade_id,
        assessment_type="questionnaire",
        scale_name="MSSMHS-55",
        total_score=int(total_score),
        risk_level=risk_level,
        dimension_scores={"dimensions": dimensions},
        assessment_date=date.today(),
        conclusion=(
            f"MSSMHS-55 心理健康筛查总分 {total_score}，"
            f"评定为 {'⚠️高风险 (≥160分)' if risk_level == 'high' else '⚡中风险 (120-159分)' if risk_level == 'medium' else '✅低风险 (<120分)'}"
        ),
        recommendations="建议关注学生心理状态，结合日常表现综合研判，必要时安排专业心理咨询",
        need_intervention=risk_level in ("high", "medium"),
        intervention_plan="由班主任持续关注，心理老师定期回访" if risk_level == "high" else None,
        assessed_by=1,  # 系统自动创建
        status="DRAFT",
    )
    db.add(assessment)
    await db.flush()
    return assessment


# ═══════════════════════════════════════════════════════════════
# 4. 评估 CRUD
# ═══════════════════════════════════════════════════════════════


async def list_assessments(
    db: AsyncSession,
    school_id: int,
    grade_id: int | None = None,
    class_id: int | None = None,
    student_id: int | None = None,
    risk_level: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """评估列表 + 统计"""
    conditions = [MentalHealthAssessment.school_id == school_id]
    if grade_id:
        conditions.append(MentalHealthAssessment.grade_id == grade_id)
    if class_id:
        conditions.append(MentalHealthAssessment.class_id == class_id)
    if student_id:
        conditions.append(MentalHealthAssessment.student_id == student_id)
    if risk_level:
        conditions.append(MentalHealthAssessment.risk_level == risk_level)

    # 总数
    count_stmt = select(func.count(MentalHealthAssessment.id)).where(*conditions)
    total = (await db.execute(count_stmt)).scalar()

    # 列表
    stmt = (
        select(MentalHealthAssessment)
        .where(*conditions)
        .order_by(MentalHealthAssessment.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    assessments = result.scalars().all()

    # 统计
    stats_stmt = select(
        func.count(MentalHealthAssessment.id),
        func.sum(func.if_(MentalHealthAssessment.risk_level == "high", 1, 0)),
        func.sum(func.if_(MentalHealthAssessment.risk_level == "medium", 1, 0)),
        func.sum(func.if_(MentalHealthAssessment.risk_level == "low", 1, 0)),
        func.sum(func.if_(MentalHealthAssessment.need_intervention, 1, 0)),
    ).where(*conditions)
    stats_result = await db.execute(stats_stmt)
    stats_row = stats_result.one()
    stats = {
        "total": stats_row[0] or 0,
        "high": stats_row[1] or 0,
        "medium": stats_row[2] or 0,
        "low": stats_row[3] or 0,
        "need_intervention": stats_row[4] or 0,
    }

    return {
        "assessments": assessments,
        "total": total,
        "stats": stats,
    }


async def create_assessment(
    db: AsyncSession,
    school_id: int,
    assessed_by: int,
    data: dict,
) -> MentalHealthAssessment:
    """手动创建评估"""
    student = await db.execute(
        select(Student).where(Student.id == data["student_id"], Student.school_id == school_id)
    )
    student = student.scalar_one_or_none()
    if not student:
        raise ValueError(f"Student {data['student_id']} not found")

    assessment = MentalHealthAssessment(
        school_id=school_id,
        student_id=student.id,
        class_id=student.class_id,
        grade_id=student.grade_id,
        assessment_type=data.get("assessment_type", "interview"),
        scale_name=data.get("scale_name"),
        conclusion=data.get("conclusion"),
        recommendations=data.get("recommendations"),
        need_intervention=data.get("need_intervention", False),
        intervention_plan=data.get("intervention_plan"),
        risk_level=data.get("risk_level", "low"),
        assessed_by=assessed_by,
        assessment_date=date.today(),
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)

    # ── EventBus: 心理评估创建 → 成长时间线 ──
    EventBus().publish(
        "psych.risk_changed",
        {
            "school_id": school_id,
            "student_id": assessment.student_id,
            "previous_level": None,
            "current_level": assessment.risk_level,
            "source": "psych_screening",
            "trigger": "create_assessment",
            "assessment_id": assessment.id,
            "occurred_at": get_local_now().isoformat(),
        },
    )

    return assessment


async def update_assessment(
    db: AsyncSession,
    assessment_id: int,
    data: dict,
) -> MentalHealthAssessment:
    """更新评估"""
    assessment = await db.execute(
        select(MentalHealthAssessment).where(MentalHealthAssessment.id == assessment_id)
    )
    assessment = assessment.scalar_one_or_none()
    if not assessment:
        raise ValueError(f"Assessment {assessment_id} not found")

    # 记录变更前的风险等级
    prev_risk_level = assessment.risk_level

    for field in [
        "assessment_type",
        "scale_name",
        "conclusion",
        "recommendations",
        "need_intervention",
        "intervention_plan",
        "risk_level",
        "status",
    ]:
        if field in data and data[field] is not None:
            setattr(assessment, field, data[field])

    assessment.updated_at = get_local_now()
    await db.commit()
    await db.refresh(assessment)

    # ── EventBus: 风险等级变更 → 成长时间线 ──
    new_risk = data.get("risk_level")
    if new_risk is not None and new_risk != prev_risk_level:
        EventBus().publish(
            "psych.risk_changed",
            {
                "school_id": assessment.school_id,
                "student_id": assessment.student_id,
                "previous_level": prev_risk_level,
                "current_level": new_risk,
                "source": "psych_screening",
                "trigger": "update_assessment",
                "assessment_id": assessment.id,
                "occurred_at": get_local_now().isoformat(),
            },
        )

    return assessment


async def delete_assessment(db: AsyncSession, assessment_id: int) -> bool:
    """删除评估"""
    assessment = await db.execute(
        select(MentalHealthAssessment).where(MentalHealthAssessment.id == assessment_id)
    )
    assessment = assessment.scalar_one_or_none()
    if not assessment:
        return False
    await db.delete(assessment)
    await db.commit()
    return True


# ═══════════════════════════════════════════════════════════════
# 5. 维度聚合 — 雷达图数据
# ═══════════════════════════════════════════════════════════════


async def get_dimension_aggregation(
    db: AsyncSession,
    school_id: int,
    grade_id: int | None = None,
    class_id: int | None = None,
) -> dict:
    """
    聚合 MSSMHS-55 全部有效问卷的 10 维度数据:
      - averages / maxes / counts
      - 各维度最高分学生
      - 风险分布 (含因子触发)
      - 班级对比 (年级/校级)
    """
    conditions = [
        PsychSurvey.school_id == school_id,
        PsychSurvey.survey_type == "MSSMHS-55",
        PsychSurvey.is_valid,
        PsychSurvey.verify_status == "VERIFIED",
        PsychSurvey.dimension_scores.isnot(None),
    ]
    if grade_id:
        conditions.append(PsychSurvey.grade_id == grade_id)
    if class_id:
        conditions.append(PsychSurvey.class_id == class_id)

    stmt = select(PsychSurvey).where(*conditions)
    result = await db.execute(stmt)
    surveys = result.scalars().all()

    if not surveys:
        return {
            "indicator": MSSMHS_DIMENSIONS,
            "max_per_dim": MSSMHS_MAX_PER_DIM,
            "average": [0] * len(MSSMHS_DIMENSIONS),
            "max": [0] * len(MSSMHS_DIMENSIONS),
            "count": 0,
            "top_students": [],
            "risk_distribution": {"high": 0, "medium": 0, "low": 0},
            "class_comparison": [],
        }

    # 批量加载学生和班级信息
    student_ids = list({s.student_id for s in surveys})
    students_result = await db.execute(select(Student).where(Student.id.in_(student_ids)))
    student_map = {s.id: s for s in students_result.scalars().all()}

    class_ids = list({s.class_id for s in surveys})
    classes_result = await db.execute(select(Class).where(Class.id.in_(class_ids)))
    class_map = {c.id: c for c in classes_result.scalars().all()}

    # 聚合
    dim_sums = dict.fromkeys(MSSMHS_DIMENSIONS, 0.0)
    dim_max = dict.fromkeys(MSSMHS_DIMENSIONS, 0.0)
    dim_max_students = dict.fromkeys(MSSMHS_DIMENSIONS)
    risk_dist = {"high": 0, "medium": 0, "low": 0}

    for survey in surveys:
        dims = _parse_dimensions(survey.dimension_scores)
        if not dims:
            continue

        stu = student_map.get(survey.student_id)
        stu_info = {"id": survey.student_id, "name": stu.name if stu else "Unknown"}
        cls = class_map.get(survey.class_id)
        if cls:
            stu_info["class_name"] = cls.name

        for dim_name in MSSMHS_DIMENSIONS:
            score = float(dims.get(dim_name, 0))
            dim_sums[dim_name] += score
            if score > dim_max[dim_name]:
                dim_max[dim_name] = score
                dim_max_students[dim_name] = stu_info

        # 风险分布 (双轨判定)
        total = survey.total_score or 0
        factor_triggered = any(float(dims.get(d, 0)) / 6 >= 3.0 for d in MSSMHS_DIMENSIONS)
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

    # 班级对比
    class_comparison = []
    if not class_id:  # 校级或年级视图
        class_dim_data = {}
        class_count = {}
        for survey in surveys:
            cid = survey.class_id
            if cid not in class_dim_data:
                class_dim_data[cid] = dict.fromkeys(MSSMHS_DIMENSIONS, 0.0)
                class_count[cid] = 0
            dims = _parse_dimensions(survey.dimension_scores)
            if not dims:
                continue
            class_count[cid] += 1
            for dim_name in MSSMHS_DIMENSIONS:
                class_dim_data[cid][dim_name] += float(dims.get(dim_name, 0))

        for cid, cnt in class_count.items():
            if cnt == 0:
                continue
            cls = class_map.get(cid)
            class_comparison.append(
                {
                    "class_id": cid,
                    "class_name": cls.name if cls else f"Class {cid}",
                    "count": cnt,
                    "averages": [round(class_dim_data[cid][d] / cnt, 2) for d in MSSMHS_DIMENSIONS],
                }
            )
        class_comparison.sort(key=lambda x: x["class_name"])

    return {
        "indicator": MSSMHS_DIMENSIONS,
        "max_per_dim": MSSMHS_MAX_PER_DIM,
        "average": averages,
        "max": maxes,
        "count": valid_count,
        "top_students": top_students,
        "risk_distribution": risk_dist,
        "class_comparison": class_comparison,
    }


def _parse_dimensions(dim_data) -> dict | None:
    """安全解析 dimension_scores (兼容两种格式)

    Format A (新): {"dimensions": {"强迫症状": 18, "偏执": 12, ...}}
    Format B (旧 ETL): {"anxiety_score": 1.0, "paranoid_score": 1.0, ...}
    """
    if not dim_data:
        return None
    if isinstance(dim_data, dict):
        # Format A: 标准格式
        if "dimensions" in dim_data:
            return dim_data["dimensions"]
        # Format B: 旧 ETL 英文 Key
        return _convert_english_keys(dim_data)
    try:
        data = json.loads(dim_data)
        if isinstance(data, dict):
            if "dimensions" in data:
                return data["dimensions"]
            return _convert_english_keys(data)
    except (json.JSONDecodeError, TypeError):
        return None
    return None


# ETL 英文 Key → 中文维度名映射
_ENGLISH_KEY_MAP = {
    "obsessive_compulsive_score": "强迫症状",
    "paranoid_score": "偏执",
    "hostility_score": "敌对",
    "interpersonal_sensitivity_score": "人际敏感",
    "depression_score": "抑郁",
    "anxiety_score": "焦虑",
    "learning_pressure_score": "学习压力",
    "maladjustment_score": "适应不良",
    "emotional_imbalance_score": "情绪不平衡",
    "psychological_imbalance_score": "心理不平衡",
}


def _convert_english_keys(data: dict) -> dict:
    """将 ETL 英文 Key 转为中文维度名"""
    result = {}
    for eng_key, cn_key in _ENGLISH_KEY_MAP.items():
        if eng_key in data:
            # ETL 数据是按项均分 (0-5 scale), 需要 ×6 转换为维度总分
            val = data[eng_key]
            result[cn_key] = round(float(val) * 6, 2) if val else 0
    return result


# ═══════════════════════════════════════════════════════════════
# 6. AI 宏观分析 — DeepSeek 生成白皮书
# ═══════════════════════════════════════════════════════════════


async def run_ai_analysis(
    db: AsyncSession,
    school_id: int,
    grade_id: int | None = None,
    class_id: int | None = None,
) -> dict:
    """
    调用 DeepSeek 生成心理健康宏观分析白皮书。
    基于 MSSMHS-55 全量问卷数据的统计摘要和维度均分。
    """
    conditions = [
        PsychSurvey.school_id == school_id,
        PsychSurvey.survey_type == "MSSMHS-55",
        PsychSurvey.is_valid,
        PsychSurvey.verify_status == "VERIFIED",
        PsychSurvey.dimension_scores.isnot(None),
    ]
    if grade_id:
        conditions.append(PsychSurvey.grade_id == grade_id)
    if class_id:
        conditions.append(PsychSurvey.class_id == class_id)

    stmt = select(PsychSurvey).where(*conditions)
    result = await db.execute(stmt)
    surveys = result.scalars().all()

    if not surveys:
        return {"error": "暂无有效问卷数据", "report": None}

    # 聚合统计
    dim_sums = dict.fromkeys(MSSMHS_DIMENSIONS, 0.0)
    dim_max = dict.fromkeys(MSSMHS_DIMENSIONS, 0.0)
    valid_count = len(surveys)
    total_scores = []
    risk_dist = {"high": 0, "medium": 0, "low": 0}

    for survey in surveys:
        dims = _parse_dimensions(survey.dimension_scores)
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

    data_summary = (
        f"## 梨江中学 MSSMHS-55 心理筛查数据摘要\n\n"
        f"- 有效问卷数: {valid_count} 份\n"
        f"- 总分均值: {avg_total} / {MSSMHS_MAX_TOTAL}\n"
        f"- 总分范围: {min_total} ~ {max_total}\n"
        f"- 风险分布: 高风险 {risk_dist['high']} 人 ({risk_dist['high'] / valid_count * 100:.1f}%), "
        f"中风险 {risk_dist['medium']} 人 ({risk_dist['medium'] / valid_count * 100:.1f}%), "
        f"低风险 {risk_dist['low']} 人 ({risk_dist['low'] / valid_count * 100:.1f}%)\n\n"
        f"### 各维度均分（满分 {MSSMHS_MAX_PER_DIM} 分）\n"
    )
    for dim_name in MSSMHS_DIMENSIONS:
        avg = dim_avg[dim_name]
        pct = avg / MSSMHS_MAX_PER_DIM * 100
        level = "偏高" if pct > 50 else "中等" if pct > 30 else "正常"
        data_summary += f"- {dim_name}: {avg} ({level}, 占满分 {pct:.1f}%)\n"

    data_summary += "### 各维度最高分\n"
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
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                LLM_API_URL,
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": data_summary},
                    ],
                    "temperature": 0.5,
                    "max_tokens": 4096,
                },
            )
            if resp.status_code == 200:
                body = resp.json()
                report = body["choices"][0]["message"]["content"].strip()
                return {"report": report, "error": None}
            else:
                return {"error": f"LLM API 返回 {resp.status_code}", "report": None}
    except Exception as e:
        logger.warning(f"[psych_screening] AI analysis failed: {e}")
        return {"error": f"AI 分析生成失败: {str(e)}", "report": None}


# ═══════════════════════════════════════════════════════════════
# 7. 问卷 → 评估批量同步
# ═══════════════════════════════════════════════════════════════


async def sync_surveys_to_assessments(
    db: AsyncSession,
    school_id: int,
    grade_id: int | None = None,
) -> dict:
    """
    扫描所有 MSSMHS-55 中高风险问卷，自动创建/更新心理健康评估。
    幂等：同一学生只保留一份 questionnaire 类型的评估。
    """
    conditions = [
        PsychSurvey.school_id == school_id,
        PsychSurvey.survey_type == "MSSMHS-55",
        PsychSurvey.is_valid,
        PsychSurvey.verify_status == "VERIFIED",
        PsychSurvey.total_score >= 120,
    ]
    if grade_id:
        conditions.append(PsychSurvey.grade_id == grade_id)

    stmt = select(PsychSurvey).where(*conditions)
    result = await db.execute(stmt)
    surveys = result.scalars().all()

    created = 0
    updated = 0
    for survey in surveys:
        student_result = await db.execute(select(Student).where(Student.id == survey.student_id))
        student = student_result.scalar_one_or_none()
        if not student:
            continue

        dimensions = _parse_dimensions(survey.dimension_scores) or {}
        risk_level = "high" if (survey.total_score or 0) >= 160 else "medium"

        # 判断是新建还是更新
        existing = await db.execute(
            select(MentalHealthAssessment).where(
                MentalHealthAssessment.student_id == student.id,
                MentalHealthAssessment.scale_name == "MSSMHS-55",
                MentalHealthAssessment.assessment_type == "questionnaire",
                MentalHealthAssessment.school_id == school_id,
            )
        )
        is_new = existing.scalar_one_or_none() is None

        assessment = await _auto_create_assessment(
            db,
            student,
            survey.total_score,
            dimensions,
            risk_level,
            school_id,
        )
        if assessment:
            if is_new:
                created += 1
            else:
                updated += 1

    await db.commit()
    return {
        "status": "ok",
        "created": created,
        "updated": updated,
        "total_processed": created + updated,
        "message": f"同步完成：新增 {created} 条，更新 {updated} 条",
    }


# ═══════════════════════════════════════════════════════════════
# 8. 干预追踪 CRUD
# ═══════════════════════════════════════════════════════════════


async def list_interventions(
    db: AsyncSession,
    school_id: int,
    grade_id: int | None = None,
    class_id: int | None = None,
    student_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """干预记录列表 + 统计"""
    conditions = [InterventionRecord.school_id == school_id]
    if grade_id:
        conditions.append(
            InterventionRecord.student_id.in_(
                select(Student.id).where(
                    Student.grade_id == grade_id, Student.school_id == school_id
                )
            )
        )
    if class_id:
        conditions.append(
            InterventionRecord.student_id.in_(
                select(Student.id).where(
                    Student.class_id == class_id, Student.school_id == school_id
                )
            )
        )
    if student_id:
        conditions.append(InterventionRecord.student_id == student_id)
    if status:
        conditions.append(InterventionRecord.status == status)

    count_stmt = select(func.count(InterventionRecord.id)).where(*conditions)
    total = (await db.execute(count_stmt)).scalar()

    stmt = (
        select(InterventionRecord)
        .where(*conditions)
        .order_by(InterventionRecord.intervention_date.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()

    # 统计
    all_conditions = [InterventionRecord.school_id == school_id]
    if grade_id:
        all_conditions.append(
            InterventionRecord.student_id.in_(
                select(Student.id).where(
                    Student.grade_id == grade_id, Student.school_id == school_id
                )
            )
        )
    if class_id:
        all_conditions.append(
            InterventionRecord.student_id.in_(
                select(Student.id).where(
                    Student.class_id == class_id, Student.school_id == school_id
                )
            )
        )

    stats_stmt = select(
        func.count(InterventionRecord.id),
        func.sum(func.if_(InterventionRecord.status == "tracking", 1, 0)),
        func.sum(func.if_(InterventionRecord.status == "completed", 1, 0)),
        func.sum(func.if_(InterventionRecord.effect_rating.in_(["显著好转", "略有好转"]), 1, 0)),
    ).where(*all_conditions)
    stats_result = await db.execute(stats_stmt)
    stats_row = stats_result.one()
    stats = {
        "total": stats_row[0] or 0,
        "tracking": stats_row[1] or 0,
        "completed": stats_row[2] or 0,
        "effective": stats_row[3] or 0,
    }

    return {"records": records, "total": total, "stats": stats}


async def create_intervention(
    db: AsyncSession,
    school_id: int,
    teacher_id: int,
    data: dict,
) -> InterventionRecord:
    """创建干预记录"""
    student_result = await db.execute(
        select(Student).where(Student.id == data["student_id"], Student.school_id == school_id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise ValueError(f"Student {data['student_id']} not found")

    # 确定 mh_risk_before
    mh_risk_before = None
    assessment_id = data.get("assessment_id")
    if assessment_id:
        assessment = await db.execute(
            select(MentalHealthAssessment).where(MentalHealthAssessment.id == assessment_id)
        )
        assessment = assessment.scalar_one_or_none()
        if assessment:
            mh_risk_before = assessment.risk_level

    if not mh_risk_before:
        latest = await db.execute(
            select(MentalHealthAssessment)
            .where(
                MentalHealthAssessment.student_id == data["student_id"],
                MentalHealthAssessment.school_id == school_id,
            )
            .order_by(MentalHealthAssessment.created_at.desc())
        )
        latest = latest.scalar_one_or_none()
        if latest:
            assessment_id = latest.id
            mh_risk_before = latest.risk_level

    # 解析日期
    intervention_date = _parse_date(data.get("intervention_date"))
    follow_up_date = _parse_date(data.get("follow_up_date"))

    rec = InterventionRecord(
        school_id=school_id,
        student_id=data["student_id"],
        teacher_id=teacher_id,
        assessment_id=assessment_id,
        mh_risk_before=mh_risk_before,
        intervention_type=data.get("intervention_type", "心理谈话"),
        notes=data.get("notes"),
        parent_feedback=data.get("parent_feedback"),
        intervention_date=intervention_date,
        follow_up_date=follow_up_date,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec


async def followup_intervention(
    db: AsyncSession,
    intervention_id: int,
    data: dict,
) -> InterventionRecord:
    """随访更新干预记录"""
    rec = await db.execute(
        select(InterventionRecord).where(InterventionRecord.id == intervention_id)
    )
    rec = rec.scalar_one_or_none()
    if not rec:
        raise ValueError(f"Intervention {intervention_id} not found")

    rec.effect_rating = data.get("effect_rating", rec.effect_rating)
    rec.follow_up_notes = data.get("follow_up_notes", rec.follow_up_notes)
    rec.parent_feedback = data.get("parent_feedback") or rec.parent_feedback
    rec.follow_up_done = True
    rec.follow_up_date = date.today()
    rec.mh_risk_after = data.get("mh_risk_after", rec.mh_risk_after)
    rec.status = "completed"
    rec.updated_at = get_local_now()
    await db.commit()
    await db.refresh(rec)

    # ── EventBus: 干预完成 → 成长时间线 ──
    EventBus().publish(
        "psych.risk_changed",
        {
            "school_id": rec.school_id,
            "student_id": rec.student_id,
            "previous_level": rec.mh_risk_before,
            "current_level": rec.mh_risk_after,
            "source": "psych_screening",
            "trigger": "followup_intervention",
            "intervention_id": rec.id,
            "effect_rating": rec.effect_rating,
            "occurred_at": get_local_now().isoformat(),
        },
    )

    return rec


async def get_intervention_timeline(
    db: AsyncSession,
    student_id: int,
    school_id: int,
) -> dict:
    """学生干预时间线"""
    student = await db.execute(
        select(Student).where(Student.id == student_id, Student.school_id == school_id)
    )
    student = student.scalar_one_or_none()
    if not student:
        raise ValueError(f"Student {student_id} not found")

    records = await db.execute(
        select(InterventionRecord)
        .where(
            InterventionRecord.student_id == student_id,
            InterventionRecord.school_id == school_id,
        )
        .order_by(InterventionRecord.intervention_date.asc())
    )
    records = records.scalars().all()

    latest_assessment = await db.execute(
        select(MentalHealthAssessment)
        .where(
            MentalHealthAssessment.student_id == student_id,
            MentalHealthAssessment.school_id == school_id,
        )
        .order_by(MentalHealthAssessment.created_at.desc())
    )
    latest_assessment = latest_assessment.scalar_one_or_none()

    # 风险变化趋势
    risk_order = {"low": 1, "medium": 2, "high": 3}
    risk_trend = []
    for r in records:
        if r.mh_risk_before:
            risk_trend.append(
                {
                    "date": str(r.intervention_date) if r.intervention_date else "",
                    "risk": r.mh_risk_before,
                    "type": "干预前",
                    "label": r.intervention_type,
                }
            )
        if r.mh_risk_after and r.follow_up_done:
            risk_trend.append(
                {
                    "date": str(r.follow_up_date) if r.follow_up_date else "",
                    "risk": r.mh_risk_after,
                    "type": "随访后",
                    "label": r.effect_rating or "",
                }
            )

    risk_trend.sort(key=lambda x: (x["date"], risk_order.get(x["risk"], 0)))

    return {
        "student_id": student_id,
        "student_name": student.name,
        "records": records,
        "risk_trend": risk_trend,
        "latest_assessment": latest_assessment,
    }


# ═══════════════════════════════════════════════════════════════
# 9. 学生搜索 (供干预创建使用)
# ═══════════════════════════════════════════════════════════════


async def search_students(
    db: AsyncSession,
    school_id: int,
    grade_id: int | None = None,
    class_id: int | None = None,
    keyword: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """按权限 scope 搜索学生"""
    conditions = [Student.school_id == school_id, Student.is_active]
    if grade_id:
        conditions.append(Student.grade_id == grade_id)
    if class_id:
        conditions.append(Student.class_id == class_id)
    if keyword:
        conditions.append(Student.name.contains(keyword))

    stmt = select(Student).where(*conditions).order_by(Student.class_id, Student.name).limit(limit)
    result = await db.execute(stmt)
    students = result.scalars().all()

    output = []
    for s in students:
        # 取最新 MH 评估
        latest = await db.execute(
            select(MentalHealthAssessment)
            .where(
                MentalHealthAssessment.student_id == s.id,
                MentalHealthAssessment.school_id == school_id,
            )
            .order_by(MentalHealthAssessment.created_at.desc())
        )
        latest = latest.scalar_one_or_none()

        output.append(
            {
                "id": s.id,
                "name": s.name,
                "class_name": s.class_.name if s.class_ else "",
                "risk_level": latest.risk_level if latest else None,
                "total_score": latest.total_score if latest else None,
                "assessment_id": latest.id if latest else None,
            }
        )

    return output


# ═══════════════════════════════════════════════════════════════
# 10. 统计仪表盘
# ═══════════════════════════════════════════════════════════════


async def get_dashboard_stats(
    db: AsyncSession,
    school_id: int,
    grade_id: int | None = None,
    class_id: int | None = None,
) -> dict:
    """
    心理筛查仪表盘聚合统计:
      - 问卷概况
      - 风险分布
      - 评估概况
      - 干预概况
      - 维度预警
    """
    # 问卷统计
    survey_conds = [
        PsychSurvey.school_id == school_id,
        PsychSurvey.is_valid,
        PsychSurvey.verify_status == "VERIFIED",
    ]
    if grade_id:
        survey_conds.append(PsychSurvey.grade_id == grade_id)
    if class_id:
        survey_conds.append(PsychSurvey.class_id == class_id)

    mssmhs_count = (
        await db.execute(
            select(func.count(PsychSurvey.id)).where(
                *survey_conds, PsychSurvey.survey_type == "MSSMHS-55"
            )
        )
    ).scalar() or 0
    pce_count = (
        await db.execute(
            select(func.count(PsychSurvey.id)).where(
                *survey_conds, PsychSurvey.survey_type == "PCE-55"
            )
        )
    ).scalar() or 0

    # 风险分布
    mssmhs_conds = survey_conds + [PsychSurvey.survey_type == "MSSMHS-55"]
    risk_stmt = select(
        func.sum(func.if_(PsychSurvey.total_score >= 160, 1, 0)),
        func.sum(
            func.if_(and_(PsychSurvey.total_score >= 120, PsychSurvey.total_score < 160), 1, 0)
        ),
        func.sum(func.if_(PsychSurvey.total_score < 120, 1, 0)),
    ).where(*mssmhs_conds)
    risk_result = await db.execute(risk_stmt)
    risk_row = risk_result.one()

    # 评估统计
    assessment_conds = [MentalHealthAssessment.school_id == school_id]
    if grade_id:
        assessment_conds.append(MentalHealthAssessment.grade_id == grade_id)
    if class_id:
        assessment_conds.append(MentalHealthAssessment.class_id == class_id)

    assessment_stats = {
        "total": (
            await db.execute(select(func.count(MentalHealthAssessment.id)).where(*assessment_conds))
        ).scalar()
        or 0,
        "need_intervention": (
            await db.execute(
                select(func.count(MentalHealthAssessment.id)).where(
                    *assessment_conds, MentalHealthAssessment.need_intervention
                )
            )
        ).scalar()
        or 0,
    }

    # 干预统计
    intv_conds = [InterventionRecord.school_id == school_id]
    if grade_id:
        intv_conds.append(
            InterventionRecord.student_id.in_(
                select(Student.id).where(
                    Student.grade_id == grade_id, Student.school_id == school_id
                )
            )
        )
    if class_id:
        intv_conds.append(
            InterventionRecord.student_id.in_(
                select(Student.id).where(
                    Student.class_id == class_id, Student.school_id == school_id
                )
            )
        )

    intv_stats = {
        "total": (
            await db.execute(select(func.count(InterventionRecord.id)).where(*intv_conds))
        ).scalar()
        or 0,
        "tracking": (
            await db.execute(
                select(func.count(InterventionRecord.id)).where(
                    *intv_conds, InterventionRecord.status == "tracking"
                )
            )
        ).scalar()
        or 0,
        "completed": (
            await db.execute(
                select(func.count(InterventionRecord.id)).where(
                    *intv_conds, InterventionRecord.status == "completed"
                )
            )
        ).scalar()
        or 0,
    }

    # 维度预警 (从问卷聚合中快速获取)
    dim_alerts = []
    if mssmhs_count > 0:
        dim_data = await get_dimension_aggregation(db, school_id, grade_id, class_id)
        for i, dim_name in enumerate(MSSMHS_DIMENSIONS):
            avg = dim_data["average"][i]
            if avg > 15:  # 均分超过 50%
                dim_alerts.append(
                    {
                        "dimension": dim_name,
                        "average": avg,
                        "max": dim_data["max"][i],
                        "severity": "high" if avg > 20 else "medium",
                    }
                )
        dim_alerts.sort(key=lambda x: x["average"], reverse=True)

    return {
        "survey_stats": {
            "total": mssmhs_count + pce_count,
            "mssmhs_count": mssmhs_count,
            "pce_count": pce_count,
        },
        "risk_distribution": {
            "high": risk_row[0] or 0,
            "medium": risk_row[1] or 0,
            "low": risk_row[2] or 0,
        },
        "assessment_stats": assessment_stats,
        "intervention_stats": intv_stats,
        "dimension_alerts": dim_alerts,
    }


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════


def _parse_date(date_str: str | None) -> date | None:
    """安全解析日期字符串 YYYY-MM-DD"""
    if not date_str:
        return date.today()
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return date.today()
