"""
research_activities/routers.py — 教研活动管理 API 网关

端点清单 (17个):
  POST   /                              创建活动
  GET    /                              活动列表(分页+筛选)
  GET    /dashboard                     教研活动统计看板
  GET    /{act_id}                      活动详情(含参与人+议题)
  PUT    /{act_id}                      更新活动
  DELETE /{act_id}                      删除活动(仅planned/cancelled)

  POST   /{act_id}/start                启动活动 (PLANNED→IN_PROGRESS)
  POST   /{act_id}/complete             完成活动 (IN_PROGRESS→COMPLETED)
  POST   /{act_id}/cancel               取消活动 (PLANNED→CANCELLED)

  POST   /{act_id}/participants         添加参与人
  GET    /{act_id}/participants         参与人列表
  PUT    /{act_id}/participants/{pid}   更新参与人(签到/贡献度)
  DELETE /{act_id}/participants/{pid}   移除参与人

  POST   /{act_id}/agendas              添加议题
  GET    /{act_id}/agendas              议题列表
  PUT    /{act_id}/agendas/{aid}        更新议题(讨论记录/决议)
  DELETE /{act_id}/agendas/{aid}        删除议题
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from core.routers import get_db, get_current_user
from core.models import User
from . import schemas, services
from .models import (
    ACT_PLANNED, ACT_IN_PROGRESS, ACT_COMPLETED, ACT_CANCELLED,
)

router = APIRouter(tags=["教研活动管理"])

ROLE_MS_ADMIN = "MS_ADMIN"
ROLE_GRADE_LEADER = "GRADE_LEADER"
ROLE_CLASS_TEACHER = "CLASS_TEACHER"


def _can_manage(user: User, organizer_id: int) -> bool:
    if (user.role or "").upper() == ROLE_MS_ADMIN:
        return True
    if (user.role or "").upper() == ROLE_GRADE_LEADER:
        return True
    if (user.role or "").upper() == ROLE_CLASS_TEACHER and user.id == organizer_id:
        return True
    return False


# ═══════════════════════════════════════════════
# 活动 CRUD
# ═══════════════════════════════════════════════

@router.post("/", response_model=schemas.ActivityDetailResponse, status_code=201)
async def api_create_activity(
    payload: schemas.ActivityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建教研活动"""
    if (current_user.role or "").upper() not in (ROLE_MS_ADMIN, ROLE_GRADE_LEADER, ROLE_CLASS_TEACHER):
        raise HTTPException(403, "无权创建教研活动")

    activity = await services.create_activity(
        db, current_user.school_id, current_user.id, payload,
    )

    # 获取参与人和议题
    participants, _ = await services.list_participants(db, current_user.school_id, activity.id)
    agendas, _ = await services.list_agendas(db, current_user.school_id, activity.id)

    org_name = await services._get_user_name(db, activity.organizer_id)
    base = services._activity_to_dict(activity, {activity.organizer_id: org_name})
    return {**base, "participants": participants, "agendas": agendas}


@router.get("/")
async def api_list_activities(
    subject_code: Optional[str] = Query(None),
    activity_type: Optional[str] = Query(None),
    act_status: Optional[str] = Query(None, alias="status"),
    organizer_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """活动列表"""
    items, total = await services.list_activities(
        db, current_user.school_id,
        subject_code=subject_code,
        activity_type=activity_type,
        status=act_status,
        organizer_id=organizer_id,
        page=page, page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/dashboard", response_model=schemas.DashboardStats)
async def api_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """教研活动统计看板"""
    return await services.get_dashboard_stats(db, current_user.school_id)


@router.get("/{act_id}", response_model=schemas.ActivityDetailResponse)
async def api_get_activity(
    act_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """活动详情 (含参与人+议题)"""
    activity = await services.get_activity(db, current_user.school_id, act_id)
    if not activity:
        raise HTTPException(404, "活动不存在")

    participants, _ = await services.list_participants(db, current_user.school_id, act_id)
    agendas, _ = await services.list_agendas(db, current_user.school_id, act_id)

    org_name = await services._get_user_name(db, activity.organizer_id)
    base = services._activity_to_dict(activity, {activity.organizer_id: org_name})
    return {**base, "participants": participants, "agendas": agendas}


@router.put("/{act_id}", response_model=schemas.ActivityResponse)
async def api_update_activity(
    act_id: int,
    payload: schemas.ActivityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新活动"""
    activity = await services.get_activity(db, current_user.school_id, act_id)
    if not activity:
        raise HTTPException(404, "活动不存在")
    if not _can_manage(current_user, activity.organizer_id):
        raise HTTPException(403, "无权修改他人活动")

    updated = await services.update_activity(db, current_user.school_id, act_id, payload)
    if not updated:
        raise HTTPException(400, "更新失败: 活动不存在或当前状态不允许修改")

    org_name = await services._get_user_name(db, updated.organizer_id)
    return services._activity_to_dict(updated, {updated.organizer_id: org_name})


@router.delete("/{act_id}")
async def api_delete_activity(
    act_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除活动 (仅planned/cancelled可删)"""
    activity = await services.get_activity(db, current_user.school_id, act_id)
    if not activity:
        raise HTTPException(404, "活动不存在")
    if not _can_manage(current_user, activity.organizer_id):
        raise HTTPException(403, "无权删除他人活动")

    ok = await services.delete_activity(db, current_user.school_id, act_id)
    if not ok:
        raise HTTPException(400, "删除失败: 活动不存在或进行中/已完成不允许删除")
    return {"message": "已删除"}


# ═══════════════════════════════════════════════
# 状态机流转
# ═══════════════════════════════════════════════

@router.post("/{act_id}/start", response_model=schemas.ActivityResponse)
async def api_start_activity(
    act_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """启动活动 (PLANNED → IN_PROGRESS)"""
    activity = await services.get_activity(db, current_user.school_id, act_id)
    if not activity:
        raise HTTPException(404, "活动不存在")
    if not _can_manage(current_user, activity.organizer_id):
        raise HTTPException(403, "无权操作")

    activity, err = await services.transition_status(
        db, current_user.school_id, act_id, ACT_IN_PROGRESS, current_user.id,
    )
    if err:
        raise HTTPException(400, err)
    org_name = await services._get_user_name(db, activity.organizer_id)
    return services._activity_to_dict(activity, {activity.organizer_id: org_name})


@router.post("/{act_id}/complete", response_model=schemas.ActivityResponse)
async def api_complete_activity(
    act_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """完成活动 (IN_PROGRESS → COMPLETED)"""
    activity = await services.get_activity(db, current_user.school_id, act_id)
    if not activity:
        raise HTTPException(404, "活动不存在")
    if not _can_manage(current_user, activity.organizer_id):
        raise HTTPException(403, "无权操作")

    activity, err = await services.transition_status(
        db, current_user.school_id, act_id, ACT_COMPLETED, current_user.id,
    )
    if err:
        raise HTTPException(400, err)
    org_name = await services._get_user_name(db, activity.organizer_id)
    return services._activity_to_dict(activity, {activity.organizer_id: org_name})


@router.post("/{act_id}/cancel", response_model=schemas.ActivityResponse)
async def api_cancel_activity(
    act_id: int,
    payload: schemas.CancelReason,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取消活动 (PLANNED → CANCELLED)"""
    activity = await services.get_activity(db, current_user.school_id, act_id)
    if not activity:
        raise HTTPException(404, "活动不存在")
    if not _can_manage(current_user, activity.organizer_id):
        raise HTTPException(403, "无权操作")

    activity, err = await services.transition_status(
        db, current_user.school_id, act_id, ACT_CANCELLED, current_user.id,
        cancel_reason=payload.cancel_reason,
    )
    if err:
        raise HTTPException(400, err)
    org_name = await services._get_user_name(db, activity.organizer_id)
    return services._activity_to_dict(activity, {activity.organizer_id: org_name})


# ═══════════════════════════════════════════════
# 参与人员管理
# ═══════════════════════════════════════════════

@router.post("/{act_id}/participants", response_model=schemas.ParticipantResponse, status_code=201)
async def api_add_participant(
    act_id: int,
    payload: schemas.ParticipantAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """添加参与人"""
    activity = await services.get_activity(db, current_user.school_id, act_id)
    if not activity:
        raise HTTPException(404, "活动不存在")
    if not _can_manage(current_user, activity.organizer_id):
        raise HTTPException(403, "无权添加参与人")

    p = await services.add_participant(db, current_user.school_id, act_id, payload)
    if not p:
        raise HTTPException(400, "添加失败: 活动不存在或该用户已在参与人列表中")

    user_name = await services._get_user_name(db, p.user_id)
    return {
        "id": p.id, "activity_id": p.activity_id,
        "user_id": p.user_id, "user_name": user_name,
        "role": p.role, "attendance_status": p.attendance_status,
        "check_in_at": p.check_in_at, "check_out_at": p.check_out_at,
        "contribution_score": p.contribution_score,
        "contribution_note": p.contribution_note,
        "note": p.note, "created_at": p.created_at,
    }


@router.get("/{act_id}/participants")
async def api_list_participants(
    act_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """参与人列表"""
    activity = await services.get_activity(db, current_user.school_id, act_id)
    if not activity:
        raise HTTPException(404, "活动不存在")

    items, total = await services.list_participants(db, current_user.school_id, act_id)
    return {"items": items, "total": total}


@router.put("/{act_id}/participants/{pid}", response_model=schemas.ParticipantResponse)
async def api_update_participant(
    act_id: int,
    pid: int,
    payload: schemas.ParticipantUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新参与人 (签到/贡献度)"""
    activity = await services.get_activity(db, current_user.school_id, act_id)
    if not activity:
        raise HTTPException(404, "活动不存在")
    if not _can_manage(current_user, activity.organizer_id):
        raise HTTPException(403, "无权操作")

    p = await services.update_participant(db, current_user.school_id, act_id, pid, payload)
    if not p:
        raise HTTPException(404, "参与人不存在")

    user_name = await services._get_user_name(db, p.user_id)
    return {
        "id": p.id, "activity_id": p.activity_id,
        "user_id": p.user_id, "user_name": user_name,
        "role": p.role, "attendance_status": p.attendance_status,
        "check_in_at": p.check_in_at, "check_out_at": p.check_out_at,
        "contribution_score": p.contribution_score,
        "contribution_note": p.contribution_note,
        "note": p.note, "created_at": p.created_at,
    }


@router.delete("/{act_id}/participants/{pid}")
async def api_remove_participant(
    act_id: int,
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """移除参与人"""
    activity = await services.get_activity(db, current_user.school_id, act_id)
    if not activity:
        raise HTTPException(404, "活动不存在")
    if not _can_manage(current_user, activity.organizer_id):
        raise HTTPException(403, "无权操作")

    ok = await services.remove_participant(db, current_user.school_id, act_id, pid)
    if not ok:
        raise HTTPException(404, "参与人不存在")
    return {"message": "已移除"}


# ═══════════════════════════════════════════════
# 议题/议程管理
# ═══════════════════════════════════════════════

@router.post("/{act_id}/agendas", response_model=schemas.AgendaResponse, status_code=201)
async def api_create_agenda(
    act_id: int,
    payload: schemas.AgendaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """添加议题"""
    activity = await services.get_activity(db, current_user.school_id, act_id)
    if not activity:
        raise HTTPException(404, "活动不存在")
    if not _can_manage(current_user, activity.organizer_id):
        raise HTTPException(403, "无权添加议题")

    agenda = await services.create_agenda(db, current_user.school_id, act_id, payload)
    if not agenda:
        raise HTTPException(500, "议题创建失败")

    presenter_name = None
    if agenda.presenter_id:
        presenter_name = await services._get_user_name(db, agenda.presenter_id)
    return {
        "id": agenda.id, "activity_id": agenda.activity_id,
        "seq": agenda.seq, "title": agenda.title,
        "presenter_id": agenda.presenter_id, "presenter_name": presenter_name,
        "content": agenda.content,
        "planned_duration": agenda.planned_duration,
        "actual_duration": agenda.actual_duration,
        "decision": agenda.decision, "status": agenda.status,
        "linked_plan_id": agenda.linked_plan_id,
        "linked_observation_id": agenda.linked_observation_id,
        "created_at": agenda.created_at, "updated_at": agenda.updated_at,
    }


@router.get("/{act_id}/agendas")
async def api_list_agendas(
    act_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """议题列表"""
    activity = await services.get_activity(db, current_user.school_id, act_id)
    if not activity:
        raise HTTPException(404, "活动不存在")

    items, total = await services.list_agendas(db, current_user.school_id, act_id)
    return {"items": items, "total": total}


@router.put("/{act_id}/agendas/{aid}", response_model=schemas.AgendaResponse)
async def api_update_agenda(
    act_id: int,
    aid: int,
    payload: schemas.AgendaUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新议题 (讨论记录/决议)"""
    activity = await services.get_activity(db, current_user.school_id, act_id)
    if not activity:
        raise HTTPException(404, "活动不存在")
    if not _can_manage(current_user, activity.organizer_id):
        raise HTTPException(403, "无权操作")

    agenda = await services.update_agenda(db, current_user.school_id, act_id, aid, payload)
    if not agenda:
        raise HTTPException(404, "议题不存在")

    presenter_name = None
    if agenda.presenter_id:
        presenter_name = await services._get_user_name(db, agenda.presenter_id)
    return {
        "id": agenda.id, "activity_id": agenda.activity_id,
        "seq": agenda.seq, "title": agenda.title,
        "presenter_id": agenda.presenter_id, "presenter_name": presenter_name,
        "content": agenda.content,
        "planned_duration": agenda.planned_duration,
        "actual_duration": agenda.actual_duration,
        "decision": agenda.decision, "status": agenda.status,
        "linked_plan_id": agenda.linked_plan_id,
        "linked_observation_id": agenda.linked_observation_id,
        "created_at": agenda.created_at, "updated_at": agenda.updated_at,
    }


@router.delete("/{act_id}/agendas/{aid}")
async def api_delete_agenda(
    act_id: int,
    aid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除议题"""
    activity = await services.get_activity(db, current_user.school_id, act_id)
    if not activity:
        raise HTTPException(404, "活动不存在")
    if not _can_manage(current_user, activity.organizer_id):
        raise HTTPException(403, "无权操作")

    ok = await services.delete_agenda(db, current_user.school_id, act_id, aid)
    if not ok:
        raise HTTPException(404, "议题不存在")
    return {"message": "已删除"}
