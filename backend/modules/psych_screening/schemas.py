"""
Psych Screening Pydantic 模型
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime


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
    "强迫症状", "偏执", "敌对", "人际敏感", "抑郁",
    "焦虑", "学习压力", "适应不良", "情绪不平衡", "心理不平衡",
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
    answers: List[SurveyAnswer]


class SurveySubmitResponse(BaseModel):
    """问卷提交响应"""
    status: str = "ok"
    survey_id: int
    total_score: float
    risk_level: Optional[str] = None
    assessment_id: Optional[int] = None  # 自动创建的评估 ID
    message: Optional[str] = None

    class Config:
        from_attributes = True


# ============================================================
# 问卷记录
# ============================================================

class PsychSurveyOut(BaseModel):
    """问卷记录输出"""
    id: int
    student_id: int
    student_name: Optional[str] = None
    class_name: Optional[str] = None
    grade_name: Optional[str] = None
    survey_type: str
    total_score: Optional[float] = None
    verify_status: str
    completed_at: Optional[datetime] = None
    dimensions: Optional[dict] = None  # 解析后的维度分数

    class Config:
        from_attributes = True


class PsychSurveyListResponse(BaseModel):
    """问卷列表响应"""
    surveys: List[PsychSurveyOut]
    total: int
    stats: dict  # {high: n, medium: n, low: n}


# ============================================================
# 心理健康评估
# ============================================================

class AssessmentCreateRequest(BaseModel):
    """创建评估请求"""
    student_id: int
    assessment_type: str = Field(..., description="questionnaire/interview/observation/parent_feedback/teacher_feedback")
    scale_name: Optional[str] = None
    conclusion: Optional[str] = None
    recommendations: Optional[str] = None
    need_intervention: bool = False
    intervention_plan: Optional[str] = None
    risk_level: Optional[str] = "low"


class AssessmentUpdateRequest(BaseModel):
    """更新评估请求"""
    assessment_type: Optional[str] = None
    scale_name: Optional[str] = None
    conclusion: Optional[str] = None
    recommendations: Optional[str] = None
    need_intervention: Optional[bool] = None
    intervention_plan: Optional[str] = None
    risk_level: Optional[str] = None
    status: Optional[str] = None


class AssessmentOut(BaseModel):
    """评估记录输出"""
    id: int
    student_id: int
    student_name: Optional[str] = None
    class_name: Optional[str] = None
    assessment_type: str
    assessment_date: Optional[date] = None
    scale_name: Optional[str] = None
    total_score: Optional[float] = None
    risk_level: str
    conclusion: Optional[str] = None
    recommendations: Optional[str] = None
    need_intervention: bool
    intervention_plan: Optional[str] = None
    assessed_by: Optional[int] = None
    assessor_name: Optional[str] = None
    status: str
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    review_comment: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AssessmentDetailOut(AssessmentOut):
    """评估详情 (含答题明细+辅助数据)"""
    answers: Optional[List[dict]] = None
    intervention_records: Optional[List[dict]] = None
    # 辅助数据 (同 Flask 版本的 detail 页)
    recent_discipline: Optional[List[dict]] = None
    recent_scores: Optional[List[dict]] = None
    attendance_summary: Optional[dict] = None


class AssessmentListResponse(BaseModel):
    """评估列表响应"""
    assessments: List[AssessmentOut]
    total: int
    stats: dict  # {total, high, medium, low, need_intervention}


# ============================================================
# 维度分析 (雷达图)
# ============================================================

class DimensionDataResponse(BaseModel):
    """维度聚合数据 (供 ECharts 雷达图)"""
    indicator: List[str]  # 10 维度名称
    max_per_dim: int = 30  # 每维度满分
    average: List[float]   # 各维度均分
    max: List[float]       # 各维度最高分
    count: int             # 有效问卷数
    top_students: List[dict]
    risk_distribution: dict  # {high, medium, low}
    class_comparison: List[dict]


# ============================================================
# AI 分析
# ============================================================

class AIAnalysisRequest(BaseModel):
    """AI 分析请求 (可选传班级/年级筛选)"""
    class_id: Optional[int] = None
    grade_id: Optional[int] = None


class AIAnalysisResponse(BaseModel):
    """AI 分析响应"""
    report: str  # Markdown 格式报告
    error: Optional[str] = None


# ============================================================
# 同步请求
# ============================================================

class SyncToAssessmentResponse(BaseModel):
    """同步问卷 → 评估响应"""
    status: str
    created: int
    updated: int
    total_processed: int
    message: Optional[str] = None


# ============================================================
# 干预记录
# ============================================================

class InterventionCreateRequest(BaseModel):
    """创建干预记录"""
    student_id: int
    assessment_id: Optional[int] = None
    intervention_type: str = "心理谈话"
    notes: Optional[str] = None
    parent_feedback: Optional[str] = None
    intervention_date: Optional[str] = None  # YYYY-MM-DD
    follow_up_date: Optional[str] = None      # YYYY-MM-DD


class InterventionFollowupRequest(BaseModel):
    """陪同随访请求"""
    effect_rating: Optional[str] = None
    follow_up_notes: Optional[str] = None
    parent_feedback: Optional[str] = None
    mh_risk_after: Optional[str] = None


class InterventionOut(BaseModel):
    """干预记录输出"""
    id: int
    student_id: int
    student_name: Optional[str] = None
    class_name: Optional[str] = None
    teacher_id: Optional[int] = None
    teacher_name: Optional[str] = None
    assessment_id: Optional[int] = None
    mh_risk_before: Optional[str] = None
    mh_risk_after: Optional[str] = None
    intervention_type: str
    notes: Optional[str] = None
    parent_feedback: Optional[str] = None
    effect_rating: Optional[str] = None
    intervention_date: Optional[date] = None
    follow_up_date: Optional[date] = None
    follow_up_done: bool
    follow_up_notes: Optional[str] = None
    status: str
    is_effective: bool
    mh_risk_improved: Optional[bool] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InterventionListResponse(BaseModel):
    """干预记录列表"""
    records: List[InterventionOut]
    total: int
    stats: dict


class InterventionTimelineResponse(BaseModel):
    """学生干预时间线"""
    student_id: int
    student_name: str
    records: List[InterventionOut]
    risk_trend: List[dict]  # ECharts 数据
    latest_assessment: Optional[AssessmentOut] = None


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
    questions: List[QuestionOut]
    scale_names: List[str]
    total: int


# ============================================================
# 学生搜索
# ============================================================

class StudentSearchItem(BaseModel):
    """学生搜索结果"""
    id: int
    name: str
    class_name: Optional[str] = None
    risk_level: Optional[str] = None
    total_score: Optional[float] = None
    assessment_id: Optional[int] = None


class StudentSearchResponse(BaseModel):
    """学生搜索响应"""
    students: List[StudentSearchItem]
    total: int


# ============================================================
# 统计仪表盘
# ============================================================

class PsychDashboardResponse(BaseModel):
    """心理筛查仪表盘"""
    survey_stats: dict       # {total, mssmhs_count, pce_count}
    risk_distribution: dict  # {high, medium, low}
    assessment_stats: dict   # {total, by_type, need_intervention}
    intervention_stats: dict # {total, tracking, completed, effective}
    dimension_alerts: List[dict]  # 维度预警 (均分 > 15)
