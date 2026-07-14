"""
psych_profiles/schemas.py — Pydantic 请求/响应模型
"""

from datetime import datetime

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# 心理档案
# ──────────────────────────────────────────────
class PsyProfileCreate(BaseModel):
    risk_level: str = Field("green", description="风险等级: green/yellow/orange/red")
    risk_level_source: str = Field("manual", description="来源: manual/auto/screening/nexus")
    tags: list[str] = Field(default_factory=list, description="标签云")
    guardian_contact_status: str = Field("normal", description="家校沟通状态")
    guardian_contact_note: str | None = None
    is_referred: bool = False
    referral_status: str | None = None
    referral_target: str | None = None
    notes: str | None = None


class PsyProfileUpdate(BaseModel):
    risk_level: str | None = None
    risk_level_source: str | None = None
    tags: list[str] | None = None
    guardian_contact_status: str | None = None
    guardian_contact_note: str | None = None
    is_referred: bool | None = None
    referral_status: str | None = None
    referral_target: str | None = None
    notes: str | None = None


class TagsUpdate(BaseModel):
    tags: list[str] = Field(..., description="标签云 (完整替换)")


class RiskLevelUpdate(BaseModel):
    risk_level: str = Field(..., description="green/yellow/orange/red")
    risk_level_source: str = Field("manual", description="来源")
    note: str | None = None


class PsyProfileResponse(BaseModel):
    id: int
    student_id: int
    risk_level: str
    risk_level_source: str
    risk_level_updated_at: datetime | None = None
    risk_level_updated_by: int | None = None
    tags: list[str] = []
    guardian_contact_status: str
    guardian_contact_note: str | None = None
    total_counseling_count: int
    total_screening_count: int
    total_intervention_count: int
    highest_risk_level: str
    is_referred: bool
    referral_status: str | None = None
    referral_target: str | None = None
    last_counseling_date: datetime | None = None
    last_screening_date: datetime | None = None
    last_intervention_date: datetime | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PsyProfileDetailResponse(PsyProfileResponse):
    """档案详情 — 含学生基本信息"""

    student_name: str | None = None
    student_no: str | None = None
    class_name: str | None = None
    grade_name: str | None = None
    recent_screenings: list[dict] = Field(default_factory=list, description="最近筛查记录")
    recent_counselings: list[dict] = Field(default_factory=list, description="最近咨询记录(脱敏)")
    recent_interventions: list[dict] = Field(default_factory=list, description="最近干预记录")


# ──────────────────────────────────────────────
# 筛查快照
# ──────────────────────────────────────────────
class PsyScreeningCreate(BaseModel):
    student_id: int
    scale_name: str = Field(..., description="量表名称")
    scale_version: str | None = None
    raw_scores: dict | None = None
    total_score: float | None = None
    risk_factors: list[str] = Field(default_factory=list)
    risk_level: str = Field("green")
    conclusion: str | None = None
    ai_generated: bool = False
    source: str = Field("self_report")
    assessment_id: int | None = None
    test_date: datetime


class PsyScreeningResponse(BaseModel):
    id: int
    student_id: int
    scale_name: str
    scale_version: str | None = None
    raw_scores: dict | None = None
    total_score: float | None = None
    risk_factors: list[str] = []
    risk_level: str
    conclusion: str | None = None
    ai_generated: bool
    source: str
    operator_id: int | None = None
    assessment_id: int | None = None
    test_date: datetime
    created_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────
# 双轨预警 Nexus
# ──────────────────────────────────────────────
class AcademicRiskInfo(BaseModel):
    level: str = Field(..., description="RED/YELLOW/NONE")
    z_score: float | None = None
    trigger_subjects: list[str] = []
    trigger_reason: str | None = None
    source: str = "student_risk_alerts"


class PsyRiskInfo(BaseModel):
    level: str = Field(..., description="RED/ORANGE/YELLOW/GREEN")
    factors: list[str] = []
    last_screening_date: datetime | None = None
    scale_name: str | None = None
    source: str = "psy_profiles + psy_screening_records"


class RDIRiskInfo(BaseModel):
    score: float | None = None
    level: str | None = None
    psych_deviation: float | None = None
    score_deviation: float | None = None
    behavior_deviation: float | None = None
    attendance_deviation: float | None = None
    is_escalating: bool = False
    source: str = "risk_warnings"


class NexusRiskItem(BaseModel):
    student_id: int
    student_name: str | None = None
    class_name: str | None = None
    academic_risk: AcademicRiskInfo
    psy_risk: PsyRiskInfo
    rdi_risk: RDIRiskInfo
    co_trigger: bool = Field(False, description="学业+心理同时预警")
    action_priority: str = Field("NORMAL", description="NORMAL/WATCH/URGENT/CRITICAL")
    recommended_actions: list[str] = []


class NexusListResponse(BaseModel):
    total: int
    critical_count: int
    urgent_count: int
    watch_count: int
    items: list[NexusRiskItem]


class NexusStudentDetail(BaseModel):
    """单个学生的双轨详细画像"""

    student_id: int
    student_name: str | None = None
    student_no: str | None = None
    class_name: str | None = None
    grade_name: str | None = None

    # 学业侧
    academic_risk: AcademicRiskInfo
    academic_history: list[dict] = Field(default_factory=list, description="学业预警历史")

    # 心理侧
    psy_risk: PsyRiskInfo
    psy_profile: dict | None = None
    psy_screening_history: list[dict] = Field(default_factory=list, description="筛查历史")
    psy_counseling_summary: dict | None = None

    # RDI 四维
    rdi_risk: RDIRiskInfo

    # 合成
    co_trigger: bool
    action_priority: str
    recommended_actions: list[str] = []


# ──────────────────────────────────────────────
# 仪表盘
# ──────────────────────────────────────────────
class DashboardResponse(BaseModel):
    total_profiles: int
    risk_distribution: dict = Field(
        default_factory=dict, description="{green: 0, yellow: 0, orange: 0, red: 0}"
    )
    co_trigger_count: int = Field(0, description="学业+心理双预警学生数")
    total_screenings: int
    total_counselings: int
    total_referrals: int
    recent_screenings: list[dict] = Field(default_factory=list)
    top_risk_students: list[dict] = Field(default_factory=list)
