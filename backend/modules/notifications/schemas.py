"""
modules/notifications/schemas.py — 通知 Pydantic 模型
"""

from datetime import datetime

from pydantic import BaseModel, Field

# ── 输出模型 ──


class NotificationOut(BaseModel):
    """通知输出"""

    id: int
    type: str
    title: str
    body: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    is_read: bool = False
    read_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    """通知分页响应"""

    items: list[NotificationOut]
    total: int
    limit: int
    offset: int


class UnreadCountResponse(BaseModel):
    """未读计数响应"""

    unread_count: int
    """总未读数"""

    by_type: dict = Field(default_factory=dict)
    """按类型分组的未读数，如 {"discipline_pending": 3, "discipline_activated": 1}"""
