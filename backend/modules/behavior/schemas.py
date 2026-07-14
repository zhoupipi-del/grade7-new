"""
modules/behavior/schemas.py — 违纪行为 Pydantic 数据模型
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

# ── 违纪记录 ──


class DisciplineCreate(BaseModel):
    student_id: int
    type: str = Field(..., description="违纪级别: warning/minor/major/serious")
    category: str | None = Field(None, description="违纪类别: 打架/吸烟/迟到/仪容/课堂/其他")
    description: str = Field(..., min_length=1, max_length=500)
    action_taken: str | None = Field(None, max_length=500)
    points: int = Field(0, ge=0)
    incident_date: date | None = None


class DisciplineUpdate(BaseModel):
    type: str | None = None
    category: str | None = None
    description: str | None = None
    action_taken: str | None = None
    points: int | None = None
    incident_date: date | None = None


class DisciplineOut(BaseModel):
    id: int
    student_id: int
    student_name: str | None = None
    student_no: str | None = None
    class_id: int
    class_name: str | None = None
    grade_id: int
    type: str
    category: str | None = None
    description: str
    action_taken: str | None = None
    points: int
    status: str
    verify_status: str
    incident_date: date | None = None
    created_by: int
    creator_name: str | None = None
    created_at: datetime | None = None
    resolved_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── 统计 ──


class DisciplineStatsOut(BaseModel):
    total: int
    by_type: dict  # {"warning": 5, "minor": 3, ...}
    by_category: dict  # {"打架": 2, "迟到": 6, ...}
    by_class: dict  # {"2501": 4, "2502": 3, ...}
    total_points: int
    monthly_trend: list[dict]  # [{"month": "06", "year": 2026, "count": 12}, ...]


# ── 申诉 ──


class AppealCreate(BaseModel):
    discipline_id: int
    reason: str = Field(..., min_length=1, max_length=500)


class AppealReview(BaseModel):
    status: str = Field(..., description="approved/rejected")
    review_comment: str | None = None


class AppealOut(BaseModel):
    id: int
    discipline_id: int
    student_id: int
    student_name: str | None = None
    reason: str
    status: str
    review_comment: str | None = None
    reviewer_name: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
