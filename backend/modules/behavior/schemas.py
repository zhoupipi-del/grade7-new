"""
modules/behavior/schemas.py — 违纪行为 Pydantic 数据模型
"""

from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field


# ── 违纪记录 ──

class DisciplineCreate(BaseModel):
    student_id: int
    type: str = Field(..., description="违纪级别: warning/minor/major/serious")
    category: Optional[str] = Field(None, description="违纪类别: 打架/吸烟/迟到/仪容/课堂/其他")
    description: str = Field(..., min_length=1, max_length=500)
    action_taken: Optional[str] = Field(None, max_length=500)
    points: int = Field(0, ge=0)
    incident_date: Optional[date] = None


class DisciplineUpdate(BaseModel):
    type: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    action_taken: Optional[str] = None
    points: Optional[int] = None
    incident_date: Optional[date] = None


class DisciplineOut(BaseModel):
    id: int
    student_id: int
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    class_id: int
    class_name: Optional[str] = None
    grade_id: int
    type: str
    category: Optional[str] = None
    description: str
    action_taken: Optional[str] = None
    points: int
    status: str
    verify_status: str
    incident_date: Optional[date] = None
    created_by: int
    creator_name: Optional[str] = None
    created_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── 统计 ──

class DisciplineStatsOut(BaseModel):
    total: int
    by_type: dict  # {"warning": 5, "minor": 3, ...}
    by_category: dict  # {"打架": 2, "迟到": 6, ...}
    by_class: dict  # {"2501": 4, "2502": 3, ...}
    total_points: int
    monthly_trend: List[dict]  # [{"month": "06", "year": 2026, "count": 12}, ...]


# ── 申诉 ──

class AppealCreate(BaseModel):
    discipline_id: int
    reason: str = Field(..., min_length=1, max_length=500)


class AppealReview(BaseModel):
    status: str = Field(..., description="approved/rejected")
    review_comment: Optional[str] = None


class AppealOut(BaseModel):
    id: int
    discipline_id: int
    student_id: int
    student_name: Optional[str] = None
    reason: str
    status: str
    review_comment: Optional[str] = None
    reviewer_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
