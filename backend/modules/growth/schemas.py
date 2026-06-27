"""
modules/growth/schemas.py — 成长时间轴 Pydantic 模型

家长端时间轴响应模型。
所有文案已做脱敏柔化处理，突出"成长记录"而非"审判书"。
"""
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
#  时间轴事件类型枚举（内部使用）
# ═══════════════════════════════════════════════════════════

EVENT_TYPE_BEHAVIOR = "behavior"       # 日常行为记录（违纪/扣分）
EVENT_TYPE_SANCTION = "sanction"       # 行政处分（生效）
EVENT_TYPE_SANCTION_REVOKED = "sanction_revoked"  # 处分撤销（正向）
EVENT_TYPE_ATTENDANCE = "attendance"   # 考勤异常
EVENT_TYPE_EVALUATION = "evaluation"  # 素质评价得分变动


# ═══════════════════════════════════════════════════════════
#  时间轴单项响应模型
# ═══════════════════════════════════════════════════════════

class TimelineItem(BaseModel):
    """
    时间轴单项 — 统一结构，前端按 event_type 渲染不同颜色/图标
    """
    event_id: str = Field(..., description="事件唯一ID，格式: {type}_{id}")
    event_type: str = Field(..., description="事件类型: behavior/sanction/sanction_revoked/attendance")
    occurred_at: datetime = Field(..., description="事件发生时间（用于排序）")
    event_date: date = Field(..., description="事件发生日期（用于视图分组）")

    # ── 展示文案（已脱敏柔化）──
    title: str = Field(..., description="事件标题，如「行为提醒：上课迟到」")
    description: Optional[str] = Field(None, description="事件详情描述")
    severity: str = Field(default="info", description="严重程度: info/warning/danger/success")

    # ── 关联数据──
    related_id: Optional[int] = Field(None, description="关联表主键ID")
    source_table: Optional[str] = Field(None, description="数据源表名")

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════
#  时间轴完整响应模型
# ═══════════════════════════════════════════════════════════

class GrowthTimelineResponse(BaseModel):
    """
    GET /timeline/{student_id} 响应体

    包含学生基本信息和按时间倒序排列的成长事件列表。
    """
    student_id: int
    student_name: str
    class_name: str
    total_events: int

    timeline: List[TimelineItem] = Field(
        default_factory=list,
        description="时间轴事件列表，按 occurred_at DESC 排序"
    )

    class Config:
        from_attributes = True
