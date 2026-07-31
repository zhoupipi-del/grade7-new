"""
modules/notifications/routers.py — 通知 API 端点

端点清单:
  GET  /api/v1/notifications/            — 通知列表（分页）
  GET  /api/v1/notifications/unread      — 未读计数
  PUT  /api/v1/notifications/{id}/read   — 标记单条已读
  PUT  /api/v1/notifications/read-all    — 全部已读
  GET  /api/v1/notifications/stream      — SSE 实时事件流（CEP复合预警泵站）
"""

import asyncio
import json
import logging

from core.models import User, UserRole
from core.redis_client import get_redis
from core.routers import get_current_user, get_db, require_role
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from .schemas import (
    NotificationListResponse,
    NotificationOut,
    UnreadCountResponse,
)
from .services import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["通知"])

# SSE 订阅 RBAC 白名单 — 只有这些角色有权接收实时复合预警
SSE_ALLOWED_ROLES = {UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER}


# ═══════════════════════════════════════════════════════════════
# GET / — 通知列表（分页）
# ═══════════════════════════════════════════════════════════════


@router.get("/", response_model=NotificationListResponse)
async def list_notifications(
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
    type: str | None = Query(
        None, description="按类型过滤: discipline_pending/discipline_activated/..."
    ),
    is_read: bool | None = Query(None, description="按已读状态过滤"),
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
    type: str | None = Query(None, description="只标记指定类型的通知"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """标记当前用户的所有未读通知为已读"""
    count = await NotificationService.mark_all_as_read(db, recipient_id=current_user.id, type=type)
    await db.commit()
    return {"ok": True, "marked_count": count}


# ═══════════════════════════════════════════════════════════════
# GET /stream — SSE 实时事件流 (CEP复合预警泵站)
# ═══════════════════════════════════════════════════════════════


@router.get("/stream")
async def stream_composite_alerts(
    request: Request,
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    """
    SSE 实时事件流 — 将 CEP 复合预警毫秒级泵出到前端

    RBAC 裁剪:
      - MS_ADMIN / GRADE_LEADER / CLASS_TEACHER 可订阅
      - 多租户红线: payload.school_id == current_user.school_id

    前端用法:
      const es = new EventSource('/api/v1/notifications/stream', { withCredentials: true })
      es.addEventListener('COMPOSITE_ALERT', (e) => {
        const payload = JSON.parse(e.data)
        // payload = { type, school_id, student_id, alert_id, title, summary, trigger, triggered_at, created_at }
      })
    """
    # ── RBAC 铁闸 ──
    user_role = current_user.role
    if isinstance(user_role, str):
        user_role = UserRole(user_role)
    if user_role not in SSE_ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权订阅实时预警流",
        )

    # ── Redis 就绪检查 ──
    redis = get_redis()
    if not redis:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis 服务暂不可用，SSE 泵站无法启动",
        )

    school_id = current_user.school_id
    user_id = current_user.id

    async def event_generator():
        pubsub = redis.pubsub()
        await pubsub.subscribe("wings:notifications:popup")
        logger.info(f"SSE connected: user={user_id} school={school_id}")
        try:
            while True:
                # 断连检测 — 前端关闭 EventSource 时及时退出
                if await request.is_disconnected():
                    logger.info(f"SSE client disconnected: user={user_id}")
                    break

                # 阻塞式轮询 Redis Pub/Sub，timeout=0.5s 防止忙等
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=0.5,
                )

                if message and message.get("type") == "message":
                    try:
                        payload = json.loads(message["data"])
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(f"SSE: invalid JSON from Redis, user={user_id}")
                        continue

                    # 多租户红线 — 只泵出属于当前用户学校的预警
                    if payload.get("school_id") != school_id:
                        continue

                    yield {
                        "event": "COMPOSITE_ALERT",
                        "id": str(payload.get("alert_id", "")),
                        "data": json.dumps(payload, ensure_ascii=False),
                    }

        except asyncio.CancelledError:
            logger.info(f"SSE generator cancelled: user={user_id}")
        finally:
            await pubsub.unsubscribe("wings:notifications:popup")
            await pubsub.aclose()
            logger.info(f"SSE pubsub cleaned up: user={user_id}")

    # ping=15: 每15秒自动发心跳注释行，防止 Nginx/浏览器超时断连
    return EventSourceResponse(event_generator(), ping=15)
