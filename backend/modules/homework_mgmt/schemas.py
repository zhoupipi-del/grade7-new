"""homework_mgmt/schemas.py — Pydantic 请求/响应模型"""

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


# ── 错题标记子模型 ──
class ErrorItemCreate(BaseModel):
    question_no: Optional[str] = None
    question_content: str = Field(..., description="题目内容")
    question_type: Optional[str] = None
    student_answer: Optional[str] = None
    correct_answer: Optional[str] = None
    error_type: str = Field(..., description="conceptual/procedural/careless/omission/unknown")
    knowledge_point_ids: Optional[List[int]] = None
    difficulty: Optional[str] = Field(None, description="easy/medium/hard")


class ErrorItemOut(ErrorItemCreate):
    pass


# ── 作业布置 ──
class AssignmentCreate(BaseModel):
    subject_id: int
    class_id: Optional[int] = None
    grade_id: Optional[int] = None
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    homework_type: str = "daily"
    assigned_date: datetime
    due_date: datetime
    knowledge_point_ids: Optional[List[int]] = None
    attachment_url: Optional[str] = None
    total_score: float = 100.0


class AssignmentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    homework_type: Optional[str] = None
    due_date: Optional[datetime] = None
    knowledge_point_ids: Optional[List[int]] = None
    attachment_url: Optional[str] = None
    total_score: Optional[float] = None
    status: Optional[str] = None


class AssignmentResponse(BaseModel):
    id: int
    school_id: int
    teacher_id: int
    teacher_name: Optional[str] = None
    subject_id: int
    subject_name: Optional[str] = None
    class_id: Optional[int] = None
    class_name: Optional[str] = None
    grade_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    homework_type: str
    assigned_date: datetime
    due_date: datetime
    status: str
    knowledge_point_ids: Optional[List[int]] = None
    attachment_url: Optional[str] = None
    total_score: float
    submission_count: int = 0
    graded_count: int = 0
    total_students: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── 学生提交 ──
class SubmissionCreate(BaseModel):
    content: Optional[str] = None
    attachment_url: Optional[str] = None


class SubmissionResponse(BaseModel):
    id: int
    assignment_id: int
    student_id: int
    student_name: Optional[str] = None
    content: Optional[str] = None
    attachment_url: Optional[str] = None
    submitted_at: Optional[datetime] = None
    status: str
    late_minutes: int = 0
    created_at: Optional[datetime] = None
    # 批改信息 (如果有)
    grading: Optional[dict] = None

    class Config:
        from_attributes = True


# ── 教师批改 ──
class GradingCreate(BaseModel):
    score: float = Field(..., description="得分")
    max_score: float = 100.0
    feedback: Optional[str] = None
    error_items: Optional[List[ErrorItemCreate]] = None


class GradingResponse(BaseModel):
    id: int
    submission_id: int
    teacher_id: int
    teacher_name: Optional[str] = None
    score: Optional[float] = None
    max_score: float
    score_percentage: Optional[float] = None
    grade: Optional[str] = None
    feedback: Optional[str] = None
    error_items: Optional[List[dict]] = None
    error_count: int = 0
    graded_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── 看板统计 ──
class DashboardResponse(BaseModel):
    total_assignments: int = 0
    active_assignments: int = 0
    total_submissions: int = 0
    pending_grading: int = 0
    avg_score: Optional[float] = None
    avg_completion_rate: Optional[float] = None
    by_type: dict = {}
    recent_assignments: List[dict] = []
    error_hotspots: List[dict] = []
