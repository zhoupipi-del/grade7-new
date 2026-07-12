"""
心理咨询预约与工作台 Pydantic 模型
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ─────────────────────────────────────────────────────────
# 时间槽位
# ─────────────────────────────────────────────────────────

class SlotCreateRequest(BaseModel):
    """心理老师开放可预约时段"""
    date: str = Field(..., description="日期 YYYY-MM-DD")
    start_time: str = Field(..., description="HH:MM")
    end_time: str = Field(..., description="HH:MM")
    location: Optional[str] = "心理咨询室"
    max_capacity: int = Field(default=1, ge=1, le=5)
    week_pattern: str = Field(default="every", description="every/odd/even")
    is_recurring: bool = False

    class Config:
        from_attributes = True


class SlotResponse(BaseModel):
    id: int
    teacher_id: int
    teacher_name: Optional[str] = None
    date: str
    start_time: str
    end_time: str
    location: Optional[str] = None
    max_capacity: int
    current_booked: int
    status: str
    week_pattern: str
    is_recurring: bool
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class SlotListResponse(BaseModel):
    status: str = "success"
    slots: List[SlotResponse]


# ─────────────────────────────────────────────────────────
# 预约申请
# ─────────────────────────────────────────────────────────

class AppointmentCreateRequest(BaseModel):
    """学生自荐 / 班主任转介 预约"""
    student_id: int
    slot_id: int
    source: str = Field(..., description="self/teacher/parent")
    reason_summary: Optional[str] = Field(
        default=None, max_length=200,
        description="申请理由摘要(可对外展示)",
    )
    risk_flag: str = Field(default="green", description="green/yellow/orange/red")

    class Config:
        from_attributes = True


class AppointmentUpdateRequest(BaseModel):
    """心理老师审核/更新预约状态"""
    status: Optional[str] = Field(
        default=None, description="confirmed/cancelled/completed/no_show",
    )
    risk_flag: Optional[str] = Field(default=None, description="green/yellow/orange/red")
    counselor_note: Optional[str] = Field(default=None, max_length=300)

    class Config:
        from_attributes = True


class AppointmentResponse(BaseModel):
    id: int
    student_id: int
    student_name: Optional[str] = None
    applicant_id: int
    applicant_name: Optional[str] = None
    slot_id: int
    source: str
    reason_summary: Optional[str] = None
    status: str
    risk_flag: str
    counselor_note: Optional[str] = None
    slot_date: Optional[str] = None
    slot_time: Optional[str] = None
    slot_location: Optional[str] = None
    created_at: Optional[str] = None
    confirmed_at: Optional[str] = None
    completed_at: Optional[str] = None

    class Config:
        from_attributes = True


class AppointmentListResponse(BaseModel):
    status: str = "success"
    appointments: List[AppointmentResponse]
    total: int


# ─────────────────────────────────────────────────────────
# 咨询记录 (工作台核心)
# ─────────────────────────────────────────────────────────

class ConsultRecordCreateRequest(BaseModel):
    """心理老师写实 — 提交咨询记录"""
    appointment_id: int
    student_id: int
    clog_plaintext: str = Field(
        ..., description="咨询日志明文 — 服务层自动加密落盘",
    )
    risk_level: str = Field(default="green", description="green/yellow/orange/red")
    consult_category: Optional[str] = Field(
        default=None, description="emotion/interpersonal/academic/family/self_harm/other",
    )
    is_crisis: bool = False
    is_referred: bool = False
    referral_target: Optional[str] = None
    followup_date: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    session_duration_min: Optional[int] = Field(default=None, ge=1, le=480)


class ConsultRecordResponse(BaseModel):
    """咨询记录响应 — clog 根据角色决定是否解密"""
    id: int
    appointment_id: int
    student_id: int
    student_name: Optional[str] = None
    counselor_id: int
    counselor_name: Optional[str] = None
    clog_display: str = Field(..., description="解密后的正文 / 脱敏摘要")
    risk_level: str
    consult_category: Optional[str] = None
    is_crisis: bool
    is_referred: bool
    referral_target: Optional[str] = None
    followup_date: Optional[str] = None
    session_duration_min: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class ConsultRecordListResponse(BaseModel):
    status: str = "success"
    records: List[ConsultRecordResponse]
    total: int


# ─────────────────────────────────────────────────────────
# 工作台聚合统计
# ─────────────────────────────────────────────────────────

class CounselorStatsResponse(BaseModel):
    status: str = "success"
    counselor_id: int
    total_sessions: int
    total_students: int
    crisis_count: int
    referral_count: int
    avg_duration_min: Optional[float] = None
    risk_distribution: dict = Field(default_factory=dict)
    category_distribution: dict = Field(default_factory=dict)
    upcoming_appointments: int
    pending_appointments: int
