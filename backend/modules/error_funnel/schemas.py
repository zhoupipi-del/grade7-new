"""error_funnel/schemas.py — Pydantic 请求/响应模型"""

from datetime import datetime

from pydantic import BaseModel, Field


# ── 知识点 ──
class KnowledgePointCreate(BaseModel):
    subject_id: int
    name: str = Field(..., max_length=100)
    code: str | None = None
    description: str | None = None
    parent_id: int | None = None
    sort_order: int = 0


class KnowledgePointUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    description: str | None = None
    parent_id: int | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class KnowledgePointResponse(BaseModel):
    id: int
    school_id: int
    subject_id: int
    subject_name: str | None = None
    name: str
    code: str | None = None
    description: str | None = None
    parent_id: int | None = None
    sort_order: int = 0
    is_active: bool = True
    created_at: datetime | None = None
    children: list["KnowledgePointResponse"] | None = None

    class Config:
        from_attributes = True


# ── 错题本 ──
class ErrorItemCreate(BaseModel):
    student_id: int
    subject_id: int
    source_type: str = "manual"
    source_id: int | None = None
    source_desc: str | None = None
    question_content: str
    question_type: str | None = None
    student_answer: str | None = None
    correct_answer: str | None = None
    error_type: str = "unknown"
    knowledge_point_ids: list[int] | None = None
    difficulty: str | None = None


class ErrorItemResponse(BaseModel):
    id: int
    school_id: int
    student_id: int
    student_name: str | None = None
    subject_id: int
    subject_name: str | None = None
    source_type: str
    source_id: int | None = None
    source_desc: str | None = None
    question_content: str
    question_type: str | None = None
    student_answer: str | None = None
    correct_answer: str | None = None
    error_type: str
    knowledge_point_ids: list[int] | None = None
    knowledge_point_names: list[str] | None = None
    difficulty: str | None = None
    ai_analysis: str | None = None
    ai_status: str = "pending"
    is_resolved: bool = False
    resolved_at: datetime | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


# ── 知识点断层 ──
class KnowledgeGapResponse(BaseModel):
    id: int
    school_id: int
    student_id: int
    student_name: str | None = None
    subject_id: int
    subject_name: str | None = None
    knowledge_point_id: int
    knowledge_point_name: str
    error_count: int = 0
    consecutive_errors: int = 0
    last_error_date: datetime | None = None
    last_error_source: str | None = None
    gap_level: str = "watch"
    gap_status: str = "active"
    resolved_at: datetime | None = None
    ai_prescription: str | None = None
    ai_prescription_generated_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


# ── 看板 ──
class DashboardResponse(BaseModel):
    total_errors: int = 0
    unresolved_errors: int = 0
    total_gaps: int = 0
    critical_gaps: int = 0
    warning_gaps: int = 0
    watch_gaps: int = 0
    resolved_gaps: int = 0
    ai_prescriptions_generated: int = 0
    top_error_knowledge_points: list[dict] = []
    top_error_students: list[dict] = []
    error_type_distribution: dict = {}
    recent_errors: list[dict] = []


# ── 批量导入 ──
class BatchImportFromExam(BaseModel):
    exam_id: int
    subject_id: int
    threshold: float = Field(60.0, description="得分率低于此阈值视为错题")


KnowledgePointResponse.model_rebuild()
