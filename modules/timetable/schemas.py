"""
timetable Pydantic 模型 — 适配生产DB列结构
"""

from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field


# ── 教室 ──

class ClassroomCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    building: Optional[str] = None
    floor: Optional[int] = None
    capacity: int = Field(50, ge=1)
    room_type: str = Field("standard")

class ClassroomOut(BaseModel):
    id: int
    name: str
    building: Optional[str] = None
    floor: Optional[int] = None
    capacity: int
    room_type: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ── 课程 ──

class CourseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    short_name: Optional[str] = None
    subject_category: str = Field("elective")
    color: Optional[str] = "#409EFF"
    weekly_slots: int = Field(1, ge=1, le=20)

class CourseOut(BaseModel):
    id: int
    name: str
    short_name: Optional[str] = None
    subject_category: str
    color: Optional[str] = None
    weekly_slots: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ── 课节 ──

class CourseSlotCreate(BaseModel):
    class_id: int
    course_id: int
    teacher_id: int
    classroom_id: Optional[int] = None
    day_of_week: int = Field(..., ge=1, le=7)
    slot_number: int = Field(..., ge=1, le=10)
    week_pattern: str = Field("all")
    semester: str = Field(..., min_length=1)

class CourseSlotOut(BaseModel):
    id: int
    class_id: int
    course_id: int
    course_name: str = ""
    teacher_id: int
    teacher_name: str = ""
    classroom_id: Optional[int] = None
    classroom_name: str = ""
    day_of_week: int
    slot_number: int
    week_pattern: str
    semester: str
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# ── 周视图 ──

class WeeklySlotOut(BaseModel):
    """周课表单个课节视图"""
    id: int
    course_name: str
    subject_category: str = ""
    teacher_name: str
    classroom_name: str
    slot_number: int
    week_pattern: str

class WeeklyScheduleOut(BaseModel):
    """班级周课表"""
    class_id: int
    class_name: str
    grade_name: str
    semester: str
    schedule: dict[str, list[WeeklySlotOut]]


# ── 冲突检测 ──

class ConflictDetail(BaseModel):
    """单条冲突详情"""
    conflict_type: str
    severity: str
    entity_a: Optional[dict[str, Any]] = None
    entity_b: Optional[dict[str, Any]] = None
    conflict_detail: str

class ConflictCheckResult(BaseModel):
    """冲突检测结果"""
    has_conflicts: bool
    conflict_count: int
    conflicts: List[ConflictDetail]

class ConflictOut(BaseModel):
    """冲突记录响应"""
    id: int
    slot_id_1: int
    slot_id_2: int
    conflict_type: str
    description: Optional[str] = None
    severity: str
    is_resolved: bool
    resolved_by: Optional[int] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    model_config = {"from_attributes": True}


# ── 教师课表 ──

class TeacherWeeklySlotOut(BaseModel):
    """教师课表单个课节"""
    id: int
    class_name: str
    course_name: str
    classroom_name: str
    slot_number: int

class TeacherWeeklyScheduleOut(BaseModel):
    """教师周课表"""
    teacher_id: int
    teacher_name: str
    semester: str
    schedule: dict[str, list[TeacherWeeklySlotOut]]


# ── 教务变轨 (Wings 3.1 阵地⑦) ──

class TimetableAdjustmentRequest(BaseModel):
    """教务变轨请求 — 调课/代课"""
    subject_id: int = Field(..., description="新替换的学科ID")
    teacher_id: int = Field(..., description="新指派的授课教师ID")
    adjustment_reason: Optional[str] = Field(None, max_length=255, description="调课/代课原因说明")
