"""
modules/class_mgmt/schemas.py — 班级管理 Pydantic 数据模型
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class ClassCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    grade_id: int
    head_teacher_id: Optional[int] = None
    class_slogan: Optional[str] = None


class ClassUpdate(BaseModel):
    name: Optional[str] = None
    head_teacher_id: Optional[int] = None
    is_active: Optional[bool] = None
    class_slogan: Optional[str] = None


class ClassOut(BaseModel):
    id: int
    name: str
    school_id: int
    grade_id: int
    head_teacher_id: Optional[int] = None
    head_teacher_name: Optional[str] = None
    student_count: int
    is_active: bool
    # 扩展
    class_slogan: Optional[str] = None
    class_features: Optional[list] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AssignStudentsRequest(BaseModel):
    student_ids: List[int] = Field(..., min_length=1)


class TransferStudentRequest(BaseModel):
    student_id: int
    target_class_id: int
    reason: Optional[str] = None


class AssignTeacherRequest(BaseModel):
    head_teacher_id: int


class MergeClassesRequest(BaseModel):
    source_class_ids: List[int] = Field(..., min_length=2)
    target_class_id: int
    remark: Optional[str] = None


class SplitClassRequest(BaseModel):
    source_class_id: int
    new_class_name: str
    student_ids: List[int] = Field(..., min_length=1)
    new_head_teacher_id: Optional[int] = None


class ClassChangeLogOut(BaseModel):
    id: int
    class_id: int
    change_type: str
    affected_students: Optional[list] = None
    from_class_id: Optional[int] = None
    to_class_id: Optional[int] = None
    operated_by: int
    operator_name: Optional[str] = None
    remark: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ClassStatsOut(BaseModel):
    total_classes: int
    total_students: int
    avg_class_size: float
    by_grade: dict  # {"七年级": {"classes": 8, "students": 389}}
    largest_class: Optional[dict] = None
    smallest_class: Optional[dict] = None
