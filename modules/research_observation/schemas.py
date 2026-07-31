"""
research_observation/schemas.py — Pydantic 强类型校验契约
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime


# ──────────────────────────────────────────────
# 评分维度
# ──────────────────────────────────────────────
class RubricDimension(BaseModel):
    """单个评分维度"""
    name: str = Field(..., description="维度名称: 教学引入/重难点突出/板书设计/生生互动/...")
    score: float = Field(..., ge=0, description="得分")
    max: float = Field(..., gt=0, description="满分")
    weight: Optional[float] = Field(None, description="权重(可选)")
    comment: str = Field("", description="维度评语")


class TextFeedback(BaseModel):
    """结构化文本反馈"""
    highlights: List[str] = Field(default=[], description="闪光点")
    suggestions: List[str] = Field(default=[], description="改进建议")
    overall_comment: str = Field("", description="总体评价")


# ──────────────────────────────────────────────
# 请求模型
# ──────────────────────────────────────────────
class ObservationCreate(BaseModel):
    """创建听课记录"""
    teacher_id: int = Field(..., description="授课人ID")
    class_id: int = Field(..., description="班级ID")
    subject_code: str = Field(..., description="学科代码")
    lesson_title: str = Field("", description="课题名称")
    observation_type: str = Field("routine", description="听课类型")
    lesson_plan_id: Optional[int] = Field(None, description="关联教案ID")
    plan_version_number: Optional[int] = None
    observed_at: datetime = Field(..., description="听课时间")
    duration_minutes: int = Field(45, ge=10, le=240, description="听课时长(分钟)")
    text_feedback: Optional[TextFeedback] = None
    plan_adherence: Optional[str] = Field(None, description="教案执行度: full/partial/deviated")
    plan_deviation_note: Optional[str] = None
    schedule_instance_id: Optional[int] = Field(None, description="时空弹道锚定ID (从auto-locate获取)")


class RubricSubmit(BaseModel):
    """提交多维评分"""
    template_name: str = Field("常规听课评分表", description="评分模板名称")
    dimensions: List[RubricDimension] = Field(..., min_length=1, description="评分维度列表")


class TeacherConfirm(BaseModel):
    """教师确认"""
    pass


class TeacherAppeal(BaseModel):
    """教师申诉"""
    appeal_reason: str = Field(..., min_length=1, description="申诉理由")
    appealed_dimensions: List[str] = Field(default=[], description="申诉维度列表")


class AppealResolve(BaseModel):
    """处理申诉"""
    resolution: str = Field(..., min_length=1, description="处理结论")
    score_adjusted: bool = Field(False, description="是否调整评分")
    adjusted_total_score: Optional[float] = Field(None, description="调整后总分")


class ObservationUpdate(BaseModel):
    """更新听课记录 (仅pending状态可改)"""
    lesson_title: Optional[str] = None
    observation_type: Optional[str] = None
    text_feedback: Optional[TextFeedback] = None
    plan_adherence: Optional[str] = None
    plan_deviation_note: Optional[str] = None
    schedule_instance_id: Optional[int] = Field(None, description="时空弹道锚定ID")


# ──────────────────────────────────────────────
# 时空弹道捕获器 (Wings 3.1)
# ──────────────────────────────────────────────
class AutoLocateRequest(BaseModel):
    """自动卡位请求 — 输入班级+时间, 输出节次/学科/教师"""
    class_id: int = Field(..., description="班级ID")
    occurred_at: datetime = Field(..., description="听课时间 (精确到分钟)")


class AutoLocateResponse(BaseModel):
    """自动卡位结果"""
    in_lesson: bool = Field(False, description="是否在上课时段")
    period_index: Optional[int] = Field(None, description="第几节课")
    slot_id: Optional[int] = Field(None, description="作息时段ID")
    subject_id: Optional[int] = Field(None, description="学科ID")
    teacher_id: Optional[int] = Field(None, description="教师ID")
    teacher_name: Optional[str] = Field(None, description="教师姓名")
    context_desc: str = Field("", description="时空上下文描述")
    schedule_instance_id: Optional[int] = Field(None, description="课表实例ID (可空)")
    # 前端兼容字段
    matched: bool = Field(False, description="是否匹配到课表(=in_lesson)")
    message: Optional[str] = Field(None, description="未匹配时的提示消息(=context_desc)")
    slot_number: Optional[int] = Field(None, description="第几节(=period_index+1)")
    subject_code: Optional[str] = Field(None, description="科目代码(如math/chinese)")
    subject_name: Optional[str] = Field(None, description="科目中文名")


class TimelineCommentCreate(BaseModel):
    """打点弹幕创建"""
    seconds_in_lesson: int = Field(..., ge=0, description="课中第几秒 (从上课开始计时)")
    type: str = Field("note", description="弹幕类型: highlight/suggestion/question/note")
    text: str = Field(..., min_length=1, max_length=500, description="弹幕内容")


class TimelineCommentResponse(BaseModel):
    """打点弹幕响应"""
    seconds_in_lesson: int
    type: str
    text: str
    author_id: int
    author_name: Optional[str] = None
    created_at: datetime


# ──────────────────────────────────────────────
# 响应模型
# ──────────────────────────────────────────────
class RubricResponse(BaseModel):
    id: int
    observation_id: int
    template_name: Optional[str] = None
    rubric_metrics: List[Dict[str, Any]] = []
    total_score: float
    max_score: float
    percentage: Optional[float] = None
    scorer_id: int
    scorer_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AppealResponse(BaseModel):
    id: int
    observation_id: int
    teacher_id: int
    teacher_name: Optional[str] = None
    action_type: str
    appeal_reason: Optional[str] = None
    appealed_dimensions: List[str] = []
    resolution: Optional[str] = None
    resolved_by: Optional[int] = None
    score_adjusted: bool = False
    adjusted_total_score: Optional[float] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ObservationResponse(BaseModel):
    id: int
    school_id: int
    observer_id: int
    observer_name: Optional[str] = None
    teacher_id: int
    teacher_name: Optional[str] = None
    class_id: int
    class_name: Optional[str] = None
    subject_code: str
    lesson_title: Optional[str] = None
    observation_type: str
    lesson_plan_id: Optional[int] = None
    plan_version_number: Optional[int] = None
    score_total: Optional[float] = None
    score_max: float = 100.0
    score_percentage: Optional[float] = None
    grade: Optional[str] = None
    text_feedback: Optional[Dict[str, Any]] = None
    plan_adherence: Optional[str] = None
    plan_deviation_note: Optional[str] = None
    feedback_status: str
    feedback_status_updated_at: Optional[datetime] = None
    teacher_viewed_at: Optional[datetime] = None
    schedule_instance_id: Optional[int] = None
    timeline_comments: Optional[List[Dict[str, Any]]] = None
    observed_at: datetime
    duration_minutes: int = 45
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ObservationDetailResponse(ObservationResponse):
    """听课详情 — 含评分矩阵和反馈历史"""
    rubric: Optional[RubricResponse] = None
    appeals: List[AppealResponse] = []
    plan_title: Optional[str] = None
    plan_status: Optional[str] = None


class DashboardStats(BaseModel):
    """听课统计看板"""
    total_observations: int = 0
    pending_feedback: int = 0
    confirmed: int = 0
    appealed: int = 0
    resolved: int = 0
    avg_score: Optional[float] = None
    by_type: Dict[str, int] = {}
    by_grade: Dict[str, int] = {}
    by_subject: Dict[str, int] = {}
    top_observers: List[Dict[str, Any]] = []
    top_teachers: List[Dict[str, Any]] = []
