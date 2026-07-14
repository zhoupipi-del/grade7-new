"""
research_lesson_prep/schemas.py — Pydantic 强类型校验契约
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# 教案内容结构
# ──────────────────────────────────────────────
class TeachingProcessStep(BaseModel):
    """教学过程单步"""

    phase: str = Field(..., description="环节: 导入/新授/练习/小结/作业")
    duration: int = Field(default=5, description="时长(分钟)")
    content: str = Field("", description="教学内容")
    activities: list[str] = Field(default=[], description="教学活动")
    resources: list[str] = Field(default=[], description="教学资源/教具")


class LessonContent(BaseModel):
    """结构化教案内容"""

    teaching_objectives: list[str] = Field(default=[], description="教学目标")
    key_points: list[str] = Field(default=[], description="教学重点")
    difficulties: list[str] = Field(default=[], description="教学难点")
    teaching_methods: list[str] = Field(default=[], description="教学方法")
    teaching_process: list[TeachingProcessStep] = Field(default=[], description="教学过程")
    homework: list[str] = Field(default=[], description="课后作业")
    blackboard_design: str = Field("", description="板书设计")
    reflection: str = Field("", description="教学反思(课后填写)")


# ──────────────────────────────────────────────
# 请求模型
# ──────────────────────────────────────────────
class PlanCreate(BaseModel):
    """创建备课主案"""

    title: str = Field(..., min_length=1, max_length=200, description="教案标题")
    description: str | None = None
    subject_code: str = Field(..., description="学科代码")
    grade_level: str = Field(..., description="年级")
    lesson_type: str = Field("new", description="课型: new/review/exam/test/activity")
    duration: int = Field(1, ge=1, le=10, description="课时数")
    tags: list[str] = Field(default=[], description="标签")
    content: LessonContent = Field(default=LessonContent(), description="初始教案内容")
    content_markdown: str | None = Field(None, description="Markdown+LaTeX 正文")
    change_log: str = Field("初始创建", description="版本说明")


class PlanUpdate(BaseModel):
    """更新教案元信息 (不动内容)"""

    title: str | None = Field(None, max_length=200)
    description: str | None = None
    lesson_type: str | None = None
    duration: int | None = Field(None, ge=1, le=10)
    tags: list[str] | None = None


class VersionCreate(BaseModel):
    """创建新版本 (保存内容快照)"""

    content: LessonContent = Field(..., description="教案内容")
    content_markdown: str | None = Field(None, description="Markdown+LaTeX 正文")
    change_log: str = Field("内容更新", description="变更说明")
    is_major: bool = Field(False, description="是否重大修订")


class ReviewCreate(BaseModel):
    """添加批注"""

    version_number: int = Field(..., ge=1, description="批注针对的版本号")
    target_section: str = Field(..., description="教案组件路径")
    target_anchor: str | None = None
    comment: str = Field(..., min_length=1, description="批注正文")
    severity: str = Field("suggestion", description="严重度: suggestion/issue/critical")
    parent_review_id: int | None = None


class ReviewResolve(BaseModel):
    """解决批注"""

    resolution_note: str = Field("", description="解决说明")


class StatusTransition(BaseModel):
    """状态机流转"""

    reject_reason: str | None = Field(None, description="打回原因 (回退时填写)")


class PlanFork(BaseModel):
    """Fork派生"""

    title: str = Field(..., max_length=200, description="新教案标题")


# ──────────────────────────────────────────────
# AI学情逆向处方 (Wings 3.1)
# ──────────────────────────────────────────────
class AIBiasGenerateRequest(BaseModel):
    """AI逆向处方生成请求"""

    grade_id: int | None = Field(None, description="年级ID (拉取该年级断层数据)")
    class_id: int | None = Field(
        None, description="班级ID (拉取该班级断层数据, 优先级高于grade_id)"
    )


# ──────────────────────────────────────────────
# 响应模型
# ──────────────────────────────────────────────
class VersionResponse(BaseModel):
    id: int
    plan_id: int
    version_number: int
    editor_id: int
    editor_name: str | None = None
    content: LessonContent
    content_markdown: str | None = None
    change_log: str | None = None
    is_major: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewResponse(BaseModel):
    id: int
    plan_id: int
    version_number: int
    reviewer_id: int
    reviewer_name: str | None = None
    target_section: str
    target_anchor: str | None = None
    comment: str
    severity: str
    is_resolved: bool
    resolved_by: int | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None
    parent_review_id: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class PlanResponse(BaseModel):
    id: int
    school_id: int
    title: str
    description: str | None = None
    subject_code: str
    grade_level: str
    lesson_type: str
    duration: int
    tags: list[str] = []
    status: str
    status_updated_at: datetime | None = None
    current_version: int
    published_version: int | None = None
    reference_count: int = 0
    fork_count: int = 0
    creator_id: int
    creator_name: str | None = None
    grade_leader_id: int | None = None
    forked_from_id: int | None = None
    content_markdown: str | None = None
    ai_bias_prescription: str | None = None
    ai_prescription_generated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PlanDetailResponse(PlanResponse):
    """教案详情 — 含最新版本内容"""

    latest_content: LessonContent | None = None
    latest_version_number: int | None = None
    unresolved_review_count: int = 0


class DashboardStats(BaseModel):
    """教研看板统计"""

    total_plans: int = 0
    draft_count: int = 0
    review_count: int = 0
    approved_count: int = 0
    published_count: int = 0
    total_versions: int = 0
    total_reviews: int = 0
    unresolved_reviews: int = 0
    by_subject: dict[str, int] = {}
    by_grade: dict[str, int] = {}
    top_creators: list[dict[str, Any]] = []
