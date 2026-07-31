"""
research_profile/services.py — 教师教研四维聚合引擎 (V3 融合版)

保留 V2 的高效聚合（union/json_length），加入四维0-100归一化评分。
"""

import logging

from core.models import Student, User

# 错题断层归因桥（精确优先 + 回退，跨模块只读聚合，不写库）
from modules.error_funnel.models import ErrorBookItem, KnowledgeGap
from modules.grades.models import GradeSubject
from modules.teacher_mgmt.models import TeacherSubject
from modules.timetable.models import TimetableScheduleInstance
from sqlalchemy import and_, func, literal, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ResearchActivityParticipant,
    ResearchClassObservation,
    ResearchLessonPlan,
    ResearchPlanReview,
    ResearchPlanVersion,
)

logger = logging.getLogger(__name__)


async def list_teachers(
    db: AsyncSession,
    school_id: int,
) -> list[dict]:
    """列出学校内活跃于教研模块的教师（含学科信息）"""
    s1 = select(ResearchLessonPlan.creator_id, ResearchLessonPlan.subject_code).where(
        ResearchLessonPlan.school_id == school_id
    )
    s2 = select(ResearchClassObservation.observer_id, literal(None).label("subject_code")).where(
        ResearchClassObservation.school_id == school_id
    )
    s3 = select(ResearchClassObservation.teacher_id, literal(None).label("subject_code")).where(
        ResearchClassObservation.school_id == school_id
    )
    s4 = select(ResearchActivityParticipant.user_id, literal(None).label("subject_code")).where(
        ResearchActivityParticipant.school_id == school_id
    )
    sub = union(s1, s2, s3, s4).subquery()

    stmt = (
        select(
            User.id.label("id"),
            User.display_name.label("real_name"),
            func.max(sub.c.subject_code).label("subject_code"),
        )
        .join(sub, User.id == sub.c.creator_id)
        .where(User.school_id == school_id)
        .group_by(User.id, User.display_name)
        .order_by(User.display_name)
    )
    result = await db.execute(stmt)
    return [dict(row._mapping) for row in result.all()]


# ═══════════════════════════════════════════════════
# 维度聚合辅助函数
# ═══════════════════════════════════════════════════


async def _dim1_prep(db: AsyncSession, teacher_id: int, school_id: int) -> dict:
    """维度1: 备课狂热度"""
    plans = (
        await db.execute(
            select(func.count(ResearchLessonPlan.id)).where(
                ResearchLessonPlan.creator_id == teacher_id,
                ResearchLessonPlan.school_id == school_id,
            )
        )
    ).scalar() or 0

    published = (
        await db.execute(
            select(func.count(ResearchLessonPlan.id)).where(
                ResearchLessonPlan.creator_id == teacher_id,
                ResearchLessonPlan.status == "PUBLISHED",
                ResearchLessonPlan.school_id == school_id,
            )
        )
    ).scalar() or 0

    versions = (
        await db.execute(
            select(func.count(ResearchPlanVersion.id)).where(
                ResearchPlanVersion.editor_id == teacher_id,
                ResearchPlanVersion.school_id == school_id,
            )
        )
    ).scalar() or 0

    return {"plans_count": plans, "published_count": published, "versions_count": versions}


async def _dim2_social(db: AsyncSession, teacher_id: int, school_id: int) -> dict:
    """维度2: 教研社交指数"""
    reviews = (
        await db.execute(
            select(func.count(ResearchPlanReview.id)).where(
                ResearchPlanReview.reviewer_id == teacher_id,
                ResearchPlanReview.school_id == school_id,
            )
        )
    ).scalar() or 0

    activities = (
        await db.execute(
            select(func.count(ResearchActivityParticipant.id)).where(
                ResearchActivityParticipant.user_id == teacher_id,
                ResearchActivityParticipant.school_id == school_id,
            )
        )
    ).scalar() or 0

    return {"comments_count": reviews, "activities_count": activities}


async def _dim3_observation(db: AsyncSession, teacher_id: int, school_id: int) -> dict:
    """维度3: 时空监理质感（V3.2 质+量双轨融合）"""
    obs_count = (
        await db.execute(
            select(func.count(ResearchClassObservation.id)).where(
                ResearchClassObservation.observer_id == teacher_id,
                ResearchClassObservation.school_id == school_id,
            )
        )
    ).scalar() or 0

    observed_count = (
        await db.execute(
            select(func.count(ResearchClassObservation.id)).where(
                ResearchClassObservation.teacher_id == teacher_id,
                ResearchClassObservation.school_id == school_id,
            )
        )
    ).scalar() or 0

    # 弹幕打点：MySQL JSON_LENGTH 聚合
    marks = (
        await db.execute(
            select(
                func.coalesce(
                    func.sum(func.json_length(ResearchClassObservation.timeline_comments)), 0
                )
            ).where(
                ResearchClassObservation.observer_id == teacher_id,
                ResearchClassObservation.school_id == school_id,
            )
        )
    ).scalar() or 0

    # ═══ V3.2 质量数据并网 ═══
    # 被听课质量：该教师授课时获得的平均得分率
    observed_avg = (
        await db.execute(
            select(func.round(func.avg(ResearchClassObservation.score_percentage), 1)).where(
                ResearchClassObservation.teacher_id == teacher_id,
                ResearchClassObservation.school_id == school_id,
                ResearchClassObservation.score_percentage.isnot(None),
            )
        )
    ).scalar()

    # 打分习惯：该教师作为听课人给出的平均分
    scoring_avg = (
        await db.execute(
            select(func.round(func.avg(ResearchClassObservation.score_percentage), 1)).where(
                ResearchClassObservation.observer_id == teacher_id,
                ResearchClassObservation.school_id == school_id,
                ResearchClassObservation.score_percentage.isnot(None),
            )
        )
    ).scalar()

    # 打分次数（用于判断是否有打分数据）
    scoring_count = (
        await db.execute(
            select(func.count(ResearchClassObservation.id)).where(
                ResearchClassObservation.observer_id == teacher_id,
                ResearchClassObservation.school_id == school_id,
                ResearchClassObservation.score_percentage.isnot(None),
            )
        )
    ).scalar() or 0

    # 全校得分基准
    school_avg = (
        await db.execute(
            select(func.round(func.avg(ResearchClassObservation.score_percentage), 1)).where(
                ResearchClassObservation.school_id == school_id,
                ResearchClassObservation.score_percentage.isnot(None),
            )
        )
    ).scalar()

    # rubric 评分矩阵份数（含分维度打分的记录数）
    from .models import ResearchObservationRubric

    rubric_count = (
        await db.execute(
            select(func.count(ResearchObservationRubric.id))
            .join(
                ResearchClassObservation,
                ResearchObservationRubric.observation_id == ResearchClassObservation.id,
            )
            .where(
                ResearchClassObservation.teacher_id == teacher_id,
                ResearchClassObservation.school_id == school_id,
            )
        )
    ).scalar() or 0

    return {
        "observations_count": obs_count,
        "observed_count": observed_count,
        "timeline_marks_count": int(marks),
        # V3.2 质量字段
        "observed_avg_score": float(observed_avg) if observed_avg is not None else 0.0,
        "scoring_avg": float(scoring_avg) if scoring_avg is not None else 0.0,
        "scoring_count": int(scoring_count),
        "school_avg_score": float(school_avg) if school_avg is not None else 0.0,
        "rubric_count": int(rubric_count),
    }


async def _dim4_ai(db: AsyncSession, teacher_id: int, school_id: int) -> dict:
    """维度4: AI偏方转化率"""
    ai_count = (
        await db.execute(
            select(func.count(ResearchLessonPlan.id)).where(
                ResearchLessonPlan.creator_id == teacher_id,
                ResearchLessonPlan.ai_bias_prescription.isnot(None),
                ResearchLessonPlan.school_id == school_id,
            )
        )
    ).scalar() or 0

    ai_published = (
        await db.execute(
            select(func.count(ResearchLessonPlan.id)).where(
                ResearchLessonPlan.creator_id == teacher_id,
                ResearchLessonPlan.ai_bias_prescription.isnot(None),
                ResearchLessonPlan.status == "PUBLISHED",
                ResearchLessonPlan.school_id == school_id,
            )
        )
    ).scalar() or 0

    return {"ai_integration_count": ai_count, "ai_published_count": ai_published}


# ═══════════════════════════════════════════════════
# 评分归一化引擎
# ═══════════════════════════════════════════════════


def _normalize_scores(raw: dict) -> dict:
    """四维 0-100 归一化评分（V3.2 — rigor 质+量双轨融合）"""
    p = raw["metrics"]["plans_count"]
    v = raw["metrics"]["versions_count"]
    pub = raw["metrics"]["published_count"]
    c = raw["metrics"]["comments_count"]
    a = raw["metrics"]["activities_count"]
    o = raw["metrics"]["observations_count"]
    m = raw["metrics"]["timeline_marks_count"]
    ai = raw["metrics"]["ai_integration_count"]
    ai_pub = raw["metrics"]["ai_published_count"]

    # 质量数据（V3.2 新增）
    observed_cnt = raw["metrics"].get("observed_count", 0)
    quality_score = float(raw["metrics"].get("observed_avg_score", 0) or 0)
    scoring_avg = float(raw["metrics"].get("scoring_avg", 0) or 0)
    school_avg = float(raw["metrics"].get("school_avg_score", 0) or 0)
    scoring_cnt = raw["metrics"].get("scoring_count", 0)

    intensity = min(100, int(p * 20 + v * 5 + pub * 10))
    social = min(100, int(c * 10 + a * 15))
    ai_score = min(100, int(100 * ai_pub / max(1, ai))) if ai > 0 else 0

    # ═══ V3.2 rigor 质+量双轨融合 ═══
    if quality_score > 0 and observed_cnt > 0:
        # 有被听课质量数据 → 50% 行为量 + 50% 授课质量
        behavioral = min(100, int(o * 15 + m * 5 + observed_cnt * 5))
        rigor = min(100, int(behavioral * 0.5 + quality_score * 0.5))

        # 评分客观度微调 (±3)：打分偏离全校均值越远越不客观
        if scoring_cnt > 0 and school_avg > 0:
            deviation = abs(scoring_avg - school_avg)
            if deviation <= 3:
                rigor = min(100, rigor + 3)  # 高度客观
            elif deviation > 15:
                rigor = max(0, rigor - 3)  # 偏差过大
        # 无打分数据的教师：不调整（中性）
    else:
        # 无质量数据：纯行为量旧公式
        rigor = min(100, int(o * 25 + m * 8))

    return {
        "intensity": intensity,
        "social": social,
        "rigor": rigor,
        "ai_integration": ai_score,
    }


# ═══════════════════════════════════════════════════
# 主画像聚合
# ═══════════════════════════════════════════════════


async def get_teacher_profile(
    db: AsyncSession,
    teacher_id: int,
    school_id: int,
) -> dict | None:
    """获取教师四维教研全息画像（含0-100评分归一化）"""
    r = await db.execute(
        select(User.display_name).where(User.id == teacher_id, User.school_id == school_id)
    )
    teacher_name = r.scalar()
    if not teacher_name:
        return None

    # 四维并行聚合
    d1 = await _dim1_prep(db, teacher_id, school_id)
    d2 = await _dim2_social(db, teacher_id, school_id)
    d3 = await _dim3_observation(db, teacher_id, school_id)
    d4 = await _dim4_ai(db, teacher_id, school_id)

    avg_versions = round(d1["versions_count"] / max(1, d1["plans_count"]), 2)

    metrics = {
        "plans_count": d1["plans_count"],
        "versions_count": d1["versions_count"],
        "published_count": d1["published_count"],
        "comments_count": d2["comments_count"],
        "activities_count": d2["activities_count"],
        "observations_count": d3["observations_count"],
        "observed_count": d3["observed_count"],
        "timeline_marks_count": d3["timeline_marks_count"],
        "ai_integration_count": d4["ai_integration_count"],
        "ai_published_count": d4["ai_published_count"],
        "avg_versions_per_plan": avg_versions,
        # V3.2 质量维度
        "observed_avg_score": d3.get("observed_avg_score", 0.0),
        "scoring_avg": d3.get("scoring_avg", 0.0),
        "scoring_count": d3.get("scoring_count", 0),
        "school_avg_score": d3.get("school_avg_score", 0.0),
        "rubric_count": d3.get("rubric_count", 0),
    }

    profile = {"teacher_id": teacher_id, "metrics": metrics}
    profile["scores"] = _normalize_scores(profile)

    logger.info(
        f"教师画像计算完成: teacher_id={teacher_id}, intensity={profile['scores']['intensity']}"
    )
    return profile


# ═══════════════════════════════════════════════════
# 全校教研效能排行榜（领导视图，低频管理聚合）
# ═══════════════════════════════════════════════════

# 综合分权重（与四维语义对齐：备课+听课是教研主战场，各占 0.30）
_COMPARE_WEIGHTS = {
    "intensity": 0.30,
    "social": 0.25,
    "rigor": 0.30,
    "ai_integration": 0.15,
}
_VALID_METRICS = ("composite", "intensity", "social", "rigor", "ai_integration")


async def get_ranking(
    db: AsyncSession,
    school_id: int,
    metric: str = "composite",
    limit: int = 20,
) -> dict:
    """
    全校教研效能排行榜。

    复用 list_teachers + get_teacher_profile 串行聚合（低频管理视图，
    不引入批量 group-by 重写，最小化对现有聚合引擎的影响）。
    综合分 = Σ(维度分 × 权重)，单维度排序时直接取该维度分。
    """
    if metric not in _VALID_METRICS:
        metric = "composite"

    teachers = await list_teachers(db, school_id)
    rows: list[dict] = []
    for t in teachers:
        tid = t["id"]
        prof = await get_teacher_profile(db, tid, school_id)
        if prof is None:
            continue
        sc = prof.get("scores", {})
        composite = round(
            sc.get("intensity", 0) * _COMPARE_WEIGHTS["intensity"]
            + sc.get("social", 0) * _COMPARE_WEIGHTS["social"]
            + sc.get("rigor", 0) * _COMPARE_WEIGHTS["rigor"]
            + sc.get("ai_integration", 0) * _COMPARE_WEIGHTS["ai_integration"],
            1,
        )
        rows.append(
            {
                "teacher_id": tid,
                "real_name": t["real_name"],
                "subject_code": t.get("subject_code"),
                "composite": composite,
                "scores": sc,
            }
        )

    # 排序：composite 用加权总分，否则取对应维度分
    if metric == "composite":
        rows.sort(key=lambda r: r["composite"], reverse=True)
    else:
        rows.sort(key=lambda r: r["scores"].get(metric, 0), reverse=True)

    items = []
    for i, r in enumerate(rows[:limit], start=1):
        items.append(
            {
                "rank": i,
                "teacher_id": r["teacher_id"],
                "real_name": r["real_name"],
                "subject_code": r["subject_code"],
                "composite": r["composite"],
                "scores": r["scores"],
            }
        )

    logger.info(
        f"教研排行榜计算完成: school_id={school_id}, metric={metric}, "
        f"total={len(rows)}, returned={len(items)}"
    )
    return {"metric": metric, "total": len(rows), "items": items}


# ═══════════════════════════════════════════════════════════════════════════
# 错题断层归因（dim5 诊断维度，独立子维度，不计入四维综合分）
#
# 归因桥（精确优先 + 回退，避免重复计数）：
#   精确桥 timetable_schedule_instances：class_id + subject_id(grades_subjects同源) + teacher_id
#          三件套齐全且与错题 subject_id 同源，可锁具体任课老师；运行时滚动表(仅近窗口)。
#   回退桥 teacher_subjects：subject_code + grade_id(执教年级)，无班级；
#          同年级同科多老师时整组归因（暑假/历史错题 timetable 无实例时启用）。
# ═══════════════════════════════════════════════════════════════════════════


async def get_teacher_error_gap(
    db: AsyncSession,
    teacher_id: int,
    school_id: int,
) -> dict:
    """
    教师任教范围内学生错题断层归因（教学盲区关注度诊断信号）。

    纯只读聚合，复用 timetable/teacher_mgmt/error_funnel/grades 模型，
    不建新表、不写库。返回结构直接喂 schemas.TeacherErrorGapResponse。

    归因语义：错题(ErrorBookItem/KnowledgeGap) 仅含 student_id + subject_id，
    经 Student.class_id/grade_id 反查，匹配教师的任教 (class,subject) 组合。
    """
    # ── 步骤1：构建任教映射 ──
    # 精确桥：timetable_schedule_instances（class + subject + teacher 同源）
    precise_rows = (
        await db.execute(
            select(
                TimetableScheduleInstance.class_id,
                TimetableScheduleInstance.subject_id,
            )
            .where(
                TimetableScheduleInstance.teacher_id == teacher_id,
                TimetableScheduleInstance.school_id == school_id,
            )
            .distinct()
        )
    ).all()
    precise_pairs = [(r.class_id, r.subject_id) for r in precise_rows]
    precise_class_ids = list({c for c, _ in precise_pairs})

    # 回退桥：teacher_subjects（subject_code + grade_id）
    ts_rows = (
        await db.execute(
            select(TeacherSubject.subject_code, TeacherSubject.grade_id).where(
                TeacherSubject.teacher_user_id == teacher_id,
                TeacherSubject.school_id == school_id,
            )
        )
    ).all()
    subj_codes = list({r.subject_code for r in ts_rows if r.subject_code})
    fallback_subject_ids: list[int] = []
    if subj_codes:
        gs_rows = (
            (
                await db.execute(
                    select(GradeSubject.id).where(
                        GradeSubject.school_id == school_id,
                        GradeSubject.code.in_(subj_codes),
                    )
                )
            )
            .scalars()
            .all()
        )
        fallback_subject_ids = list(gs_rows)
    # grade_ids（去重；teacher_subjects.grade_id 为 NULL 表示覆盖全校该学科）
    fallback_grade_ids = list({r.grade_id for r in ts_rows if r.grade_id is not None})

    # ── 步骤2：精确优先 + 回退，构建错题匹配条件（互斥，避免重复计数）──
    use_precise = bool(precise_pairs)
    if use_precise:
        ebi_conditions = [
            or_(
                *[
                    and_(Student.class_id == c, ErrorBookItem.subject_id == s)
                    for c, s in precise_pairs
                ]
            )
        ]
        kg_conditions = [
            or_(
                *[
                    and_(Student.class_id == c, KnowledgeGap.subject_id == s)
                    for c, s in precise_pairs
                ]
            )
        ]
        attribution = "precise"
        _student_scope = precise_class_ids
    elif fallback_subject_ids:
        subj_cond_e = ErrorBookItem.subject_id.in_(fallback_subject_ids)
        subj_cond_k = KnowledgeGap.subject_id.in_(fallback_subject_ids)
        if fallback_grade_ids:
            ebi_conditions = [and_(subj_cond_e, Student.grade_id.in_(fallback_grade_ids))]
            kg_conditions = [and_(subj_cond_k, Student.grade_id.in_(fallback_grade_ids))]
        else:
            # 该学科覆盖全校 → 不限年级
            ebi_conditions = [subj_cond_e]
            kg_conditions = [subj_cond_k]
        attribution = "fallback"
        _student_scope = fallback_grade_ids
    else:
        ebi_conditions = []
        kg_conditions = []
        attribution = "none"

    # ── 步骤3：归集错题指标 ──
    total_errors = unresolved_errors = 0
    by_error_type: dict[str, int] = {}
    if ebi_conditions:
        ebi_rows = (
            await db.execute(
                select(ErrorBookItem, Student.grade_id, Student.class_id)
                .join(Student, ErrorBookItem.student_id == Student.id)
                .where(ErrorBookItem.school_id == school_id)
                .where(or_(*ebi_conditions))
            )
        ).all()
        for ebi, _gid, _cid in ebi_rows:
            total_errors += 1
            if not ebi.is_resolved:
                unresolved_errors += 1
            et = ebi.error_type or "unknown"
            by_error_type[et] = by_error_type.get(et, 0) + 1

    gap_total = gap_critical = gap_active = gap_resolved = 0
    if kg_conditions:
        kg_rows = (
            (
                await db.execute(
                    select(KnowledgeGap)
                    .join(Student, KnowledgeGap.student_id == Student.id)
                    .where(KnowledgeGap.school_id == school_id)
                    .where(or_(*kg_conditions))
                )
            )
            .scalars()
            .all()
        )
        for g in kg_rows:
            gap_total += 1
            if g.gap_level == "critical":
                gap_critical += 1
            if g.gap_status == "active":
                gap_active += 1
            elif g.gap_status == "resolved":
                gap_resolved += 1

    # ── 步骤4：任教学生数（密度分母） ──
    if use_precise:
        n_students = (
            await db.execute(
                select(func.count(Student.id)).where(
                    Student.school_id == school_id,
                    Student.class_id.in_(precise_class_ids),
                )
            )
        ).scalar() or 0
    elif fallback_subject_ids and fallback_grade_ids:
        n_students = (
            await db.execute(
                select(func.count(Student.id)).where(
                    Student.school_id == school_id,
                    Student.grade_id.in_(fallback_grade_ids),
                )
            )
        ).scalar() or 0
    elif fallback_subject_ids and not fallback_grade_ids:
        # 该学科覆盖全校（teacher_subjects.grade_id 全 NULL）→ 全校学生数为分母
        n_students = (
            await db.execute(select(func.count(Student.id)).where(Student.school_id == school_id))
        ).scalar() or 0
    else:
        n_students = 0

    # ── 步骤5：归一化（0-100 教学盲区关注度，诊断信号非惩罚）──
    # 将错题率/断层率先转百分制再加权，避免 rate(0-1)×100 让分数瞬间饱和到 100。
    if n_students > 0:
        unresolved_pct = (unresolved_errors / n_students) * 100  # 未纠错率(%)
        critical_pct = (gap_critical / n_students) * 100  # 危重断层率(%)
        score = min(100, round(unresolved_pct * 0.6 + critical_pct * 0.4))
    else:
        score = 0

    logger.info(
        f"教师错题断层归因完成: teacher_id={teacher_id}, school_id={school_id}, "
        f"attribution={attribution}, attributed_students={n_students}, "
        f"errors={total_errors}, gaps={gap_total}, score={score}"
    )
    return {
        "teacher_id": teacher_id,
        "attributed_students": n_students,
        "attribution": attribution,
        "error_book": {
            "total": total_errors,
            "unresolved": unresolved_errors,
            "by_error_type": by_error_type,
        },
        "knowledge_gap": {
            "total": gap_total,
            "critical": gap_critical,
            "active": gap_active,
            "resolved": gap_resolved,
        },
        "score": score,
    }
