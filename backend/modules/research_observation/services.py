"""
research_observation/services.py — 听课评课核心业务引擎

核心能力:
  1. 听课记录 CRUD + 教案血缘咬合 (lesson_plan_id)
  2. 多维量化评分 (JSON动态矩阵, 自动汇总总分/等级)
  3. 教师确认/申诉状态机 (PENDING → CONFIRMED / APPEALED → RESOLVED)
  4. 教案执行度对比 (plan_adherence: full/partial/deviated)
  5. 听课统计看板 (按类型/等级/学科/教师聚合)
"""

from datetime import datetime

from core.models import User, get_local_now
from modules.timetable.enricher import TimetableEnricher
from modules.timetable.models import TimetableScheduleInstance
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    FEEDBACK_APPEALED,
    FEEDBACK_CONFIRMED,
    FEEDBACK_PENDING,
    FEEDBACK_RESOLVED,
    VALID_FEEDBACK_TRANSITIONS,
    ResearchClassObservation,
    ResearchObservationAppeal,
    ResearchObservationRubric,
)
from .schemas import (
    AppealResolve,
    ObservationCreate,
    ObservationUpdate,
    RubricSubmit,
    TeacherAppeal,
    TimelineCommentCreate,
)

# ═══════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════


async def _get_user_name(db: AsyncSession, user_id: int) -> str:
    result = await db.execute(select(User.display_name).where(User.id == user_id))
    row = result.scalar_one_or_none()
    return row or f"用户{user_id}"


async def _get_user_names_batch(db: AsyncSession, user_ids: list[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    result = await db.execute(select(User.id, User.display_name).where(User.id.in_(user_ids)))
    return {row[0]: row[1] for row in result.fetchall()}


def _calculate_grade(percentage: float) -> str:
    """根据得分率计算等级"""
    if percentage >= 90:
        return "excellent"
    elif percentage >= 75:
        return "good"
    elif percentage >= 60:
        return "fair"
    else:
        return "needs_improvement"


def _validate_feedback_transition(current: str, target: str) -> bool:
    allowed = VALID_FEEDBACK_TRANSITIONS.get(current, [])
    return target in allowed


# ═══════════════════════════════════════════════
# 听课记录 CRUD
# ═══════════════════════════════════════════════


async def create_observation(
    db: AsyncSession,
    school_id: int,
    observer_id: int,
    data: ObservationCreate,
) -> ResearchClassObservation:
    """创建听课记录"""
    obs = ResearchClassObservation(
        school_id=school_id,
        observer_id=observer_id,
        teacher_id=data.teacher_id,
        class_id=data.class_id,
        subject_code=data.subject_code,
        lesson_title=data.lesson_title,
        observation_type=data.observation_type,
        lesson_plan_id=data.lesson_plan_id,
        plan_version_number=data.plan_version_number,
        text_feedback=data.text_feedback.model_dump() if data.text_feedback else None,
        plan_adherence=data.plan_adherence,
        plan_deviation_note=data.plan_deviation_note,
        schedule_instance_id=data.schedule_instance_id,
        feedback_status=FEEDBACK_PENDING,
        observed_at=data.observed_at,
        duration_minutes=data.duration_minutes,
        score_max=100.0,
    )
    db.add(obs)
    await db.commit()
    await db.refresh(obs)
    return obs


async def get_observation(
    db: AsyncSession,
    school_id: int,
    obs_id: int,
) -> ResearchClassObservation | None:
    result = await db.execute(
        select(ResearchClassObservation).where(
            and_(
                ResearchClassObservation.id == obs_id,
                ResearchClassObservation.school_id == school_id,
            )
        )
    )
    return result.scalar_one_or_none()


async def list_observations(
    db: AsyncSession,
    school_id: int,
    observer_id: int | None = None,
    teacher_id: int | None = None,
    class_id: int | None = None,
    subject_code: str | None = None,
    feedback_status: str | None = None,
    observation_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    """听课列表 (分页+多维度筛选)"""
    conditions = [ResearchClassObservation.school_id == school_id]
    if observer_id:
        conditions.append(ResearchClassObservation.observer_id == observer_id)
    if teacher_id:
        conditions.append(ResearchClassObservation.teacher_id == teacher_id)
    if class_id:
        conditions.append(ResearchClassObservation.class_id == class_id)
    if subject_code:
        conditions.append(ResearchClassObservation.subject_code == subject_code)
    if feedback_status:
        conditions.append(ResearchClassObservation.feedback_status == feedback_status)
    if observation_type:
        conditions.append(ResearchClassObservation.observation_type == observation_type)

    total = (
        await db.execute(
            select(func.count()).select_from(ResearchClassObservation).where(*conditions)
        )
    ).scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        select(ResearchClassObservation)
        .where(*conditions)
        .order_by(ResearchClassObservation.observed_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = result.scalars().all()

    # 批量获取人名
    user_ids = set()
    for r in rows:
        user_ids.add(r.observer_id)
        user_ids.add(r.teacher_id)
    name_map = await _get_user_names_batch(db, list(user_ids))

    items = []
    for r in rows:
        items.append(_obs_to_dict(r, name_map))

    return items, total


async def update_observation(
    db: AsyncSession,
    school_id: int,
    obs_id: int,
    data: ObservationUpdate,
) -> ResearchClassObservation | None:
    """更新听课记录 (仅pending状态可改)"""
    obs = await get_observation(db, school_id, obs_id)
    if not obs:
        return None
    if obs.feedback_status != FEEDBACK_PENDING:
        return None

    if data.lesson_title is not None:
        obs.lesson_title = data.lesson_title
    if data.observation_type is not None:
        obs.observation_type = data.observation_type
    if data.text_feedback is not None:
        obs.text_feedback = data.text_feedback.model_dump()
    if data.plan_adherence is not None:
        obs.plan_adherence = data.plan_adherence
    if data.plan_deviation_note is not None:
        obs.plan_deviation_note = data.plan_deviation_note

    await db.commit()
    await db.refresh(obs)
    return obs


async def delete_observation(db: AsyncSession, school_id: int, obs_id: int) -> bool:
    """删除听课记录 (仅pending状态可删)"""
    obs = await get_observation(db, school_id, obs_id)
    if not obs:
        return False
    if obs.feedback_status != FEEDBACK_PENDING:
        return False

    # 级联删除评分和申诉
    await db.execute(
        delete(ResearchObservationRubric).where(ResearchObservationRubric.observation_id == obs_id)
    )
    await db.execute(
        delete(ResearchObservationAppeal).where(ResearchObservationAppeal.observation_id == obs_id)
    )
    await db.delete(obs)
    await db.commit()
    return True


# ═══════════════════════════════════════════════
# 多维量化评分
# ═══════════════════════════════════════════════


async def submit_rubric(
    db: AsyncSession,
    school_id: int,
    obs_id: int,
    scorer_id: int,
    data: RubricSubmit,
) -> tuple[ResearchObservationRubric, ResearchClassObservation] | None:
    """提交多维评分 — 自动计算总分/等级"""
    obs = await get_observation(db, school_id, obs_id)
    if not obs:
        return None

    # 计算总分
    total = sum(d.score for d in data.dimensions)
    max_score = sum(d.max for d in data.dimensions)
    percentage = round(total / max_score * 100, 1) if max_score > 0 else 0

    # 序列化维度
    rubric_metrics = [d.model_dump() for d in data.dimensions]

    # 删除旧评分 (幂等)
    await db.execute(
        delete(ResearchObservationRubric).where(
            and_(
                ResearchObservationRubric.observation_id == obs_id,
                ResearchObservationRubric.school_id == school_id,
            )
        )
    )
    await db.flush()

    rubric = ResearchObservationRubric(
        school_id=school_id,
        observation_id=obs_id,
        template_name=data.template_name,
        rubric_metrics=rubric_metrics,
        total_score=total,
        max_score=max_score,
        percentage=percentage,
        scorer_id=scorer_id,
    )
    db.add(rubric)

    # 回写听课主表
    obs.score_total = total
    obs.score_max = max_score
    obs.score_percentage = percentage
    obs.grade = _calculate_grade(percentage)

    await db.commit()
    await db.refresh(rubric)
    await db.refresh(obs)
    return rubric, obs


async def get_rubric(
    db: AsyncSession,
    school_id: int,
    obs_id: int,
) -> ResearchObservationRubric | None:
    result = await db.execute(
        select(ResearchObservationRubric).where(
            and_(
                ResearchObservationRubric.observation_id == obs_id,
                ResearchObservationRubric.school_id == school_id,
            )
        )
    )
    return result.scalar_one_or_none()


# ═══════════════════════════════════════════════
# 教师确认/申诉状态机
# ═══════════════════════════════════════════════


async def teacher_confirm(
    db: AsyncSession,
    school_id: int,
    obs_id: int,
    teacher_id: int,
) -> ResearchClassObservation | None:
    """教师确认评课结果 (PENDING → CONFIRMED)"""
    obs = await get_observation(db, school_id, obs_id)
    if not obs:
        return None
    if obs.teacher_id != teacher_id:
        return None

    if not _validate_feedback_transition(obs.feedback_status, FEEDBACK_CONFIRMED):
        return None

    obs.feedback_status = FEEDBACK_CONFIRMED
    obs.feedback_status_updated_at = get_local_now()
    if not obs.teacher_viewed_at:
        obs.teacher_viewed_at = get_local_now()

    # 记录确认
    appeal = ResearchObservationAppeal(
        school_id=school_id,
        observation_id=obs_id,
        teacher_id=teacher_id,
        action_type="confirm",
    )
    db.add(appeal)
    await db.commit()
    await db.refresh(obs)
    return obs


async def teacher_appeal(
    db: AsyncSession,
    school_id: int,
    obs_id: int,
    teacher_id: int,
    data: TeacherAppeal,
) -> ResearchClassObservation | None:
    """教师申诉 (PENDING → APPEALED)"""
    obs = await get_observation(db, school_id, obs_id)
    if not obs:
        return None
    if obs.teacher_id != teacher_id:
        return None

    if not _validate_feedback_transition(obs.feedback_status, FEEDBACK_APPEALED):
        return None

    obs.feedback_status = FEEDBACK_APPEALED
    obs.feedback_status_updated_at = get_local_now()
    if not obs.teacher_viewed_at:
        obs.teacher_viewed_at = get_local_now()

    appeal = ResearchObservationAppeal(
        school_id=school_id,
        observation_id=obs_id,
        teacher_id=teacher_id,
        action_type="appeal",
        appeal_reason=data.appeal_reason,
        appealed_dimensions=data.appealed_dimensions,
    )
    db.add(appeal)
    await db.commit()
    await db.refresh(obs)
    return obs


async def resolve_appeal(
    db: AsyncSession,
    school_id: int,
    obs_id: int,
    resolver_id: int,
    data: AppealResolve,
) -> ResearchClassObservation | None:
    """处理申诉 (APPEALED → RESOLVED)"""
    obs = await get_observation(db, school_id, obs_id)
    if not obs:
        return None

    if not _validate_feedback_transition(obs.feedback_status, FEEDBACK_RESOLVED):
        return None

    obs.feedback_status = FEEDBACK_RESOLVED
    obs.feedback_status_updated_at = get_local_now()

    # 如果调整了评分 — adjusted_total_score 为 0-100 分制，同步更新 score_max
    if data.score_adjusted and data.adjusted_total_score is not None:
        obs.score_total = data.adjusted_total_score
        obs.score_max = 100  # 仲裁调整分统一为百分制
        obs.score_percentage = round(data.adjusted_total_score, 1)
        obs.grade = _calculate_grade(obs.score_percentage)

    appeal = ResearchObservationAppeal(
        school_id=school_id,
        observation_id=obs_id,
        teacher_id=obs.teacher_id,
        action_type="resolve",
        resolution=data.resolution,
        resolved_by=resolver_id,
        score_adjusted=data.score_adjusted,
        adjusted_total_score=data.adjusted_total_score,
        resolved_at=get_local_now(),
    )
    db.add(appeal)
    await db.commit()
    await db.refresh(obs)
    return obs


async def list_appeals(
    db: AsyncSession,
    school_id: int,
    obs_id: int,
) -> tuple[list[dict], int]:
    """获取听课记录的反馈/申诉历史"""
    result = await db.execute(
        select(ResearchObservationAppeal)
        .where(
            and_(
                ResearchObservationAppeal.observation_id == obs_id,
                ResearchObservationAppeal.school_id == school_id,
            )
        )
        .order_by(ResearchObservationAppeal.created_at.asc())
    )
    rows = result.scalars().all()

    teacher_ids = [r.teacher_id for r in rows] + [r.resolved_by for r in rows if r.resolved_by]
    name_map = await _get_user_names_batch(db, list(set(teacher_ids)))

    items = []
    for r in rows:
        items.append(
            {
                "id": r.id,
                "observation_id": r.observation_id,
                "teacher_id": r.teacher_id,
                "teacher_name": name_map.get(r.teacher_id, f"用户{r.teacher_id}"),
                "action_type": r.action_type,
                "appeal_reason": r.appeal_reason,
                "appealed_dimensions": r.appealed_dimensions or [],
                "resolution": r.resolution,
                "resolved_by": r.resolved_by,
                "score_adjusted": r.score_adjusted,
                "adjusted_total_score": r.adjusted_total_score,
                "created_at": r.created_at,
                "resolved_at": r.resolved_at,
            }
        )

    return items, len(items)


# ═══════════════════════════════════════════════
# 教师听课历史
# ═══════════════════════════════════════════════


async def get_teacher_history(
    db: AsyncSession,
    school_id: int,
    teacher_id: int,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    """教师被听课历史"""
    return await list_observations(
        db,
        school_id,
        teacher_id=teacher_id,
        page=page,
        page_size=page_size,
    )


# ═══════════════════════════════════════════════
# 听课统计看板
# ═══════════════════════════════════════════════


async def get_dashboard_stats(db: AsyncSession, school_id: int) -> dict:
    """听课统计看板"""
    total = (
        await db.execute(
            select(func.count())
            .select_from(ResearchClassObservation)
            .where(ResearchClassObservation.school_id == school_id)
        )
    ).scalar() or 0

    # 按反馈状态
    status_q = (
        select(ResearchClassObservation.feedback_status, func.count())
        .where(ResearchClassObservation.school_id == school_id)
        .group_by(ResearchClassObservation.feedback_status)
    )
    status_rows = (await db.execute(status_q)).fetchall()
    status_map = {row[0]: row[1] for row in status_rows}

    # 平均分
    avg_q = select(func.avg(ResearchClassObservation.score_percentage)).where(
        and_(
            ResearchClassObservation.school_id == school_id,
            ResearchClassObservation.score_percentage.isnot(None),
        )
    )
    avg_score = (await db.execute(avg_q)).scalar()

    # 按听课类型
    type_q = (
        select(ResearchClassObservation.observation_type, func.count())
        .where(ResearchClassObservation.school_id == school_id)
        .group_by(ResearchClassObservation.observation_type)
    )
    type_rows = (await db.execute(type_q)).fetchall()
    by_type = {row[0]: row[1] for row in type_rows}

    # 按等级
    grade_q = (
        select(ResearchClassObservation.grade, func.count())
        .where(
            and_(
                ResearchClassObservation.school_id == school_id,
                ResearchClassObservation.grade.isnot(None),
            )
        )
        .group_by(ResearchClassObservation.grade)
    )
    grade_rows = (await db.execute(grade_q)).fetchall()
    by_grade = {row[0]: row[1] for row in grade_rows}

    # 按学科
    subject_q = (
        select(ResearchClassObservation.subject_code, func.count())
        .where(ResearchClassObservation.school_id == school_id)
        .group_by(ResearchClassObservation.subject_code)
    )
    subject_rows = (await db.execute(subject_q)).fetchall()
    by_subject = {row[0]: row[1] for row in subject_rows}

    # Top听课人
    observer_q = (
        select(
            ResearchClassObservation.observer_id,
            func.count().label("obs_count"),
        )
        .where(ResearchClassObservation.school_id == school_id)
        .group_by(ResearchClassObservation.observer_id)
        .order_by(func.count().desc())
        .limit(5)
    )
    observer_rows = (await db.execute(observer_q)).fetchall()
    observer_ids = [row[0] for row in observer_rows]
    obs_name_map = await _get_user_names_batch(db, observer_ids)
    top_observers = [
        {"user_id": r[0], "name": obs_name_map.get(r[0], f"用户{r[0]}"), "observation_count": r[1]}
        for r in observer_rows
    ]

    # Top被听课教师
    teacher_q = (
        select(
            ResearchClassObservation.teacher_id,
            func.count().label("obs_count"),
            func.avg(ResearchClassObservation.score_percentage).label("avg_score"),
        )
        .where(ResearchClassObservation.school_id == school_id)
        .group_by(ResearchClassObservation.teacher_id)
        .order_by(func.count().desc())
        .limit(5)
    )
    teacher_rows = (await db.execute(teacher_q)).fetchall()
    teacher_ids = [row[0] for row in teacher_rows]
    t_name_map = await _get_user_names_batch(db, teacher_ids)
    top_teachers = [
        {
            "user_id": r[0],
            "name": t_name_map.get(r[0], f"用户{r[0]}"),
            "observation_count": r[1],
            "avg_score": round(float(r[2]), 1) if r[2] else None,
        }
        for r in teacher_rows
    ]

    return {
        "total_observations": total,
        "pending_feedback": status_map.get(FEEDBACK_PENDING, 0),
        "confirmed": status_map.get(FEEDBACK_CONFIRMED, 0),
        "appealed": status_map.get(FEEDBACK_APPEALED, 0),
        "resolved": status_map.get(FEEDBACK_RESOLVED, 0),
        "avg_score": round(float(avg_score), 1) if avg_score else None,
        "by_type": by_type,
        "by_grade": by_grade,
        "by_subject": by_subject,
        "top_observers": top_observers,
        "top_teachers": top_teachers,
    }


# ═══════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════


def _obs_to_dict(obs: ResearchClassObservation, name_map: dict[int, str]) -> dict:
    """ORM → dict"""
    return {
        "id": obs.id,
        "school_id": obs.school_id,
        "observer_id": obs.observer_id,
        "observer_name": name_map.get(obs.observer_id, f"用户{obs.observer_id}"),
        "teacher_id": obs.teacher_id,
        "teacher_name": name_map.get(obs.teacher_id, f"用户{obs.teacher_id}"),
        "class_id": obs.class_id,
        "subject_code": obs.subject_code,
        "lesson_title": obs.lesson_title,
        "observation_type": obs.observation_type,
        "lesson_plan_id": obs.lesson_plan_id,
        "plan_version_number": obs.plan_version_number,
        "score_total": obs.score_total,
        "score_max": obs.score_max or 100.0,
        "score_percentage": obs.score_percentage,
        "grade": obs.grade,
        "text_feedback": obs.text_feedback,
        "plan_adherence": obs.plan_adherence,
        "plan_deviation_note": obs.plan_deviation_note,
        "schedule_instance_id": obs.schedule_instance_id,
        "timeline_comments": obs.timeline_comments or [],
        "feedback_status": obs.feedback_status,
        "feedback_status_updated_at": obs.feedback_status_updated_at,
        "teacher_viewed_at": obs.teacher_viewed_at,
        "observed_at": obs.observed_at,
        "duration_minutes": obs.duration_minutes,
        "created_at": obs.created_at,
        "updated_at": obs.updated_at,
    }


# ═══════════════════════════════════════════════
# 时空弹道捕获器 (Wings 3.1)
# ═══════════════════════════════════════════════


async def auto_locate(
    db: AsyncSession,
    school_id: int,
    class_id: int,
    occurred_at: datetime,
) -> dict:
    """
    自动卡位 — 调用TimetableEnricher零输入自动反查(节次/学科/教师)
    输入: class_id + 时间戳
    输出: {in_lesson, period_index, slot_id, subject_id, teacher_id, teacher_name, context_desc, schedule_instance_id}
    """
    # 调用时空连续体富集网关
    ctx = await TimetableEnricher.enrich_telemetry_event(
        school_id,
        class_id,
        occurred_at,
        db,
    )

    result = {
        "in_lesson": ctx.get("in_lesson", False),
        "period_index": ctx.get("period_index"),
        "slot_id": ctx.get("slot_id"),
        "subject_id": ctx.get("subject_id"),
        "teacher_id": ctx.get("teacher_id"),
        "teacher_name": None,
        "context_desc": ctx.get("context_desc", ""),
        "schedule_instance_id": None,
    }

    # 如果在课中且有slot_id，反查schedule_instance_id
    slot_id = ctx.get("slot_id")
    if slot_id:
        inst_result = await db.execute(
            select(TimetableScheduleInstance.id).where(
                and_(
                    TimetableScheduleInstance.school_id == school_id,
                    TimetableScheduleInstance.class_id == class_id,
                    TimetableScheduleInstance.date == occurred_at.date(),
                    TimetableScheduleInstance.slot_id == slot_id,
                )
            )
        )
        inst_id = inst_result.scalar_one_or_none()
        if inst_id:
            result["schedule_instance_id"] = inst_id

    # 如果有teacher_id，反查教师姓名
    teacher_id = ctx.get("teacher_id")
    if teacher_id:
        result["teacher_name"] = await _get_user_name(db, teacher_id)

    return result


async def add_timeline_comment(
    db: AsyncSession,
    school_id: int,
    obs_id: int,
    user_id: int,
    data: TimelineCommentCreate,
) -> dict | None:
    """
    打点弹幕 — 听课过程中实时打点, 追加到timeline_comments JSON数组
    每条弹幕: {seconds_in_lesson, type, text, author_id, author_name, created_at}
    """
    obs = await get_observation(db, school_id, obs_id)
    if not obs:
        return None

    author_name = await _get_user_name(db, user_id)
    now = get_local_now()

    comment_entry = {
        "seconds_in_lesson": data.seconds_in_lesson,
        "type": data.type,
        "text": data.text,
        "author_id": user_id,
        "author_name": author_name,
        "created_at": now.isoformat() if now else None,
    }

    # 追加到JSON数组 (MySQL JSON_ARRAY_APPEND 或 Python层操作)
    existing = obs.timeline_comments or []
    existing.append(comment_entry)
    obs.timeline_comments = existing
    # 强制标记脏数据 (SQLAlchemy JSON列变更检测)
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(obs, "timeline_comments")

    await db.commit()
    await db.refresh(obs)

    return comment_entry
