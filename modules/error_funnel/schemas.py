"""error_funnel/schemas.py — Pydantic 请求/响应模型"""

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


# ── 知识点 ──
class KnowledgePointCreate(BaseModel):
    subject_id: int
    name: str = Field(..., max_length=100)
    code: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: int = 0


class KnowledgePointUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class KnowledgePointResponse(BaseModel):
    id: int
    school_id: int
    subject_id: int
    subject_name: Optional[str] = None
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: int = 0
    is_active: bool = True
    created_at: Optional[datetime] = None
    children: Optional[List["KnowledgePointResponse"]] = None

    class Config:
        from_attributes = True


# ── 错题本 ──
class ErrorItemCreate(BaseModel):
    student_id: int
    subject_id: int
    source_type: str = "manual"
    source_id: Optional[int] = None
    source_desc: Optional[str] = None
    question_content: str
    question_type: Optional[str] = None
    student_answer: Optional[str] = None
    correct_answer: Optional[str] = None
    error_type: str = "unknown"
    knowledge_point_ids: Optional[List[int]] = None
    difficulty: Optional[str] = None


class ErrorItemResponse(BaseModel):
    id: int
    school_id: int
    student_id: int
    student_name: Optional[str] = None
    subject_id: int
    subject_name: Optional[str] = None
    source_type: str
    source_id: Optional[int] = None
    source_desc: Optional[str] = None
    question_content: str
    question_type: Optional[str] = None
    student_answer: Optional[str] = None
    correct_answer: Optional[str] = None
    error_type: str
    knowledge_point_ids: Optional[List[int]] = None
    knowledge_point_names: Optional[List[str]] = None
    difficulty: Optional[str] = None
    ai_analysis: Optional[str] = None
    ai_status: str = "pending"
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── 知识点断层 ──
class KnowledgeGapResponse(BaseModel):
    id: int
    school_id: int
    student_id: int
    student_name: Optional[str] = None
    subject_id: int
    subject_name: Optional[str] = None
    knowledge_point_id: int
    knowledge_point_name: str
    error_count: int = 0
    consecutive_errors: int = 0
    last_error_date: Optional[datetime] = None
    last_error_source: Optional[str] = None
    gap_level: str = "watch"
    gap_status: str = "active"
    resolved_at: Optional[datetime] = None
    ai_prescription: Optional[str] = None
    ai_prescription_generated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

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
    top_error_knowledge_points: List[dict] = []
    top_error_students: List[dict] = []
    error_type_distribution: dict = {}
    recent_errors: List[dict] = []


# ── 批量导入 ──
class BatchImportFromExam(BaseModel):
    exam_id: int
    subject_id: int
    threshold: float = Field(60.0, description="得分率低于此阈值视为错题")


KnowledgePointResponse.model_rebuild()
