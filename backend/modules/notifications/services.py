"""
modules/notifications/services.py — 通知引擎服务层

核心能力:
  1. 创建通知（单条 / 按角色批量）
  2. 查询通知列表（分页 + 按类型过滤 + 按已读状态过滤）
  3. 标记已读（单条 / 全部已读）
  4. 未读计数
  5. 按角色查询用户列表
"""

import logging

from core.models import User, UserRole
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Notification

logger = logging.getLogger(__name__)


class NotificationService:
    """通知引擎 — 纯服务层，无状态"""

    # ═══════════════════════════════════════════════════════════
    # 创建通知
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create(
        db: AsyncSession,
        recipient_id: int,
        type: str,
        title: str,
        body: str | None = None,
        sender_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        school_id: int = 1,
    ) -> Notification:
        """
        创建一条通知

        Args:
            recipient_id: 收件人用户ID
            type: 通知类型 (见 NotificationType 常量)
            title: 标题 (≤200字符)
            body: 正文 (可选)
            sender_id: 发件人ID（系统生成时为 None）
            entity_type: 关联实体类型
            entity_id: 关联实体ID
            school_id: 学校ID（默认 1）

        Returns:
            创建的 Notification 对象
        """
        notification = Notification(
            school_id=school_id,
            recipient_id=recipient_id,
            sender_id=sender_id or None,
            type=type,
            title=title[:200],
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        db.add(notification)
        return notification

    @staticmethod
    async def notify_by_role(
        db: AsyncSession,
        school_id: int,
        role: UserRole,
        type: str,
        title: str,
        body: str | None = None,
        sender_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
    ) -> list[Notification]:
        """
        向指定角色的所有活跃用户发送通知

        Args:
            school_id: 学校ID
            role: 目标角色 (UserRole.GRADE_LEADER / UserRole.MS_ADMIN / ...)
            type: 通知类型
            title: 标题
            body: 正文
            sender_id: 发件人ID
            entity_type: 关联实体类型
            entity_id: 关联实体ID

        Returns:
            创建的 Notification 对象列表
        """
        users = await NotificationService.get_users_by_role(db, school_id, role)
        notifications = []
        for user in users:
            notif = await NotificationService.create(
                db,
                recipient_id=user.id,
                type=type,
                title=title,
                body=body,
                sender_id=sender_id,
                entity_type=entity_type,
                entity_id=entity_id,
                school_id=school_id,
            )
            notifications.append(notif)
        return notifications

    @staticmethod
    async def notify_users(
        db: AsyncSession,
        user_ids: list[int],
        type: str,
        title: str,
        body: str | None = None,
        sender_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        school_id: int = 1,
    ) -> list[Notification]:
        """
        向指定用户列表发送通知

        自动去重（同一用户不重复发送）
        """
        unique_ids = list(dict.fromkeys(user_ids))  # 保序去重
        notifications = []
        for uid in unique_ids:
            notif = await NotificationService.create(
                db,
                recipient_id=uid,
                type=type,
                title=title,
                body=body,
                sender_id=sender_id,
                entity_type=entity_type,
                entity_id=entity_id,
                school_id=school_id,
            )
            notifications.append(notif)
        return notifications

    # ═══════════════════════════════════════════════════════════
    # 查询用户
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_users_by_role(db: AsyncSession, school_id: int, role: UserRole) -> list[User]:
        """查询指定学校下指定角色的所有活跃用户"""
        result = await db.execute(
            select(User).where(
                User.school_id == school_id,
                User.role == role,
                User.is_active == True,
            )
        )
        return list(result.scalars().all())

    # ═══════════════════════════════════════════════════════════
    # 查询通知
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def list_notifications(
        db: AsyncSession,
        recipient_id: int,
        limit: int = 20,
        offset: int = 0,
        type: str | None = None,
        is_read: bool | None = None,
    ) -> tuple[list[Notification], int]:
        """
        查询收件人通知列表（分页）

        Args:
            recipient_id: 收件人用户ID
            limit: 每页条数
            offset: 偏移量
            type: 按类型过滤（可选）
            is_read: 按已读状态过滤（可选）

        Returns:
            (通知列表, 总数)
        """
        conditions = [Notification.recipient_id == recipient_id]
        if type:
            conditions.append(Notification.type == type)
        if is_read is not None:
            conditions.append(Notification.is_read == is_read)

        # 总数
        count_result = await db.execute(
            select(func.count()).select_from(Notification).where(*conditions)
        )
        total = count_result.scalar() or 0

        # 列表 — 按创建时间倒序
        result = await db.execute(
            select(Notification)
            .where(*conditions)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list(result.scalars().all())

        return items, total

    # ═══════════════════════════════════════════════════════════
    # 已读标记
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def mark_as_read(
        db: AsyncSession,
        notification_id: int,
        recipient_id: int,
    ) -> bool:
        """
        标记单条通知为已读

        双重校验: notification_id + recipient_id 防止越权

        Returns:
            True 如果成功标记，False 如果通知不存在或不属于该用户
        """
        from core.models import get_local_now

        result = await db.execute(
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.recipient_id == recipient_id,
                Notification.is_read == False,
            )
            .values(is_read=True, read_at=get_local_now())
        )
        return result.rowcount > 0

    @staticmethod
    async def mark_all_as_read(db: AsyncSession, recipient_id: int, type: str | None = None) -> int:
        """
        标记收件人的全部(或指定类型)未读通知为已读

        Returns:
            标记成功的通知数量
        """
        from core.models import get_local_now

        conditions = [
            Notification.recipient_id == recipient_id,
            Notification.is_read == False,
        ]
        if type:
            conditions.append(Notification.type == type)

        result = await db.execute(
            update(Notification).where(*conditions).values(is_read=True, read_at=get_local_now())
        )
        return result.rowcount

    # ═══════════════════════════════════════════════════════════
    # 未读计数
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_unread_count(db: AsyncSession, recipient_id: int) -> tuple[int, dict]:
        """
        获取未读计数

        Returns:
            (总未读数, {type: count} 按类型分组)
        """
        # 总未读数
        total_result = await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_id == recipient_id,
                Notification.is_read == False,
            )
        )
        total = total_result.scalar() or 0

        # 按类型分组
        type_counts = {}
        if total > 0:
            type_result = await db.execute(
                select(Notification.type, func.count())
                .where(
                    Notification.recipient_id == recipient_id,
                    Notification.is_read == False,
                )
                .group_by(Notification.type)
            )
            for row in type_result:
                type_counts[row[0]] = row[1]

        return total, type_counts
