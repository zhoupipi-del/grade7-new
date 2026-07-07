"""
modules/notifications/routers.py — 通知 API 端点

端点清单:
  GET  /api/v1/notifications/            — 通知列表（分页）
  GET  /api/v1/notifications/unread      — 未读计数
  PUT  /api/v1/notifications/{id}/read   — 标记单条已读
  PUT  /api/v1/notifications/read-all    — 全部已读
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.routers import get_current_user, get_db
from core.models import User
from .services import NotificationService
from .schemas import (
    NotificationOut,
    NotificationListResponse,
    UnreadCountResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["通知"])


# ═══════════════════════════════════════════════════════════════
# GET / — 通知列表（分页）
# ═══════════════════════════════════════════════════════════════

@router.get("/", response_model=NotificationListResponse)
async def list_notifications(
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
    type: Optional[str] = Query(None, description="按类型过滤: discipline_pending/discipline_activated/..."),
    is_read: Optional[bool] = Query(None, description="按已读状态过滤"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询当前用户的通知列表"""
    items, total = await NotificationService.list_notifications(
        db,
        recipient_id=current_user.id,
        limit=limit,
        offset=offset,
        type=type,
        is_read=is_read,
    )
    return NotificationListResponse(
        items=[NotificationOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ═══════════════════════════════════════════════════════════════
# GET /unread — 未读计数
# ═══════════════════════════════════════════════════════════════

@router.get("/unread", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的未读通知计数"""
    total, by_type = await NotificationService.get_unread_count(db, current_user.id)
    return UnreadCountResponse(unread_count=total, by_type=by_type)


# ═══════════════════════════════════════════════════════════════
# PUT /{notification_id}/read — 标记单条已读
# ═══════════════════════════════════════════════════════════════

@router.put("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """标记指定通知为已读"""
    success = await NotificationService.mark_as_read(
        db, notification_id=notification_id, recipient_id=current_user.id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="通知不存在、不属于您，或已经标记为已读",
        )
    await db.commit()
    return {"ok": True, "notification_id": notification_id}


# ═══════════════════════════════════════════════════════════════
# PUT /read-all — 全部已读
# ═══════════════════════════════════════════════════════════════

@router.put("/read-all")
async def mark_all_read(
    type: Optional[str] = Query(None, description="只标记指定类型的通知"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """标记当前用户的所有未读通知为已读"""
    count = await NotificationService.mark_all_as_read(
        db, recipient_id=current_user.id, type=type
    )
    await db.commit()
    return {"ok": True, "marked_count": count}
