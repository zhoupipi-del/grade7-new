"""
modules/growth/schemas.py — 成长档案 Pydantic 契约层

保留原有只读时间轴模型（TimelineItem / GrowthTimelineResponse），
新增 P0 重型契约：事件写入 / 周期快照 / 五维雷达 / 全息画像。
"""
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
#  原有：只读时间轴事件类型（7路融合）
# ═══════════════════════════════════════════════════════════

EVENT_TYPE_BEHAVIOR = "behavior"
EVENT_TYPE_SANCTION = "sanction"
EVENT_TYPE_SANCTION_REVOKED = "sanction_revoked"
EVENT_TYPE_ATTENDANCE = "attendance"
EVENT_TYPE_SCORE_LOG = "score_log"
EVENT_TYPE_RECOVERY = "recovery"
EVENT_TYPE_RISK_MILESTONE = "risk_milestone"
EVENT_TYPE_EVALUATION = "evaluation"


class TimelineItem(BaseModel):
    event_id: str = Field(..., description="事件唯一ID")
    event_type: str = Field(..., description="事件类型")
    occurred_at: datetime = Field(..., description="事件发生时间")
    event_date: date = Field(..., description="事件发生日期")
    title: str = Field(..., description="事件标题")
    description: Optional[str] = Field(None, description="事件详情")
    severity: str = Field(default="info", description="严重程度")
    related_id: Optional[int] = Field(None, description="关联表主键ID")
    source_table: Optional[str] = Field(None, description="数据源表名")

    class Config:
        from_attributes = True


class GrowthTimelineResponse(BaseModel):
    student_id: int
    student_name: str
    class_name: str
    total_events: int
    timeline: List[TimelineItem] = Field(default_factory=list)

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════
#  P0 新增：成长事件写入契约
# ═══════════════════════════════════════════════════════════

class TimelineEventCreate(BaseModel):
    """手动/系统注入成长事件"""
    student_id: int = Field(..., description="学生ID")
    dimension: str = Field(..., description="五育维度: academic/attendance/behavior/psychology/activity")
    severity: str = Field("info", description="级别: info/bonus/warning/critical")
    event_type: str = Field(..., max_length=50, description="事件标识，如 hw_missing, gap_critical")
    title: str = Field(..., max_length=200, description="事件标题")
    occurred_at: datetime = Field(..., description="事件真实发生时间")
    payload: Optional[Dict[str, Any]] = Field(None, description="多态结构化载荷")


class TimelineEventResponse(BaseModel):
    """成长事件响应"""
    id: int
    student_id: int
    dimension: str
    severity: str
    event_type: str
    title: str
    occurred_at: datetime
    payload: Optional[Dict[str, Any]] = None
    reporter_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════
#  P0 新增：周期快照契约
# ═══════════════════════════════════════════════════════════

class RadarDimensions(BaseModel):
    """五维雷达图得分"""
    academic: float = Field(..., ge=0.0, le=100.0, description="学业指数")
    attendance: float = Field(..., ge=0.0, le=100.0, description="考勤表现")
    behavior: float = Field(..., ge=0.0, le=100.0, description="日常品行")
    psychology: float = Field(..., ge=0.0, le=100.0, description="心理韧性")
    activity: float = Field(..., ge=0.0, le=100.0, description="活动实践")


class SnapshotMetricsSummary(BaseModel):
    """期末关键数量摘要"""
    total_absent_count: int = Field(0, description="累计缺勤次数")
    critical_gap_count: int = Field(0, description="当前顽固错题断层数")
    behavior_violation_count: int = Field(0, description="累计违纪次数")
    honor_count: int = Field(0, description="获得荣誉次数")
    additional_info: Dict[str, Any] = Field(default_factory=dict, description="额外扩展统计")


class GrowthSnapshotResponse(BaseModel):
    """周期快照响应"""
    id: int
    student_id: int
    snapshot_type: str = Field(..., description="monthly / semester")
    period_label: str = Field(..., description="时间标签")

    scores: RadarDimensions
    metrics_summary: SnapshotMetricsSummary

    teacher_comment: Optional[str] = Field(None, description="班主任评语")
    ai_growth_prescription: Optional[str] = Field(None, description="AI全息发展处方")
    created_at: datetime

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════
#  P0 新增：班主任评语 + 快照生成请求
# ═══════════════════════════════════════════════════════════

class TeacherCommentUpdate(BaseModel):
    """班主任手工录入评语"""
    teacher_comment: str = Field(..., min_length=5, max_length=2000, description="期末综合评语")


class SnapshotGenerateRequest(BaseModel):
    """快照生成请求"""
    student_id: int = Field(..., description="学生ID")
    snapshot_type: str = Field("monthly", description="monthly / semester")
    period_label: str = Field(..., description="时间标签，如 2026-07")


# ═══════════════════════════════════════════════════════════
#  P0 新增：全息成长主页契约
# ═══════════════════════════════════════════════════════════

class StudentHolisticProfile(BaseModel):
    """学生全息成长画像 — 所有数据的终极汇聚出口"""
    student_id: int
    student_name: str
    class_name: str

    current_snapshot: Optional[GrowthSnapshotResponse] = None
    historical_snapshots: List[GrowthSnapshotResponse] = Field(default_factory=list)
    recent_events: List[TimelineEventResponse] = Field(default_factory=list)

    # 原有7路融合时间轴（保留兼容）
    legacy_timeline: Optional[GrowthTimelineResponse] = None

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════
#  P0 新增：成长看板统计
# ═══════════════════════════════════════════════════════════

class GrowthDashboard(BaseModel):
    """成长档案看板"""
    total_students: int = Field(0, description="总学生数")
    total_events: int = Field(0, description="总事件数")
    total_snapshots: int = Field(0, description="总快照数")
    critical_events: int = Field(0, description="critical级事件数")
    warning_events: int = Field(0, description="warning级事件数")
    bonus_events: int = Field(0, description="bonus级事件数")
    dimension_distribution: List[Dict[str, Any]] = Field(default_factory=list, description="维度分布")
    recent_critical_events: List[TimelineEventResponse] = Field(default_factory=list, description="近期critical事件")
