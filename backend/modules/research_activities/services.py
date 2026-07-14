"""
research_activities/services.py — 教研活动管理核心业务引擎

核心能力:
  1. 活动 CRUD + 状态机 (PLANNED → IN_PROGRESS → COMPLETED / CANCELLED)
  2. 参与人员管理 (角色/考勤/贡献度, 唯一约束防重复)
  3. 议题/议程管理 (讨论记录/决议, 血缘咬合备课+听课)
  4. 教研活动看板统计 (按类型/学科/月份聚合)
  5. 活动总结与决议归档
"""

from core.models import User, get_local_now
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ACT_CANCELLED,
    ACT_COMPLETED,
    ACT_IN_PROGRESS,
    ACT_PLANNED,
    AGENDA_PENDING,
    ATTEND_REGISTERED,
    PART_ORGANIZER,
    VALID_ACT_TRANSITIONS,
    ResearchActivity,
    ResearchActivityAgenda,
    ResearchActivityParticipant,
)
from .schemas import (
    ActivityCreate,
    ActivityUpdate,
    AgendaCreate,
    AgendaUpdate,
    ParticipantAdd,
    ParticipantUpdate,
)

# ═══════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════


async def _get_user_name(db: AsyncSession, user_id: int) -> str:
    result = await db.execute(select(User.display_name).where(User.id == user_id))
    return result.scalar_one_or_none() or f"用户{user_id}"


async def _get_user_names_batch(db: AsyncSession, user_ids: list[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    result = await db.execute(select(User.id, User.display_name).where(User.id.in_(user_ids)))
    return {row[0]: row[1] for row in result.fetchall()}


def _validate_act_transition(current: str, target: str) -> bool:
    return target in VALID_ACT_TRANSITIONS.get(current, [])


# ═══════════════════════════════════════════════
# 活动 CRUD
# ═══════════════════════════════════════════════


async def create_activity(
    db: AsyncSession,
    school_id: int,
    organizer_id: int,
    data: ActivityCreate,
) -> ResearchActivity:
    """创建教研活动 + 初始参与人"""
    now = get_local_now()
    activity = ResearchActivity(
        school_id=school_id,
        title=data.title,
        description=data.description,
        activity_type=data.activity_type,
        subject_code=data.subject_code,
        grade_level=data.grade_level,
        planned_at=data.planned_at,
        planned_end_at=data.planned_end_at,
        location=data.location,
        status=ACT_PLANNED,
        status_updated_at=now,
        status_updated_by=organizer_id,
        organizer_id=organizer_id,
        linked_plan_ids=data.linked_plan_ids,
        linked_observation_ids=data.linked_observation_ids,
    )
    db.add(activity)
    await db.flush()

    # 组织者自动加入参与人
    org_participant = ResearchActivityParticipant(
        school_id=school_id,
        activity_id=activity.id,
        user_id=organizer_id,
        role=PART_ORGANIZER,
        attendance_status=ATTEND_REGISTERED,
    )
    db.add(org_participant)

    # 添加初始参与人
    for uid in data.participant_ids:
        if uid != organizer_id:
            p = ResearchActivityParticipant(
                school_id=school_id,
                activity_id=activity.id,
                user_id=uid,
                attendance_status=ATTEND_REGISTERED,
            )
            db.add(p)

    activity.participant_count = 1 + len(data.participant_ids)
    await db.commit()
    await db.refresh(activity)
    return activity


async def get_activity(db: AsyncSession, school_id: int, act_id: int) -> ResearchActivity | None:
    result = await db.execute(
        select(ResearchActivity).where(
            and_(ResearchActivity.id == act_id, ResearchActivity.school_id == school_id)
        )
    )
    return result.scalar_one_or_none()


async def list_activities(
    db: AsyncSession,
    school_id: int,
    subject_code: str | None = None,
    activity_type: str | None = None,
    status: str | None = None,
    organizer_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    conditions = [ResearchActivity.school_id == school_id]
    if subject_code:
        conditions.append(ResearchActivity.subject_code == subject_code)
    if activity_type:
        conditions.append(ResearchActivity.activity_type == activity_type)
    if status:
        conditions.append(ResearchActivity.status == status)
    if organizer_id:
        conditions.append(ResearchActivity.organizer_id == organizer_id)

    total = (
        await db.execute(select(func.count()).select_from(ResearchActivity).where(*conditions))
    ).scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        select(ResearchActivity)
        .where(*conditions)
        .order_by(ResearchActivity.planned_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = result.scalars().all()

    org_ids = [r.organizer_id for r in rows]
    name_map = await _get_user_names_batch(db, org_ids)

    items = [_activity_to_dict(r, name_map) for r in rows]
    return items, total


async def update_activity(
    db: AsyncSession,
    school_id: int,
    act_id: int,
    data: ActivityUpdate,
) -> ResearchActivity | None:
    activity = await get_activity(db, school_id, act_id)
    if not activity:
        return None
    if activity.status not in (ACT_PLANNED, ACT_IN_PROGRESS):
        return None

    for field in [
        "title",
        "description",
        "activity_type",
        "grade_level",
        "planned_at",
        "planned_end_at",
        "location",
        "summary",
        "decisions",
        "attachments",
        "linked_plan_ids",
        "linked_observation_ids",
    ]:
        val = getattr(data, field, None)
        if val is not None:
            setattr(activity, field, val)

    await db.commit()
    await db.refresh(activity)
    return activity


async def delete_activity(db: AsyncSession, school_id: int, act_id: int) -> bool:
    activity = await get_activity(db, school_id, act_id)
    if not activity:
        return False
    if activity.status in (ACT_IN_PROGRESS, ACT_COMPLETED):
        return False

    await db.execute(
        delete(ResearchActivityParticipant).where(ResearchActivityParticipant.activity_id == act_id)
    )
    await db.execute(
        delete(ResearchActivityAgenda).where(ResearchActivityAgenda.activity_id == act_id)
    )
    await db.delete(activity)
    await db.commit()
    return True


# ═══════════════════════════════════════════════
# 状态机流转
# ═══════════════════════════════════════════════


async def transition_status(
    db: AsyncSession,
    school_id: int,
    act_id: int,
    target: str,
    operator_id: int,
    cancel_reason: str | None = None,
) -> tuple[ResearchActivity | None, str | None]:
    activity = await get_activity(db, school_id, act_id)
    if not activity:
        return None, "活动不存在"

    if not _validate_act_transition(activity.status, target):
        return None, f"非法状态流转: {activity.status} → {target}"

    now = get_local_now()
    if target == ACT_IN_PROGRESS:
        activity.actual_start_at = now
    elif target == ACT_COMPLETED:
        activity.actual_end_at = now
    elif target == ACT_CANCELLED:
        activity.cancel_reason = cancel_reason

    activity.status = target
    activity.status_updated_at = now
    activity.status_updated_by = operator_id

    await db.commit()
    await db.refresh(activity)
    return activity, None


# ═══════════════════════════════════════════════
# 参与人员管理
# ═══════════════════════════════════════════════


async def add_participant(
    db: AsyncSession,
    school_id: int,
    act_id: int,
    data: ParticipantAdd,
) -> ResearchActivityParticipant | None:
    activity = await get_activity(db, school_id, act_id)
    if not activity:
        return None

    # 唯一约束: 同一活动同一人不能重复
    existing = await db.execute(
        select(ResearchActivityParticipant).where(
            and_(
                ResearchActivityParticipant.activity_id == act_id,
                ResearchActivityParticipant.user_id == data.user_id,
                ResearchActivityParticipant.school_id == school_id,
            )
        )
    )
    if existing.scalar_one_or_none():
        return None

    p = ResearchActivityParticipant(
        school_id=school_id,
        activity_id=act_id,
        user_id=data.user_id,
        role=data.role,
        attendance_status=ATTEND_REGISTERED,
    )
    db.add(p)

    # 更新参与人数缓存
    activity.participant_count = (activity.participant_count or 0) + 1

    await db.commit()
    await db.refresh(p)
    return p


async def list_participants(
    db: AsyncSession,
    school_id: int,
    act_id: int,
) -> tuple[list[dict], int]:
    result = await db.execute(
        select(ResearchActivityParticipant)
        .where(
            and_(
                ResearchActivityParticipant.activity_id == act_id,
                ResearchActivityParticipant.school_id == school_id,
            )
        )
        .order_by(ResearchActivityParticipant.created_at.asc())
    )
    rows = result.scalars().all()

    user_ids = [r.user_id for r in rows]
    name_map = await _get_user_names_batch(db, user_ids)

    items = []
    for r in rows:
        items.append(
            {
                "id": r.id,
                "activity_id": r.activity_id,
                "user_id": r.user_id,
                "user_name": name_map.get(r.user_id, f"用户{r.user_id}"),
                "role": r.role,
                "attendance_status": r.attendance_status,
                "check_in_at": r.check_in_at,
                "check_out_at": r.check_out_at,
                "contribution_score": r.contribution_score,
                "contribution_note": r.contribution_note,
                "note": r.note,
                "created_at": r.created_at,
            }
        )
    return items, len(items)


async def update_participant(
    db: AsyncSession,
    school_id: int,
    act_id: int,
    participant_id: int,
    data: ParticipantUpdate,
) -> ResearchActivityParticipant | None:
    result = await db.execute(
        select(ResearchActivityParticipant).where(
            and_(
                ResearchActivityParticipant.id == participant_id,
                ResearchActivityParticipant.activity_id == act_id,
                ResearchActivityParticipant.school_id == school_id,
            )
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        return None

    for field in [
        "role",
        "attendance_status",
        "check_in_at",
        "check_out_at",
        "contribution_score",
        "contribution_note",
        "note",
    ]:
        val = getattr(data, field, None)
        if val is not None:
            setattr(p, field, val)

    await db.commit()
    await db.refresh(p)
    return p


async def remove_participant(
    db: AsyncSession, school_id: int, act_id: int, participant_id: int
) -> bool:
    result = await db.execute(
        select(ResearchActivityParticipant).where(
            and_(
                ResearchActivityParticipant.id == participant_id,
                ResearchActivityParticipant.activity_id == act_id,
                ResearchActivityParticipant.school_id == school_id,
            )
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        return False

    activity = await get_activity(db, school_id, act_id)
    if activity and activity.participant_count and activity.participant_count > 0:
        activity.participant_count -= 1

    await db.delete(p)
    await db.commit()
    return True


# ═══════════════════════════════════════════════
# 议题/议程管理
# ═══════════════════════════════════════════════


async def create_agenda(
    db: AsyncSession,
    school_id: int,
    act_id: int,
    data: AgendaCreate,
) -> ResearchActivityAgenda | None:
    activity = await get_activity(db, school_id, act_id)
    if not activity:
        return None

    # 获取当前最大seq
    max_seq_result = await db.execute(
        select(func.max(ResearchActivityAgenda.seq)).where(
            and_(
                ResearchActivityAgenda.activity_id == act_id,
                ResearchActivityAgenda.school_id == school_id,
            )
        )
    )
    max_seq = max_seq_result.scalar() or 0

    agenda = ResearchActivityAgenda(
        school_id=school_id,
        activity_id=act_id,
        seq=max_seq + 1,
        title=data.title,
        presenter_id=data.presenter_id,
        content=data.content,
        planned_duration=data.planned_duration,
        linked_plan_id=data.linked_plan_id,
        linked_observation_id=data.linked_observation_id,
        status=AGENDA_PENDING,
    )
    db.add(agenda)

    activity.agenda_count = (activity.agenda_count or 0) + 1

    await db.commit()
    await db.refresh(agenda)
    return agenda


async def list_agendas(
    db: AsyncSession,
    school_id: int,
    act_id: int,
) -> tuple[list[dict], int]:
    result = await db.execute(
        select(ResearchActivityAgenda)
        .where(
            and_(
                ResearchActivityAgenda.activity_id == act_id,
                ResearchActivityAgenda.school_id == school_id,
            )
        )
        .order_by(ResearchActivityAgenda.seq.asc())
    )
    rows = result.scalars().all()

    presenter_ids = [r.presenter_id for r in rows if r.presenter_id]
    name_map = await _get_user_names_batch(db, presenter_ids)

    items = []
    for r in rows:
        items.append(
            {
                "id": r.id,
                "activity_id": r.activity_id,
                "seq": r.seq,
                "title": r.title,
                "presenter_id": r.presenter_id,
                "presenter_name": name_map.get(r.presenter_id, f"用户{r.presenter_id}")
                if r.presenter_id
                else None,
                "content": r.content,
                "planned_duration": r.planned_duration,
                "actual_duration": r.actual_duration,
                "decision": r.decision,
                "status": r.status,
                "linked_plan_id": r.linked_plan_id,
                "linked_observation_id": r.linked_observation_id,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
        )
    return items, len(items)


async def update_agenda(
    db: AsyncSession,
    school_id: int,
    act_id: int,
    agenda_id: int,
    data: AgendaUpdate,
) -> ResearchActivityAgenda | None:
    result = await db.execute(
        select(ResearchActivityAgenda).where(
            and_(
                ResearchActivityAgenda.id == agenda_id,
                ResearchActivityAgenda.activity_id == act_id,
                ResearchActivityAgenda.school_id == school_id,
            )
        )
    )
    agenda = result.scalar_one_or_none()
    if not agenda:
        return None

    for field in [
        "title",
        "presenter_id",
        "content",
        "planned_duration",
        "actual_duration",
        "decision",
        "status",
        "linked_plan_id",
        "linked_observation_id",
    ]:
        val = getattr(data, field, None)
        if val is not None:
            setattr(agenda, field, val)

    await db.commit()
    await db.refresh(agenda)
    return agenda


async def delete_agenda(db: AsyncSession, school_id: int, act_id: int, agenda_id: int) -> bool:
    result = await db.execute(
        select(ResearchActivityAgenda).where(
            and_(
                ResearchActivityAgenda.id == agenda_id,
                ResearchActivityAgenda.activity_id == act_id,
                ResearchActivityAgenda.school_id == school_id,
            )
        )
    )
    agenda = result.scalar_one_or_none()
    if not agenda:
        return False

    activity = await get_activity(db, school_id, act_id)
    if activity and activity.agenda_count and activity.agenda_count > 0:
        activity.agenda_count -= 1

    await db.delete(agenda)
    await db.commit()
    return True


# ═══════════════════════════════════════════════
# 教研活动看板统计
# ═══════════════════════════════════════════════


async def get_dashboard_stats(db: AsyncSession, school_id: int) -> dict:
    total = (
        await db.execute(
            select(func.count())
            .select_from(ResearchActivity)
            .where(ResearchActivity.school_id == school_id)
        )
    ).scalar() or 0

    # 按状态
    status_q = (
        select(ResearchActivity.status, func.count())
        .where(ResearchActivity.school_id == school_id)
        .group_by(ResearchActivity.status)
    )
    status_rows = (await db.execute(status_q)).fetchall()
    status_map = {row[0]: row[1] for row in status_rows}

    # 参与人次
    total_participants = (
        await db.execute(
            select(func.count())
            .select_from(ResearchActivityParticipant)
            .where(ResearchActivityParticipant.school_id == school_id)
        )
    ).scalar() or 0

    # 议题统计
    total_agendas = (
        await db.execute(
            select(func.count())
            .select_from(ResearchActivityAgenda)
            .where(ResearchActivityAgenda.school_id == school_id)
        )
    ).scalar() or 0

    resolved_agendas = (
        await db.execute(
            select(func.count())
            .select_from(ResearchActivityAgenda)
            .where(
                and_(
                    ResearchActivityAgenda.school_id == school_id,
                    ResearchActivityAgenda.status == "resolved",
                )
            )
        )
    ).scalar() or 0

    # 按类型
    type_q = (
        select(ResearchActivity.activity_type, func.count())
        .where(ResearchActivity.school_id == school_id)
        .group_by(ResearchActivity.activity_type)
    )
    type_rows = (await db.execute(type_q)).fetchall()
    by_type = {row[0]: row[1] for row in type_rows}

    # 按学科
    subject_q = (
        select(ResearchActivity.subject_code, func.count())
        .where(ResearchActivity.school_id == school_id)
        .group_by(ResearchActivity.subject_code)
    )
    subject_rows = (await db.execute(subject_q)).fetchall()
    by_subject = {row[0]: row[1] for row in subject_rows}

    # 按月份 (YYYY-MM)
    month_q = (
        select(
            func.date_format(ResearchActivity.planned_at, "%Y-%m").label("month"),
            func.count(),
        )
        .where(ResearchActivity.school_id == school_id)
        .group_by("month")
        .order_by("month")
    )
    month_rows = (await db.execute(month_q)).fetchall()
    by_month = {row[0]: row[1] for row in month_rows}

    # Top组织者
    org_q = (
        select(ResearchActivity.organizer_id, func.count().label("act_count"))
        .where(ResearchActivity.school_id == school_id)
        .group_by(ResearchActivity.organizer_id)
        .order_by(func.count().desc())
        .limit(5)
    )
    org_rows = (await db.execute(org_q)).fetchall()
    org_ids = [row[0] for row in org_rows]
    org_name_map = await _get_user_names_batch(db, org_ids)
    top_organizers = [
        {"user_id": r[0], "name": org_name_map.get(r[0], f"用户{r[0]}"), "activity_count": r[1]}
        for r in org_rows
    ]

    return {
        "total_activities": total,
        "planned": status_map.get(ACT_PLANNED, 0),
        "in_progress": status_map.get(ACT_IN_PROGRESS, 0),
        "completed": status_map.get(ACT_COMPLETED, 0),
        "cancelled": status_map.get(ACT_CANCELLED, 0),
        "total_participants": total_participants,
        "total_agendas": total_agendas,
        "resolved_agendas": resolved_agendas,
        "by_type": by_type,
        "by_subject": by_subject,
        "by_month": by_month,
        "top_organizers": top_organizers,
    }


# ═══════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════


def _activity_to_dict(activity: ResearchActivity, name_map: dict[int, str]) -> dict:
    return {
        "id": activity.id,
        "school_id": activity.school_id,
        "title": activity.title,
        "description": activity.description,
        "activity_type": activity.activity_type,
        "subject_code": activity.subject_code,
        "grade_level": activity.grade_level,
        "planned_at": activity.planned_at,
        "planned_end_at": activity.planned_end_at,
        "actual_start_at": activity.actual_start_at,
        "actual_end_at": activity.actual_end_at,
        "location": activity.location,
        "status": activity.status,
        "status_updated_at": activity.status_updated_at,
        "cancel_reason": activity.cancel_reason,
        "organizer_id": activity.organizer_id,
        "organizer_name": name_map.get(activity.organizer_id, f"用户{activity.organizer_id}"),
        "summary": activity.summary,
        "decisions": activity.decisions or [],
        "attachments": activity.attachments or [],
        "linked_plan_ids": activity.linked_plan_ids or [],
        "linked_observation_ids": activity.linked_observation_ids or [],
        "participant_count": activity.participant_count or 0,
        "agenda_count": activity.agenda_count or 0,
        "created_at": activity.created_at,
        "updated_at": activity.updated_at,
    }
