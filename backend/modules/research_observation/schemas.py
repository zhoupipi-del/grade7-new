"""
research_observation/schemas.py — Pydantic 强类型校验契约
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# 评分维度
# ──────────────────────────────────────────────
class RubricDimension(BaseModel):
    """单个评分维度"""

    name: str = Field(..., description="维度名称: 教学引入/重难点突出/板书设计/生生互动/...")
    score: float = Field(..., ge=0, description="得分")
    max: float = Field(..., gt=0, description="满分")
    weight: float | None = Field(None, description="权重(可选)")
    comment: str = Field("", description="维度评语")


class TextFeedback(BaseModel):
    """结构化文本反馈"""

    highlights: list[str] = Field(default=[], description="闪光点")
    suggestions: list[str] = Field(default=[], description="改进建议")
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
    lesson_plan_id: int | None = Field(None, description="关联教案ID")
    plan_version_number: int | None = None
    observed_at: datetime = Field(..., description="听课时间")
    duration_minutes: int = Field(45, ge=10, le=240, description="听课时长(分钟)")
    text_feedback: TextFeedback | None = None
    plan_adherence: str | None = Field(None, description="教案执行度: full/partial/deviated")
    plan_deviation_note: str | None = None
    schedule_instance_id: int | None = Field(None, description="时空弹道锚定ID (从auto-locate获取)")


class RubricSubmit(BaseModel):
    """提交多维评分"""

    template_name: str = Field("常规听课评分表", description="评分模板名称")
    dimensions: list[RubricDimension] = Field(..., min_length=1, description="评分维度列表")


class TeacherConfirm(BaseModel):
    """教师确认"""

    pass


class TeacherAppeal(BaseModel):
    """教师申诉"""

    appeal_reason: str = Field(..., min_length=1, description="申诉理由")
    appealed_dimensions: list[str] = Field(default=[], description="申诉维度列表")


class AppealResolve(BaseModel):
    """处理申诉"""

    resolution: str = Field(..., min_length=1, description="处理结论")
    score_adjusted: bool = Field(False, description="是否调整评分")
    adjusted_total_score: float | None = Field(None, description="调整后总分")


class ObservationUpdate(BaseModel):
    """更新听课记录 (仅pending状态可改)"""

    lesson_title: str | None = None
    observation_type: str | None = None
    text_feedback: TextFeedback | None = None
    plan_adherence: str | None = None
    plan_deviation_note: str | None = None
    schedule_instance_id: int | None = Field(None, description="时空弹道锚定ID")


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
    period_index: int | None = Field(None, description="第几节课")
    slot_id: int | None = Field(None, description="作息时段ID")
    subject_id: int | None = Field(None, description="学科ID")
    teacher_id: int | None = Field(None, description="教师ID")
    teacher_name: str | None = Field(None, description="教师姓名")
    context_desc: str = Field("", description="时空上下文描述")
    schedule_instance_id: int | None = Field(None, description="课表实例ID (可空)")


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
    author_name: str | None = None
    created_at: datetime


# ──────────────────────────────────────────────
# 响应模型
# ──────────────────────────────────────────────
class RubricResponse(BaseModel):
    id: int
    observation_id: int
    template_name: str | None = None
    rubric_metrics: list[dict[str, Any]] = []
    total_score: float
    max_score: float
    percentage: float | None = None
    scorer_id: int
    scorer_name: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class AppealResponse(BaseModel):
    id: int
    observation_id: int
    teacher_id: int
    teacher_name: str | None = None
    action_type: str
    appeal_reason: str | None = None
    appealed_dimensions: list[str] = []
    resolution: str | None = None
    resolved_by: int | None = None
    score_adjusted: bool = False
    adjusted_total_score: float | None = None
    created_at: datetime
    resolved_at: datetime | None = None

    class Config:
        from_attributes = True


class ObservationResponse(BaseModel):
    id: int
    school_id: int
    observer_id: int
    observer_name: str | None = None
    teacher_id: int
    teacher_name: str | None = None
    class_id: int
    class_name: str | None = None
    subject_code: str
    lesson_title: str | None = None
    observation_type: str
    lesson_plan_id: int | None = None
    plan_version_number: int | None = None
    score_total: float | None = None
    score_max: float = 100.0
    score_percentage: float | None = None
    grade: str | None = None
    text_feedback: dict[str, Any] | None = None
    plan_adherence: str | None = None
    plan_deviation_note: str | None = None
    feedback_status: str
    feedback_status_updated_at: datetime | None = None
    teacher_viewed_at: datetime | None = None
    schedule_instance_id: int | None = None
    timeline_comments: list[dict[str, Any]] | None = None
    observed_at: datetime
    duration_minutes: int = 45
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ObservationDetailResponse(ObservationResponse):
    """听课详情 — 含评分矩阵和反馈历史"""

    rubric: RubricResponse | None = None
    appeals: list[AppealResponse] = []
    plan_title: str | None = None
    plan_status: str | None = None


class DashboardStats(BaseModel):
    """听课统计看板"""

    total_observations: int = 0
    pending_feedback: int = 0
    confirmed: int = 0
    appealed: int = 0
    resolved: int = 0
    avg_score: float | None = None
    by_type: dict[str, int] = {}
    by_grade: dict[str, int] = {}
    by_subject: dict[str, int] = {}
    top_observers: list[dict[str, Any]] = []
    top_teachers: list[dict[str, Any]] = []
