"""
modules/class_mgmt/schemas.py — 班级管理 Pydantic 数据模型
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ClassCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    grade_id: int
    head_teacher_id: int | None = None
    class_slogan: str | None = None


class ClassUpdate(BaseModel):
    name: str | None = None
    head_teacher_id: int | None = None
    is_active: bool | None = None
    class_slogan: str | None = None


class ClassOut(BaseModel):
    id: int
    name: str
    school_id: int
    grade_id: int
    head_teacher_id: int | None = None
    head_teacher_name: str | None = None
    student_count: int
    is_active: bool
    # 扩展
    class_slogan: str | None = None
    class_features: list | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AssignStudentsRequest(BaseModel):
    student_ids: list[int] = Field(..., min_length=1)


class TransferStudentRequest(BaseModel):
    student_id: int
    target_class_id: int
    reason: str | None = None


class AssignTeacherRequest(BaseModel):
    head_teacher_id: int


class MergeClassesRequest(BaseModel):
    source_class_ids: list[int] = Field(..., min_length=2)
    target_class_id: int
    remark: str | None = None


class SplitClassRequest(BaseModel):
    source_class_id: int
    new_class_name: str
    student_ids: list[int] = Field(..., min_length=1)
    new_head_teacher_id: int | None = None


class ClassChangeLogOut(BaseModel):
    id: int
    class_id: int
    change_type: str
    affected_students: list | None = None
    from_class_id: int | None = None
    to_class_id: int | None = None
    operated_by: int
    operator_name: str | None = None
    remark: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ClassStatsOut(BaseModel):
    total_classes: int
    total_students: int
    avg_class_size: float
    by_grade: dict  # {"七年级": {"classes": 8, "students": 389}}
    largest_class: dict | None = None
    smallest_class: dict | None = None
