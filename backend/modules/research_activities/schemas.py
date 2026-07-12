"""
research_activities/schemas.py — Pydantic 强类型校验契约
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime


# ──────────────────────────────────────────────
# 请求模型
# ──────────────────────────────────────────────
class ActivityCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    activity_type: str = Field("regular_meeting")
    subject_code: str = Field(..., description="学科代码")
    grade_level: Optional[str] = None
    planned_at: datetime = Field(..., description="计划开始时间")
    planned_end_at: Optional[datetime] = None
    location: Optional[str] = None
    linked_plan_ids: List[int] = Field(default=[])
    linked_observation_ids: List[int] = Field(default=[])
    participant_ids: List[int] = Field(default=[], description="初始参与人ID列表")


class ActivityUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    activity_type: Optional[str] = None
    grade_level: Optional[str] = None
    planned_at: Optional[datetime] = None
    planned_end_at: Optional[datetime] = None
    location: Optional[str] = None
    summary: Optional[str] = None
    decisions: Optional[List[str]] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    linked_plan_ids: Optional[List[int]] = None
    linked_observation_ids: Optional[List[int]] = None


class CancelReason(BaseModel):
    cancel_reason: str = Field("未说明原因")


class ParticipantAdd(BaseModel):
    user_id: int
    role: str = Field("participant", description="角色: organizer/presenter/recorder/participant")


class ParticipantUpdate(BaseModel):
    role: Optional[str] = None
    attendance_status: Optional[str] = None
    check_in_at: Optional[datetime] = None
    check_out_at: Optional[datetime] = None
    contribution_score: Optional[int] = Field(None, ge=1, le=5)
    contribution_note: Optional[str] = None
    note: Optional[str] = None


class AgendaCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    presenter_id: Optional[int] = None
    content: Optional[str] = None
    planned_duration: Optional[int] = Field(None, ge=1, le=300)
    linked_plan_id: Optional[int] = None
    linked_observation_id: Optional[int] = None


class AgendaUpdate(BaseModel):
    title: Optional[str] = None
    presenter_id: Optional[int] = None
    content: Optional[str] = None
    planned_duration: Optional[int] = None
    actual_duration: Optional[int] = None
    decision: Optional[str] = None
    status: Optional[str] = None
    linked_plan_id: Optional[int] = None
    linked_observation_id: Optional[int] = None


# ──────────────────────────────────────────────
# 响应模型
# ──────────────────────────────────────────────
class ParticipantResponse(BaseModel):
    id: int
    activity_id: int
    user_id: int
    user_name: Optional[str] = None
    role: str
    attendance_status: str
    check_in_at: Optional[datetime] = None
    check_out_at: Optional[datetime] = None
    contribution_score: Optional[int] = None
    contribution_note: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AgendaResponse(BaseModel):
    id: int
    activity_id: int
    seq: int
    title: str
    presenter_id: Optional[int] = None
    presenter_name: Optional[str] = None
    content: Optional[str] = None
    planned_duration: Optional[int] = None
    actual_duration: Optional[int] = None
    decision: Optional[str] = None
    status: str
    linked_plan_id: Optional[int] = None
    linked_observation_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ActivityResponse(BaseModel):
    id: int
    school_id: int
    title: str
    description: Optional[str] = None
    activity_type: str
    subject_code: str
    grade_level: Optional[str] = None
    planned_at: datetime
    planned_end_at: Optional[datetime] = None
    actual_start_at: Optional[datetime] = None
    actual_end_at: Optional[datetime] = None
    location: Optional[str] = None
    status: str
    status_updated_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    organizer_id: int
    organizer_name: Optional[str] = None
    summary: Optional[str] = None
    decisions: List[str] = []
    attachments: List[Dict[str, Any]] = []
    linked_plan_ids: List[int] = []
    linked_observation_ids: List[int] = []
    participant_count: int = 0
    agenda_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ActivityDetailResponse(ActivityResponse):
    """活动详情 — 含参与人和议题"""
    participants: List[ParticipantResponse] = []
    agendas: List[AgendaResponse] = []


class DashboardStats(BaseModel):
    """教研活动统计看板"""
    total_activities: int = 0
    planned: int = 0
    in_progress: int = 0
    completed: int = 0
    cancelled: int = 0
    total_participants: int = 0
    total_agendas: int = 0
    resolved_agendas: int = 0
    by_type: Dict[str, int] = {}
    by_subject: Dict[str, int] = {}
    by_month: Dict[str, int] = {}
    top_organizers: List[Dict[str, Any]] = []
