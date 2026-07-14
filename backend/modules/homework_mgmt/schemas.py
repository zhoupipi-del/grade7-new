"""homework_mgmt/schemas.py — Pydantic 请求/响应模型"""

from datetime import datetime

from pydantic import BaseModel, Field


# ── 错题标记子模型 ──
class ErrorItemCreate(BaseModel):
    question_no: str | None = None
    question_content: str = Field(..., description="题目内容")
    question_type: str | None = None
    student_answer: str | None = None
    correct_answer: str | None = None
    error_type: str = Field(..., description="conceptual/procedural/careless/omission/unknown")
    knowledge_point_ids: list[int] | None = None
    difficulty: str | None = Field(None, description="easy/medium/hard")


class ErrorItemOut(ErrorItemCreate):
    pass


# ── 作业布置 ──
class AssignmentCreate(BaseModel):
    subject_id: int
    class_id: int | None = None
    grade_id: int | None = None
    title: str = Field(..., max_length=200)
    description: str | None = None
    homework_type: str = "daily"
    assigned_date: datetime
    due_date: datetime
    knowledge_point_ids: list[int] | None = None
    attachment_url: str | None = None
    total_score: float = 100.0


class AssignmentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    homework_type: str | None = None
    due_date: datetime | None = None
    knowledge_point_ids: list[int] | None = None
    attachment_url: str | None = None
    total_score: float | None = None
    status: str | None = None


class AssignmentResponse(BaseModel):
    id: int
    school_id: int
    teacher_id: int
    teacher_name: str | None = None
    subject_id: int
    subject_name: str | None = None
    class_id: int | None = None
    class_name: str | None = None
    grade_id: int | None = None
    title: str
    description: str | None = None
    homework_type: str
    assigned_date: datetime
    due_date: datetime
    status: str
    knowledge_point_ids: list[int] | None = None
    attachment_url: str | None = None
    total_score: float
    submission_count: int = 0
    graded_count: int = 0
    total_students: int = 0
    created_at: datetime | None = None

    class Config:
        from_attributes = True


# ── 学生提交 ──
class SubmissionCreate(BaseModel):
    content: str | None = None
    attachment_url: str | None = None


class SubmissionResponse(BaseModel):
    id: int
    assignment_id: int
    student_id: int
    student_name: str | None = None
    content: str | None = None
    attachment_url: str | None = None
    submitted_at: datetime | None = None
    status: str
    late_minutes: int = 0
    created_at: datetime | None = None
    # 批改信息 (如果有)
    grading: dict | None = None

    class Config:
        from_attributes = True


# ── 教师批改 ──
class GradingCreate(BaseModel):
    score: float = Field(..., description="得分")
    max_score: float = 100.0
    feedback: str | None = None
    error_items: list[ErrorItemCreate] | None = None


class GradingResponse(BaseModel):
    id: int
    submission_id: int
    teacher_id: int
    teacher_name: str | None = None
    score: float | None = None
    max_score: float
    score_percentage: float | None = None
    grade: str | None = None
    feedback: str | None = None
    error_items: list[dict] | None = None
    error_count: int = 0
    graded_at: datetime | None = None

    class Config:
        from_attributes = True


# ── 看板统计 ──
class DashboardResponse(BaseModel):
    total_assignments: int = 0
    active_assignments: int = 0
    total_submissions: int = 0
    pending_grading: int = 0
    avg_score: float | None = None
    avg_completion_rate: float | None = None
    by_type: dict = {}
    recent_assignments: list[dict] = []
    error_hotspots: list[dict] = []
