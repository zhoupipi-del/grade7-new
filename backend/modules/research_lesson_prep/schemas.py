"""
research_lesson_prep/schemas.py — Pydantic 强类型校验契约
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime


# ──────────────────────────────────────────────
# 教案内容结构
# ──────────────────────────────────────────────
class TeachingProcessStep(BaseModel):
    """教学过程单步"""
    phase: str = Field(..., description="环节: 导入/新授/练习/小结/作业")
    duration: int = Field(default=5, description="时长(分钟)")
    content: str = Field("", description="教学内容")
    activities: List[str] = Field(default=[], description="教学活动")
    resources: List[str] = Field(default=[], description="教学资源/教具")


class LessonContent(BaseModel):
    """结构化教案内容"""
    teaching_objectives: List[str] = Field(default=[], description="教学目标")
    key_points: List[str] = Field(default=[], description="教学重点")
    difficulties: List[str] = Field(default=[], description="教学难点")
    teaching_methods: List[str] = Field(default=[], description="教学方法")
    teaching_process: List[TeachingProcessStep] = Field(default=[], description="教学过程")
    homework: List[str] = Field(default=[], description="课后作业")
    blackboard_design: str = Field("", description="板书设计")
    reflection: str = Field("", description="教学反思(课后填写)")


# ──────────────────────────────────────────────
# 请求模型
# ──────────────────────────────────────────────
class PlanCreate(BaseModel):
    """创建备课主案"""
    title: str = Field(..., min_length=1, max_length=200, description="教案标题")
    description: Optional[str] = None
    subject_code: str = Field(..., description="学科代码")
    grade_level: str = Field(..., description="年级")
    lesson_type: str = Field("new", description="课型: new/review/exam/test/activity")
    duration: int = Field(1, ge=1, le=10, description="课时数")
    tags: List[str] = Field(default=[], description="标签")
    content: LessonContent = Field(default=LessonContent(), description="初始教案内容")
    change_log: str = Field("初始创建", description="版本说明")


class PlanUpdate(BaseModel):
    """更新教案元信息 (不动内容)"""
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    lesson_type: Optional[str] = None
    duration: Optional[int] = Field(None, ge=1, le=10)
    tags: Optional[List[str]] = None


class VersionCreate(BaseModel):
    """创建新版本 (保存内容快照)"""
    content: LessonContent = Field(..., description="教案内容")
    change_log: str = Field("内容更新", description="变更说明")
    is_major: bool = Field(False, description="是否重大修订")


class ReviewCreate(BaseModel):
    """添加批注"""
    version_number: int = Field(..., ge=1, description="批注针对的版本号")
    target_section: str = Field(..., description="教案组件路径")
    target_anchor: Optional[str] = None
    comment: str = Field(..., min_length=1, description="批注正文")
    severity: str = Field("suggestion", description="严重度: suggestion/issue/critical")
    parent_review_id: Optional[int] = None


class ReviewResolve(BaseModel):
    """解决批注"""
    resolution_note: str = Field("", description="解决说明")


class StatusTransition(BaseModel):
    """状态机流转"""
    reject_reason: Optional[str] = Field(None, description="打回原因 (回退时填写)")


class PlanFork(BaseModel):
    """Fork派生"""
    title: str = Field(..., max_length=200, description="新教案标题")


# ──────────────────────────────────────────────
# 响应模型
# ──────────────────────────────────────────────
class VersionResponse(BaseModel):
    id: int
    plan_id: int
    version_number: int
    editor_id: int
    editor_name: Optional[str] = None
    content: LessonContent
    change_log: Optional[str] = None
    is_major: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewResponse(BaseModel):
    id: int
    plan_id: int
    version_number: int
    reviewer_id: int
    reviewer_name: Optional[str] = None
    target_section: str
    target_anchor: Optional[str] = None
    comment: str
    severity: str
    is_resolved: bool
    resolved_by: Optional[int] = None
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    parent_review_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PlanResponse(BaseModel):
    id: int
    school_id: int
    title: str
    description: Optional[str] = None
    subject_code: str
    grade_level: str
    lesson_type: str
    duration: int
    tags: List[str] = []
    status: str
    status_updated_at: Optional[datetime] = None
    current_version: int
    published_version: Optional[int] = None
    reference_count: int = 0
    fork_count: int = 0
    creator_id: int
    creator_name: Optional[str] = None
    grade_leader_id: Optional[int] = None
    forked_from_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PlanDetailResponse(PlanResponse):
    """教案详情 — 含最新版本内容"""
    latest_content: Optional[LessonContent] = None
    latest_version_number: Optional[int] = None
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
    by_subject: Dict[str, int] = {}
    by_grade: Dict[str, int] = {}
    top_creators: List[Dict[str, Any]] = []
