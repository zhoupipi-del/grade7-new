"""
心理咨询预约与工作台 Pydantic 模型
"""

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────
# 时间槽位
# ─────────────────────────────────────────────────────────


class SlotCreateRequest(BaseModel):
    """心理老师开放可预约时段"""

    date: str = Field(..., description="日期 YYYY-MM-DD")
    start_time: str = Field(..., description="HH:MM")
    end_time: str = Field(..., description="HH:MM")
    location: str | None = "心理咨询室"
    max_capacity: int = Field(default=1, ge=1, le=5)
    week_pattern: str = Field(default="every", description="every/odd/even")
    is_recurring: bool = False

    class Config:
        from_attributes = True


class SlotResponse(BaseModel):
    id: int
    teacher_id: int
    teacher_name: str | None = None
    date: str
    start_time: str
    end_time: str
    location: str | None = None
    max_capacity: int
    current_booked: int
    status: str
    week_pattern: str
    is_recurring: bool
    created_at: str | None = None

    class Config:
        from_attributes = True


class SlotListResponse(BaseModel):
    status: str = "success"
    slots: list[SlotResponse]


# ─────────────────────────────────────────────────────────
# 预约申请
# ─────────────────────────────────────────────────────────


class AppointmentCreateRequest(BaseModel):
    """学生自荐 / 班主任转介 预约"""

    student_id: int
    slot_id: int
    source: str = Field(..., description="self/teacher/parent")
    reason_summary: str | None = Field(
        default=None,
        max_length=200,
        description="申请理由摘要(可对外展示)",
    )
    risk_flag: str = Field(default="green", description="green/yellow/orange/red")

    class Config:
        from_attributes = True


class AppointmentUpdateRequest(BaseModel):
    """心理老师审核/更新预约状态"""

    status: str | None = Field(
        default=None,
        description="confirmed/cancelled/completed/no_show",
    )
    risk_flag: str | None = Field(default=None, description="green/yellow/orange/red")
    counselor_note: str | None = Field(default=None, max_length=300)

    class Config:
        from_attributes = True


class AppointmentResponse(BaseModel):
    id: int
    student_id: int
    student_name: str | None = None
    applicant_id: int
    applicant_name: str | None = None
    slot_id: int
    source: str
    reason_summary: str | None = None
    status: str
    risk_flag: str
    counselor_note: str | None = None
    slot_date: str | None = None
    slot_time: str | None = None
    slot_location: str | None = None
    created_at: str | None = None
    confirmed_at: str | None = None
    completed_at: str | None = None

    class Config:
        from_attributes = True


class AppointmentListResponse(BaseModel):
    status: str = "success"
    appointments: list[AppointmentResponse]
    total: int


# ─────────────────────────────────────────────────────────
# 咨询记录 (工作台核心)
# ─────────────────────────────────────────────────────────


class ConsultRecordCreateRequest(BaseModel):
    """心理老师写实 — 提交咨询记录"""

    appointment_id: int
    student_id: int
    clog_plaintext: str = Field(
        ...,
        description="咨询日志明文 — 服务层自动加密落盘",
    )
    risk_level: str = Field(default="green", description="green/yellow/orange/red")
    consult_category: str | None = Field(
        default=None,
        description="emotion/interpersonal/academic/family/self_harm/other",
    )
    is_crisis: bool = False
    is_referred: bool = False
    referral_target: str | None = None
    followup_date: str | None = Field(default=None, description="YYYY-MM-DD")
    session_duration_min: int | None = Field(default=None, ge=1, le=480)


class ConsultRecordResponse(BaseModel):
    """咨询记录响应 — clog 根据角色决定是否解密"""

    id: int
    appointment_id: int
    student_id: int
    student_name: str | None = None
    counselor_id: int
    counselor_name: str | None = None
    clog_display: str = Field(..., description="解密后的正文 / 脱敏摘要")
    risk_level: str
    consult_category: str | None = None
    is_crisis: bool
    is_referred: bool
    referral_target: str | None = None
    followup_date: str | None = None
    session_duration_min: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    class Config:
        from_attributes = True


class ConsultRecordListResponse(BaseModel):
    status: str = "success"
    records: list[ConsultRecordResponse]
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
    avg_duration_min: float | None = None
    risk_distribution: dict = Field(default_factory=dict)
    category_distribution: dict = Field(default_factory=dict)
    upcoming_appointments: int
    pending_appointments: int
