"""
modules/risk_models/schemas.py — 风险预警雷达 Pydantic 数据模型 (v3.1 四维版本)

v3.1 新增:
  - DimensionScores: 10维英文标准Key Pydantic v2 强校验模型
  - PsychSurveyOut / MentalHealthAssessmentOut / PsychCrossAnalysisOut
  - RiskWarningOut / MonitorStudentCard / RDICalculateResponse 升级为四维
"""

from typing import Optional, List, Dict
from datetime import datetime, date
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# v3.1 核心: 10维心理标准Key Pydantic v2 强校验模型
# =============================================================================

# 10维标准Key定义 (ETL v3.1 已标准化，100% 英文Key)
DIMENSION_KEYS = {
    "obsessive_compulsive_score":     "强迫症状",
    "paranoid_score":                 "偏执",
    "hostility_score":                "敌对",
    "interpersonal_sensitivity_score": "人际敏感",
    "depression_score":               "抑郁",
    "anxiety_score":                  "焦虑",
    "learning_pressure_score":        "学习压力",
    "maladjustment_score":            "适应不良",
    "emotional_imbalance_score":      "情绪不平衡",
    "psychological_imbalance_score":  "心理不平衡",
}


class DimensionScores(BaseModel):
    """
    10维心理标准分数 Pydantic v2 强校验模型

    类型约束: 每维 Float, 边界 [-5.0, 10.0]
    逻辑约束: 所有字段必须为 10 维标准英文 Key
    序列化仅允许 10 个字段，拒绝任意额外字段
    """
    obsessive_compulsive_score:     Optional[float] = Field(None, ge=-5.0, le=10.0, description="强迫症状")
    paranoid_score:                 Optional[float] = Field(None, ge=-5.0, le=10.0, description="偏执")
    hostility_score:                Optional[float] = Field(None, ge=-5.0, le=10.0, description="敌对")
    interpersonal_sensitivity_score: Optional[float] = Field(None, ge=-5.0, le=10.0, description="人际敏感")
    depression_score:               Optional[float] = Field(None, ge=-5.0, le=10.0, description="抑郁")
    anxiety_score:                  Optional[float] = Field(None, ge=-5.0, le=10.0, description="焦虑")
    learning_pressure_score:        Optional[float] = Field(None, ge=-5.0, le=10.0, description="学习压力")
    maladjustment_score:            Optional[float] = Field(None, ge=-5.0, le=10.0, description="适应不良")
    emotional_imbalance_score:      Optional[float] = Field(None, ge=-5.0, le=10.0, description="情绪不平衡")
    psychological_imbalance_score:  Optional[float] = Field(None, ge=-5.0, le=10.0, description="心理不平衡")

    model_config = {"extra": "forbid"}  # 拒绝任意额外字段

    @classmethod
    def all_dimension_keys(cls) -> List[str]:
        """返回10维标准Key列表"""
        return list(cls.model_fields.keys())

    @classmethod
    def max_dimension(cls, scores: dict) -> tuple:
        """
        极端维度驱动: 返回偏离分数最大的维度名和值

        Args:
            scores: {"depression_score": 5.086, "anxiety_score": 2.1, ...}

        Returns:
            (dimension_key, max_value) — 如 ("depression_score", 5.086)
        """
        if not scores:
            return (None, 0.0)
        dim_scores = {k: v for k, v in scores.items()
                      if k in cls.model_fields and v is not None}
        if not dim_scores:
            return (None, 0.0)
        max_dim = max(dim_scores, key=lambda k: abs(dim_scores[k]))
        return (max_dim, dim_scores[max_dim])


# =============================================================================
# 心理筛查三表 Schema
# =============================================================================

class PsychSurveyOut(BaseModel):
    """心理筛查问卷输出"""
    id: int
    student_id: int
    student_name: Optional[str] = None
    class_id: int
    class_name: Optional[str] = None
    grade_id: int
    survey_type: str
    total_score: Optional[float] = None
    dimension_scores: Optional[dict] = None
    is_valid: bool = True
    verify_status: str = "PENDING"
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    source_id: Optional[int] = None

    model_config = {"from_attributes": True}


class MentalHealthAssessmentOut(BaseModel):
    """心理健康评估输出"""
    id: int
    student_id: int
    student_name: Optional[str] = None
    class_id: int
    class_name: Optional[str] = None
    grade_id: int
    assessment_type: str
    assessment_date: Optional[date] = None
    scale_name: Optional[str] = None
    total_score: Optional[int] = None
    risk_level: Optional[str] = None
    dimension_scores: Optional[dict] = None
    conclusion: Optional[str] = None
    recommendations: Optional[str] = None
    need_intervention: bool = False
    intervention_plan: Optional[str] = None
    status: str = "DRAFT"
    assessed_by: int
    created_at: Optional[datetime] = None
    source_id: Optional[int] = None
    source_survey_id: Optional[int] = None

    model_config = {"from_attributes": True}


class PsychCrossAnalysisOut(BaseModel):
    """跨维度交叉分析输出"""
    id: int
    student_id: int
    student_name: Optional[str] = None
    class_id: int
    grade_id: int
    analysis_type: str
    details_json: Optional[dict] = None
    created_at: Optional[datetime] = None
    source_id: Optional[int] = None

    model_config = {"from_attributes": True}


# =============================================================================
# 风险预警 (四维升级)
# =============================================================================

class RiskWarningCreate(BaseModel):
    """创建风险预警 (系统自动触发，不开放手动创建)"""
    student_id: int
    rdi_score: float = Field(..., ge=-5.0, le=5.0, description="RDI 风险偏离指数 (Z-Score)")
    risk_level: str = Field(..., description="normal/attention/intervention")
    behavior_deviation: float = 0.0
    attendance_deviation: float = 0.0
    score_deviation: float = 0.0
    psych_deviation: float = Field(0.0, description="心理维度偏离度 (Z-Score, v3.1)")
    psych_veto_triggered: bool = Field(False, description="心理一票否决触发 (v3.1)")
    veto_dimension: Optional[str] = Field(None, description="触发一票否决的具体维度名 (v3.1)")
    trigger_event_type: Optional[str] = None
    trigger_event_id: Optional[int] = None


class RiskWarningUpdate(BaseModel):
    """更新预警状态 (教师处置)"""
    status: Optional[str] = Field(None, description="active/handled/false_positive/expired")
    handling_note: Optional[str] = Field(None, max_length=500)
    action_taken: Optional[str] = Field(None, description="heart_to_heart/talk_to_parent/intervention_plan/dismiss")


class RiskWarningOut(BaseModel):
    """风险预警输出 (v3.1 四维版)"""
    id: int
    student_id: int
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    class_id: int
    class_name: Optional[str] = None
    grade_id: int

    rdi_score: float
    risk_level: str
    behavior_deviation: float
    attendance_deviation: float
    score_deviation: float
    psych_deviation: float = Field(0.0, description="心理维度偏离度 (v3.1)")

    # 一票否决标记 (v3.1)
    psych_veto_triggered: bool = False
    veto_dimension: Optional[str] = None

    ewma_trend: float
    is_escalating: bool

    status: str
    warned_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    trigger_event_type: Optional[str] = None
    handler_name: Optional[str] = None

    model_config = {"from_attributes": True}


# =============================================================================
# 预警反馈
# =============================================================================

class WarningFeedbackCreate(BaseModel):
    warning_id: int
    action_taken: str = Field(..., description="heart_to_heart/talk_to_parent/intervention_plan/dismiss")
    action_detail: Optional[str] = Field(None, max_length=1000)
    effectiveness: Optional[str] = Field(None, description="effective/partially/pending/ineffective")
    follow_up_needed: bool = False


class WarningFeedbackOut(BaseModel):
    id: int
    warning_id: int
    teacher_name: Optional[str] = None
    action_taken: str
    action_detail: Optional[str] = None
    effectiveness: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# =============================================================================
# RDI 计算请求/响应 (四维升级)
# =============================================================================

class RDICalculateRequest(BaseModel):
    """RDI 计算请求"""
    student_id: int
    window_short: int = Field(7, ge=3, le=30, description="短窗口天数")
    window_medium: int = Field(30, ge=7, le=90, description="中窗口天数")
    window_long: int = Field(90, ge=30, le=180, description="长窗口天数")
    include_trend: bool = True
    suppress_low_rdi: bool = True
    include_psych: bool = Field(True, description="是否包含心理维度 (v3.1, 默认True)")


class RDICalculateResponse(BaseModel):
    """RDI 计算结果 (v3.1 四维版)"""
    student_id: int
    rdi_score: float
    risk_level: str

    # 四维度偏离
    behavior_deviation: float
    attendance_deviation: float
    score_deviation: float
    psych_deviation: float = Field(0.0, description="心理维度偏离度 (极端维度驱动模型)")

    # 一票否决互锁 (v3.1)
    psych_veto_triggered: bool = False
    veto_dimension: Optional[str] = None  # 触发一票否决的具体维度名

    # 各维度原始值
    behavior_count: int
    attendance_rate: float
    score_avg: float
    psych_raw_z_total: Optional[float] = Field(None, description="心理Z_total (v3.1)")
    psych_raw_max_dim: Optional[float] = Field(None, description="心理max(Z_dim1..dim10) (v3.1)")

    # 基线对比 (Z-Score 分母)
    behavior_baseline_mean: float
    behavior_baseline_std: float
    attendance_baseline_mean: float
    attendance_baseline_std: float
    score_baseline_mean: float
    score_baseline_std: float
    psych_baseline_mean: Optional[float] = Field(None, description="心理基线均值 (v3.1)")
    psych_baseline_std: Optional[float] = Field(None, description="心理基线标准差 (v3.1)")

    # EWMA 趋势
    ewma_trend: float
    is_escalating: bool

    # 大退潮保护 (v3.1)
    backslide_protected: bool = Field(False, description="是否触发大退潮保护 (30天内禁止降级)")

    # 预警建议
    warning_suppressed: bool
    suppression_reason: Optional[str] = None
    recommended_action: Optional[str] = None

    # 复合RDI分解 (v3.1)
    rdi_breakdown: Optional[Dict[str, float]] = Field(None, description="四维RDI贡献分解 {behavior: 0.5, attendance: 0.1, score: 0.3, psych: 1.2}")

    calculated_at: datetime


# =============================================================================
# 风险看板
# =============================================================================

class RiskDashboardOut(BaseModel):
    """风险看板输出 (班主任/级组长首页)"""
    total_students: int
    at_risk_count: int
    by_risk_level: dict  # {"normal": 300, "attention": 80, "intervention": 13}

    recent_warnings: List[RiskWarningOut]
    escalating_cases: List[RiskWarningOut]

    class_risk_ranking: List[dict]  # [{"class_id": 1, "class_name": "2501", "at_risk_count": 5}, ...]

    model_config = {"from_attributes": True}


# =============================================================================
# 风险监控面板 (Monitor Panel) — 四维升级
# =============================================================================

class MonitorStudentCard(BaseModel):
    """监控面板学生卡片 — 仅展示黄/红预警学生 (RDI > 1.0) (v3.1 四维版)"""
    student_id: int
    student_name: str
    student_no: Optional[str] = None
    class_id: int
    class_name: Optional[str] = None
    grade_id: int

    rdi_score: float
    risk_level: str  # attention / intervention
    risk_color: str  # yellow / red

    behavior_deviation: float
    attendance_deviation: float
    score_deviation: float
    psych_deviation: float = Field(0.0, description="心理维度偏离度 (v3.1)")
    top_dimension: str  # behavior / attendance / score / psych — 偏离最大的维度

    # 一票否决 (v3.1)
    psych_veto_triggered: bool = False
    veto_dimension: Optional[str] = None

    is_escalating: bool
    ewma_trend: float

    latest_warning_id: Optional[int] = None
    latest_warning_status: Optional[str] = None
    warned_at: Optional[datetime] = None
    days_since_warning: Optional[int] = None

    recommended_action: Optional[str] = None

    model_config = {"from_attributes": True}


class MonitorPanelOut(BaseModel):
    """监控面板输出"""
    total_students_scanned: int
    yellow_count: int   # attention (RDI 1.0-2.0)
    red_count: int      # intervention (RDI >= 2.0)
    students: List[MonitorStudentCard]

    class_breakdown: List[dict]  # [{"class_id": 1, "class_name": "2501", "yellow": 3, "red": 1}, ...]

    generated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# PenaltyExplainer 判罚透明化解释
# =============================================================================

class PenaltyExplanationRequest(BaseModel):
    """判罚解释请求 — 三段式解释的输入参数"""
    student_id: int = Field(..., description="学生ID")
    event_type: Optional[str] = Field(None, description="事件类型，如 fighting/lateness/cheating/smoking")
    event_id: Optional[int] = Field(None, description="违纪记录ID，指定则定向查询具体记录")

    # ── RDI 联动 (可选) ──
    include_rdi: bool = Field(True, description="是否自动计算 RDI (默认 True)")
    rdi_score: Optional[float] = Field(None, description="已有的 RDI 分数 (避免重复计算)")
    risk_level: Optional[str] = Field(None, description="已有的风险等级 (normal/attention/intervention)")
    is_escalating: Optional[bool] = Field(None, description="是否处于升级通道")
    warning_suppressed: Optional[bool] = Field(None, description="是否被冷静期抑制")


class PenaltyFact(BaseModel):
    """解释段①：事实陈述"""
    event_type: str = Field(..., description="事件类型代码")
    event_date: Optional[str] = Field(None, description="事件日期 (ISO格式)")
    penalty_amount: Optional[float] = Field(None, description="处罚扣分数")
    description: str = Field("", description="事实描述文本")
    data_source: str = Field(..., description="数据来源: discipline_records/score_logs/none/error")
    record_id: Optional[int] = Field(None, description="数据记录ID")


class PenaltyRule(BaseModel):
    """解释段②：校规映射"""
    regulation_ref: str = Field(..., description="校规条文引用")
    severity: str = Field(..., description="严重程度: minor/major/critical")
    dimension: str = Field(..., description="评价维度: academic_moral/discipline/attendance/activity")
    sub_dimension: str = Field(..., description="子维度")
    base_penalty: float = Field(..., description="基础扣分")
    weight_multiplier: float = Field(..., description="权重乘数")
    effective_penalty: float = Field(..., description="实际有效扣分 (= base_penalty x weight_multiplier)")


class PenaltyGrowth(BaseModel):
    """解释段③：建设性引导"""
    repairable: bool = Field(..., description="是否可回血")
    recovery_path: Optional[str] = Field(None, description="回血路径说明 (多通道合并)")
    recovery_eta_days: Optional[int] = Field(None, description="回血预估天数 (恢复到85%)")
    min_observation_days: int = Field(..., description="最短观察期天数")
    suggested_actions: List[str] = Field(default_factory=list, description="建议行动清单 (从模板提取)")
    ai_prescription_ref: Optional[str] = Field(None, description="AI 德育处方模块引用")


class PenaltyExplanationResponse(BaseModel):
    """判罚解释响应 — 三段式解释的完整输出"""
    student_id: int
    student_name: str
    student_no: Optional[str] = None
    class_name: Optional[str] = None

    # RDI 联动
    rdi_score: Optional[float] = None
    risk_level: Optional[str] = None

    # 三段式解释
    fact: PenaltyFact
    rule: PenaltyRule
    growth: PenaltyGrowth

    # 渲染结果
    explanation_text: str = Field(..., description="已渲染的完整解释文本 (变量替换+禁止用语校验后)")
    template_used: str = Field(..., description="使用的模板名称")
    tone: str = Field(..., description="语气基调")

    # 合规校验
    prohibited_phrase_violations: List[str] = Field(
        default_factory=list,
        description="禁止用语违规清单 (应为空，非空则需模板修正)"
    )

    generated_at: datetime = Field(..., description="生成时间")


# =============================================================================
# 异步任务投递
# =============================================================================

class TaskDispatchResponse(BaseModel):
    """异步任务投递响应 — fire-and-forget 模式"""
    status: str = "dispatched"
    task_id: str = Field(..., description="Celery 任务 UUID")
    message: str = Field(..., description="投递结果描述")


class AsyncCalculateRequest(BaseModel):
    """异步 RDI 计算请求 — 单学生 fire-and-forget"""
    student_id: int
    window_short: int = Field(7, ge=3, le=30)
    window_medium: int = Field(30, ge=7, le=90)
    window_long: int = Field(90, ge=30, le=180)
    include_trend: bool = True
    generate_warning: bool = Field(True, description="是否生成预警 (False=仅计算不存库)")


class AsyncScanClassRequest(BaseModel):
    """异步班级扫描请求"""
    semester: Optional[str] = Field(None, description="学期标识 (默认自动推断)")


class AsyncScanSchoolRequest(BaseModel):
    """异步全校扫描请求"""
    semester: Optional[str] = Field(None, description="学期标识 (默认自动推断)")
