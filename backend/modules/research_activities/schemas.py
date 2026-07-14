"""
research_activities/schemas.py — Pydantic 强类型校验契约
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# 请求模型
# ──────────────────────────────────────────────
class ActivityCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    activity_type: str = Field("regular_meeting")
    subject_code: str = Field(..., description="学科代码")
    grade_level: str | None = None
    planned_at: datetime = Field(..., description="计划开始时间")
    planned_end_at: datetime | None = None
    location: str | None = None
    linked_plan_ids: list[int] = Field(default=[])
    linked_observation_ids: list[int] = Field(default=[])
    participant_ids: list[int] = Field(default=[], description="初始参与人ID列表")


class ActivityUpdate(BaseModel):
    title: str | None = Field(None, max_length=200)
    description: str | None = None
    activity_type: str | None = None
    grade_level: str | None = None
    planned_at: datetime | None = None
    planned_end_at: datetime | None = None
    location: str | None = None
    summary: str | None = None
    decisions: list[str] | None = None
    attachments: list[dict[str, Any]] | None = None
    linked_plan_ids: list[int] | None = None
    linked_observation_ids: list[int] | None = None


class CancelReason(BaseModel):
    cancel_reason: str = Field("未说明原因")


class ParticipantAdd(BaseModel):
    user_id: int
    role: str = Field("participant", description="角色: organizer/presenter/recorder/participant")


class ParticipantUpdate(BaseModel):
    role: str | None = None
    attendance_status: str | None = None
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    contribution_score: int | None = Field(None, ge=1, le=5)
    contribution_note: str | None = None
    note: str | None = None


class AgendaCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    presenter_id: int | None = None
    content: str | None = None
    planned_duration: int | None = Field(None, ge=1, le=300)
    linked_plan_id: int | None = None
    linked_observation_id: int | None = None


class AgendaUpdate(BaseModel):
    title: str | None = None
    presenter_id: int | None = None
    content: str | None = None
    planned_duration: int | None = None
    actual_duration: int | None = None
    decision: str | None = None
    status: str | None = None
    linked_plan_id: int | None = None
    linked_observation_id: int | None = None


# ──────────────────────────────────────────────
# 响应模型
# ──────────────────────────────────────────────
class ParticipantResponse(BaseModel):
    id: int
    activity_id: int
    user_id: int
    user_name: str | None = None
    role: str
    attendance_status: str
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    contribution_score: int | None = None
    contribution_note: str | None = None
    note: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class AgendaResponse(BaseModel):
    id: int
    activity_id: int
    seq: int
    title: str
    presenter_id: int | None = None
    presenter_name: str | None = None
    content: str | None = None
    planned_duration: int | None = None
    actual_duration: int | None = None
    decision: str | None = None
    status: str
    linked_plan_id: int | None = None
    linked_observation_id: int | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ActivityResponse(BaseModel):
    id: int
    school_id: int
    title: str
    description: str | None = None
    activity_type: str
    subject_code: str
    grade_level: str | None = None
    planned_at: datetime
    planned_end_at: datetime | None = None
    actual_start_at: datetime | None = None
    actual_end_at: datetime | None = None
    location: str | None = None
    status: str
    status_updated_at: datetime | None = None
    cancel_reason: str | None = None
    organizer_id: int
    organizer_name: str | None = None
    summary: str | None = None
    decisions: list[str] = []
    attachments: list[dict[str, Any]] = []
    linked_plan_ids: list[int] = []
    linked_observation_ids: list[int] = []
    participant_count: int = 0
    agenda_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ActivityDetailResponse(ActivityResponse):
    """活动详情 — 含参与人和议题"""

    participants: list[ParticipantResponse] = []
    agendas: list[AgendaResponse] = []


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
    by_type: dict[str, int] = {}
    by_subject: dict[str, int] = {}
    by_month: dict[str, int] = {}
    top_organizers: list[dict[str, Any]] = []
