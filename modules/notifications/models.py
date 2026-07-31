"""
modules/notifications/models.py — 通知数据模型

设计原则:
  - 每一条通知 = 一个确定的事件 + 一个收件人
  - entity_type/entity_id 提供溯源链接（前端可据此跳转到详情页）
  - is_read 由前端轮询后调用 PUT /read 标记
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, String, Text, Boolean, DateTime,
    ForeignKey, Index, select,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Base, SchoolMixin, get_local_now


# ── 通知类型枚举 ──

class NotificationType:
    """通知类型常量 — 用于前端路由"""
    DISCIPLINE_PENDING = "discipline_pending"           # 新处分待初审（→年级组长）
    DISCIPLINE_GL_APPROVED = "discipline_gl_approved"   # 年级组长初审通过（→德育处）
    DISCIPLINE_ACTIVATED = "discipline_activated"        # 处分正式生效（→班主任）
    DISCIPLINE_REJECTED = "discipline_rejected"          # 处分被驳回（→班主任/多方）
    DISCIPLINE_REVOKED = "discipline_revoked"            # 处分已撤销（→多方）
    DISCIPLINE_ESCALATION = "discipline_escalation"      # 违纪自动升级为处分

    # Phase 4: 家校申诉通知类型
    APPEAL_CREATED = "appeal_created"          # 新申诉已提交（→德育处）
    APPEAL_ACCEPTED = "appeal_accepted"        # 申诉通过、处分已撤销（→班主任+年级组长）
    APPEAL_REJECTED = "appeal_rejected"        # 申诉驳回（→班主任）

    # 前端路由映射
    ENTITY_ROUTES = {
        "discipline_sanction": "/discipline/sanctions/",
        "sanction_appeal": "/discipline/appeals/",
    }


# ═══════════════════════════════════════════════════════════════
# 通知表
# ═══════════════════════════════════════════════════════════════

class Notification(Base, SchoolMixin):
    """
    系统通知表

    每条通知:
      - 有明确的收件人 (recipient_id)
      - 有可选的发件人 (sender_id, 系统自动生成时为 NULL)
      - 有关联的业务实体 (entity_type + entity_id, 用于前端跳转)
      - 有已读/未读状态
    """
    __tablename__ = "notifications"

    id = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ── 收/发件人 ──
    recipient_id = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True,
        comment="收件人"
    )
    sender_id = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True, index=True,
        comment="发件人（系统生成时为 NULL）"
    )

    # ── 通知类型 ──
    type = mapped_column(
        String(50), nullable=False, index=True,
        comment="通知类型: discipline_pending/discipline_activated/..."
    )

    # ── 内容 ──
    title = mapped_column(
        String(200), nullable=False,
        comment="通知标题"
    )
    body = mapped_column(
        Text, nullable=True,
        comment="通知正文"
    )

    # ── 关联实体（溯源链接） ──
    entity_type = mapped_column(
        String(50), nullable=True,
        comment="关联实体类型: discipline_sanction / behavior_record / ..."
    )
    entity_id = mapped_column(
        BigInteger, nullable=True,
        comment="关联实体 ID, 配合 entity_type 构建跳转链接"
    )

    # ── 状态 ──
    is_read = mapped_column(
        Boolean, default=False, nullable=False, index=True,
        comment="是否已读"
    )
    read_at = mapped_column(
        DateTime, nullable=True,
        comment="已读时间"
    )

    # ── 时间 ──
    created_at = mapped_column(
        DateTime, default=get_local_now, nullable=False,
        comment="通知创建时间"
    )

    # ── 关系 ──
    recipient = None  # 由 core.User 反向关系提供
    sender = None     # 由 core.User 反向关系提供

    __table_args__ = (
        Index("idx_notif_recipient_read", "recipient_id", "is_read"),
        Index("idx_notif_school_type", "school_id", "type"),
        Index("idx_notif_entity", "entity_type", "entity_id"),
    )

    def __repr__(self):
        return f"<Notification id={self.id} type={self.type} recipient={self.recipient_id} read={self.is_read}>"
