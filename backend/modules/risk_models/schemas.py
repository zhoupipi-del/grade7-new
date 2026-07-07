"""
modules/risk_models/schemas.py — 风险预警雷达 Pydantic 数据模型
"""

from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field


# ── 风险预警 ──

class RiskWarningCreate(BaseModel):
    """创建风险预警 (系统自动触发，不开放手动创建)"""
    student_id: int
    rdi_score: float = Field(..., ge=-5.0, le=5.0, description="RDI 风险偏离指数 (Z-Score)")
    risk_level: str = Field(..., description="normal/attention/intervention")
    behavior_deviation: float = 0.0
    attendance_deviation: float = 0.0
    score_deviation: float = 0.0
    trigger_event_type: Optional[str] = None
    trigger_event_id: Optional[int] = None


class RiskWarningUpdate(BaseModel):
    """更新预警状态 (教师处置)"""
    status: Optional[str] = Field(None, description="active/handled/false_positive/expired")
    handling_note: Optional[str] = Field(None, max_length=500)
    action_taken: Optional[str] = Field(None, description="heart_to_heart/talk_to_parent/intervention_plan/dismiss")


class RiskWarningOut(BaseModel):
    """风险预警输出"""
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

    ewma_trend: float
    is_escalating: bool

    status: str
    warned_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    trigger_event_type: Optional[str] = None
    handler_name: Optional[str] = None

    model_config = {"from_attributes": True}


# ── 预警反馈 ──

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


# ── RDI 计算请求/响应 ──

class RDICalculateRequest(BaseModel):
    """RDI 计算请求"""
    student_id: int
    window_short: int = Field(7, ge=3, le=30, description="短窗口天数")
    window_medium: int = Field(30, ge=7, le=90, description="中窗口天数")
    window_long: int = Field(90, ge=30, le=180, description="长窗口天数")
    include_trend: bool = True
    suppress_low_rdi: bool = True


class RDICalculateResponse(BaseModel):
    """RDI 计算结果"""
    student_id: int
    rdi_score: float
    risk_level: str

    # 三维度偏离
    behavior_deviation: float
    attendance_deviation: float
    score_deviation: float

    # 各维度原始值
    behavior_count: int
    attendance_rate: float
    score_avg: float

    # 基线对比 (Z-Score 分母)
    behavior_baseline_mean: float
    behavior_baseline_std: float
    attendance_baseline_mean: float
    attendance_baseline_std: float

    # EWMA 趋势
    ewma_trend: float
    is_escalating: bool

    # 预警建议
    warning_suppressed: bool
    suppression_reason: Optional[str] = None
    recommended_action: Optional[str] = None

    calculated_at: datetime


# ── 风险看板 ──

class RiskDashboardOut(BaseModel):
    """风险看板输出 (班主任/级组长首页)"""
    total_students: int
    at_risk_count: int
    by_risk_level: dict  # {"normal": 300, "attention": 80, "intervention": 13}

    recent_warnings: List[RiskWarningOut]
    escalating_cases: List[RiskWarningOut]

    class_risk_ranking: List[dict]  # [{"class_id": 1, "class_name": "2501", "at_risk_count": 5}, ...]

    model_config = {"from_attributes": True}


# ── 风险监控面板 (Monitor Panel) ──

class MonitorStudentCard(BaseModel):
    """监控面板学生卡片 — 仅展示黄/红预警学生 (RDI > 1.0)"""
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
    top_dimension: str  # behavior / attendance / score — 偏离最大的维度

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


# ── PenaltyExplainer 判罚透明化解释 ──

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
    effective_penalty: float = Field(..., description="实际有效扣分 (= base_penalty × weight_multiplier)")


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


# ── 异步任务投递 ──

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
