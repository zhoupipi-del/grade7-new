"""
Psych Screening Pydantic 模型
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

# ============================================================
# 枚举常量 (与前端对齐)
# ============================================================

ASSESSMENT_TYPE_CHOICES = [
    ("questionnaire", "问卷测评"),
    ("interview", "访谈评估"),
    ("observation", "观察记录"),
    ("parent_feedback", "家长反馈"),
    ("teacher_feedback", "教师反馈"),
]

RISK_LEVEL_CHOICES = [
    ("low", "低风险"),
    ("medium", "中风险"),
    ("high", "高风险"),
]

INTERVENTION_TYPE_CHOICES = [
    ("心理谈话", "心理谈话"),
    ("家长联动", "家长联动"),
    ("心理辅导", "心理辅导"),
    ("危机干预", "危机干预"),
    ("转介专业机构", "转介专业机构"),
    ("其他", "其他"),
]

EFFECT_RATING_CHOICES = [
    ("显著好转", "显著好转"),
    ("略有好转", "略有好转"),
    ("无变化", "无变化"),
    ("恶化", "恶化"),
]

# MSSMHS-55 10 维度
MSSMHS_DIMENSIONS = [
    "强迫症状",
    "偏执",
    "敌对",
    "人际敏感",
    "抑郁",
    "焦虑",
    "学习压力",
    "适应不良",
    "情绪不平衡",
    "心理不平衡",
]


# ============================================================
# 问卷提交
# ============================================================


class SurveyAnswer(BaseModel):
    """单题答案"""

    question_no: int
    score: int = Field(ge=1, le=5)


class SurveySubmitRequest(BaseModel):
    """问卷提交请求"""

    student_id: int
    survey_type: str = "MSSMHS-55"
    answers: list[SurveyAnswer]


class SurveySubmitResponse(BaseModel):
    """问卷提交响应"""

    status: str = "ok"
    survey_id: int
    total_score: float
    risk_level: str | None = None
    assessment_id: int | None = None  # 自动创建的评估 ID
    message: str | None = None

    class Config:
        from_attributes = True


# ============================================================
# 问卷记录
# ============================================================


class PsychSurveyOut(BaseModel):
    """问卷记录输出"""

    id: int
    student_id: int
    student_name: str | None = None
    class_name: str | None = None
    grade_name: str | None = None
    survey_type: str
    total_score: float | None = None
    verify_status: str
    completed_at: datetime | None = None
    dimensions: dict | None = None  # 解析后的维度分数

    class Config:
        from_attributes = True


class PsychSurveyListResponse(BaseModel):
    """问卷列表响应"""

    surveys: list[PsychSurveyOut]
    total: int
    stats: dict  # {high: n, medium: n, low: n}


# ============================================================
# 心理健康评估
# ============================================================


class AssessmentCreateRequest(BaseModel):
    """创建评估请求"""

    student_id: int
    assessment_type: str = Field(
        ..., description="questionnaire/interview/observation/parent_feedback/teacher_feedback"
    )
    scale_name: str | None = None
    conclusion: str | None = None
    recommendations: str | None = None
    need_intervention: bool = False
    intervention_plan: str | None = None
    risk_level: str | None = "low"


class AssessmentUpdateRequest(BaseModel):
    """更新评估请求"""

    assessment_type: str | None = None
    scale_name: str | None = None
    conclusion: str | None = None
    recommendations: str | None = None
    need_intervention: bool | None = None
    intervention_plan: str | None = None
    risk_level: str | None = None
    status: str | None = None


class AssessmentOut(BaseModel):
    """评估记录输出"""

    id: int
    student_id: int
    student_name: str | None = None
    class_name: str | None = None
    assessment_type: str
    assessment_date: date | None = None
    scale_name: str | None = None
    total_score: float | None = None
    risk_level: str
    conclusion: str | None = None
    recommendations: str | None = None
    need_intervention: bool
    intervention_plan: str | None = None
    assessed_by: int | None = None
    assessor_name: str | None = None
    status: str
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None
    review_comment: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class AssessmentDetailOut(AssessmentOut):
    """评估详情 (含答题明细+辅助数据)"""

    answers: list[dict] | None = None
    intervention_records: list[dict] | None = None
    # 辅助数据 (同 Flask 版本的 detail 页)
    recent_discipline: list[dict] | None = None
    recent_scores: list[dict] | None = None
    attendance_summary: dict | None = None


class AssessmentListResponse(BaseModel):
    """评估列表响应"""

    assessments: list[AssessmentOut]
    total: int
    stats: dict  # {total, high, medium, low, need_intervention}


# ============================================================
# 维度分析 (雷达图)
# ============================================================


class DimensionDataResponse(BaseModel):
    """维度聚合数据 (供 ECharts 雷达图)"""

    indicator: list[str]  # 10 维度名称
    max_per_dim: int = 30  # 每维度满分
    average: list[float]  # 各维度均分
    max: list[float]  # 各维度最高分
    count: int  # 有效问卷数
    top_students: list[dict]
    risk_distribution: dict  # {high, medium, low}
    class_comparison: list[dict]


# ============================================================
# AI 分析
# ============================================================


class AIAnalysisRequest(BaseModel):
    """AI 分析请求 (可选传班级/年级筛选)"""

    class_id: int | None = None
    grade_id: int | None = None


class AIAnalysisResponse(BaseModel):
    """AI 分析响应"""

    report: str  # Markdown 格式报告
    error: str | None = None


# ============================================================
# 同步请求
# ============================================================


class SyncToAssessmentResponse(BaseModel):
    """同步问卷 → 评估响应"""

    status: str
    created: int
    updated: int
    total_processed: int
    message: str | None = None


# ============================================================
# 干预记录
# ============================================================


class InterventionCreateRequest(BaseModel):
    """创建干预记录"""

    student_id: int
    assessment_id: int | None = None
    intervention_type: str = "心理谈话"
    notes: str | None = None
    parent_feedback: str | None = None
    intervention_date: str | None = None  # YYYY-MM-DD
    follow_up_date: str | None = None  # YYYY-MM-DD


class InterventionFollowupRequest(BaseModel):
    """陪同随访请求"""

    effect_rating: str | None = None
    follow_up_notes: str | None = None
    parent_feedback: str | None = None
    mh_risk_after: str | None = None


class InterventionOut(BaseModel):
    """干预记录输出"""

    id: int
    student_id: int
    student_name: str | None = None
    class_name: str | None = None
    teacher_id: int | None = None
    teacher_name: str | None = None
    assessment_id: int | None = None
    mh_risk_before: str | None = None
    mh_risk_after: str | None = None
    intervention_type: str
    notes: str | None = None
    parent_feedback: str | None = None
    effect_rating: str | None = None
    intervention_date: date | None = None
    follow_up_date: date | None = None
    follow_up_done: bool
    follow_up_notes: str | None = None
    status: str
    is_effective: bool
    mh_risk_improved: bool | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class InterventionListResponse(BaseModel):
    """干预记录列表"""

    records: list[InterventionOut]
    total: int
    stats: dict


class InterventionTimelineResponse(BaseModel):
    """学生干预时间线"""

    student_id: int
    student_name: str
    records: list[InterventionOut]
    risk_trend: list[dict]  # ECharts 数据
    latest_assessment: AssessmentOut | None = None


# ============================================================
# 问题库
# ============================================================


class QuestionOut(BaseModel):
    """问题条目"""

    id: int
    scale_name: str
    dimension: str
    question_no: int
    question_text: str
    option_type: str
    reverse_scoring: bool
    is_active: bool

    class Config:
        from_attributes = True


class QuestionListResponse(BaseModel):
    """问题库列表"""

    questions: list[QuestionOut]
    scale_names: list[str]
    total: int


# ============================================================
# 学生搜索
# ============================================================


class StudentSearchItem(BaseModel):
    """学生搜索结果"""

    id: int
    name: str
    class_name: str | None = None
    risk_level: str | None = None
    total_score: float | None = None
    assessment_id: int | None = None


class StudentSearchResponse(BaseModel):
    """学生搜索响应"""

    students: list[StudentSearchItem]
    total: int


# ============================================================
# 统计仪表盘
# ============================================================


class PsychDashboardResponse(BaseModel):
    """心理筛查仪表盘"""

    survey_stats: dict  # {total, mssmhs_count, pce_count}
    risk_distribution: dict  # {high, medium, low}
    assessment_stats: dict  # {total, by_type, need_intervention}
    intervention_stats: dict  # {total, tracking, completed, effective}
    dimension_alerts: list[dict]  # 维度预警 (均分 > 15)
