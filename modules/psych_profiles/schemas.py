"""
psych_profiles/schemas.py — Pydantic 请求/响应模型
"""

from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# 心理档案
# ──────────────────────────────────────────────
class PsyProfileCreate(BaseModel):
    risk_level: str = Field("green", description="风险等级: green/yellow/orange/red")
    risk_level_source: str = Field("manual", description="来源: manual/auto/screening/nexus")
    tags: List[str] = Field(default_factory=list, description="标签云")
    guardian_contact_status: str = Field("normal", description="家校沟通状态")
    guardian_contact_note: Optional[str] = None
    is_referred: bool = False
    referral_status: Optional[str] = None
    referral_target: Optional[str] = None
    notes: Optional[str] = None


class PsyProfileUpdate(BaseModel):
    risk_level: Optional[str] = None
    risk_level_source: Optional[str] = None
    tags: Optional[List[str]] = None
    guardian_contact_status: Optional[str] = None
    guardian_contact_note: Optional[str] = None
    is_referred: Optional[bool] = None
    referral_status: Optional[str] = None
    referral_target: Optional[str] = None
    notes: Optional[str] = None


class TagsUpdate(BaseModel):
    tags: List[str] = Field(..., description="标签云 (完整替换)")


class RiskLevelUpdate(BaseModel):
    risk_level: str = Field(..., description="green/yellow/orange/red")
    risk_level_source: str = Field("manual", description="来源")
    note: Optional[str] = None


class PsyProfileResponse(BaseModel):
    id: int
    student_id: int
    risk_level: str
    risk_level_source: str
    risk_level_updated_at: Optional[datetime] = None
    risk_level_updated_by: Optional[int] = None
    tags: List[str] = []
    guardian_contact_status: str
    guardian_contact_note: Optional[str] = None
    total_counseling_count: int
    total_screening_count: int
    total_intervention_count: int
    highest_risk_level: str
    is_referred: bool
    referral_status: Optional[str] = None
    referral_target: Optional[str] = None
    last_counseling_date: Optional[datetime] = None
    last_screening_date: Optional[datetime] = None
    last_intervention_date: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PsyProfileDetailResponse(PsyProfileResponse):
    """档案详情 — 含学生基本信息"""
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    class_name: Optional[str] = None
    grade_name: Optional[str] = None
    recent_screenings: List[dict] = Field(default_factory=list, description="最近筛查记录")
    recent_counselings: List[dict] = Field(default_factory=list, description="最近咨询记录(脱敏)")
    recent_interventions: List[dict] = Field(default_factory=list, description="最近干预记录")


# ──────────────────────────────────────────────
# 筛查快照
# ──────────────────────────────────────────────
class PsyScreeningCreate(BaseModel):
    student_id: int
    scale_name: str = Field(..., description="量表名称")
    scale_version: Optional[str] = None
    raw_scores: Optional[dict] = None
    total_score: Optional[float] = None
    risk_factors: List[str] = Field(default_factory=list)
    risk_level: str = Field("green")
    conclusion: Optional[str] = None
    ai_generated: bool = False
    source: str = Field("self_report")
    assessment_id: Optional[int] = None
    test_date: datetime


class PsyScreeningResponse(BaseModel):
    id: int
    student_id: int
    scale_name: str
    scale_version: Optional[str] = None
    raw_scores: Optional[dict] = None
    total_score: Optional[float] = None
    risk_factors: List[str] = []
    risk_level: str
    conclusion: Optional[str] = None
    ai_generated: bool
    source: str
    operator_id: Optional[int] = None
    assessment_id: Optional[int] = None
    test_date: datetime
    created_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────
# 双轨预警 Nexus
# ──────────────────────────────────────────────
class AcademicRiskInfo(BaseModel):
    level: str = Field(..., description="RED/YELLOW/NONE")
    z_score: Optional[float] = None
    trigger_subjects: List[str] = []
    trigger_reason: Optional[str] = None
    source: str = "student_risk_alerts"


class PsyRiskInfo(BaseModel):
    level: str = Field(..., description="RED/ORANGE/YELLOW/GREEN")
    factors: List[str] = []
    last_screening_date: Optional[datetime] = None
    scale_name: Optional[str] = None
    source: str = "psy_profiles + psy_screening_records"


class RDIRiskInfo(BaseModel):
    score: Optional[float] = None
    level: Optional[str] = None
    psych_deviation: Optional[float] = None
    score_deviation: Optional[float] = None
    behavior_deviation: Optional[float] = None
    attendance_deviation: Optional[float] = None
    is_escalating: bool = False
    source: str = "risk_warnings"


class NexusRiskItem(BaseModel):
    student_id: int
    student_name: Optional[str] = None
    class_name: Optional[str] = None
    academic_risk: AcademicRiskInfo
    psy_risk: PsyRiskInfo
    rdi_risk: RDIRiskInfo
    co_trigger: bool = Field(False, description="学业+心理同时预警")
    action_priority: str = Field("NORMAL", description="NORMAL/WATCH/URGENT/CRITICAL")
    recommended_actions: List[str] = []


class NexusListResponse(BaseModel):
    total: int
    critical_count: int
    urgent_count: int
    watch_count: int
    items: List[NexusRiskItem]


class NexusStudentDetail(BaseModel):
    """单个学生的双轨详细画像"""
    student_id: int
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    class_name: Optional[str] = None
    grade_name: Optional[str] = None

    # 学业侧
    academic_risk: AcademicRiskInfo
    academic_history: List[dict] = Field(default_factory=list, description="学业预警历史")

    # 心理侧
    psy_risk: PsyRiskInfo
    psy_profile: Optional[dict] = None
    psy_screening_history: List[dict] = Field(default_factory=list, description="筛查历史")
    psy_counseling_summary: Optional[dict] = None

    # RDI 四维
    rdi_risk: RDIRiskInfo

    # 合成
    co_trigger: bool
    action_priority: str
    recommended_actions: List[str] = []


# ──────────────────────────────────────────────
# 仪表盘
# ──────────────────────────────────────────────
class DashboardResponse(BaseModel):
    total_profiles: int
    risk_distribution: dict = Field(default_factory=dict, description="{green: 0, yellow: 0, orange: 0, red: 0}")
    co_trigger_count: int = Field(0, description="学业+心理双预警学生数")
    total_screenings: int
    total_counselings: int
    total_referrals: int
    recent_screenings: List[dict] = Field(default_factory=list)
    top_risk_students: List[dict] = Field(default_factory=list)
