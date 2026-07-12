"""
modules/student_registry/schemas.py — 学籍管理 Pydantic 数据模型
"""

from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, Field


# ── 学籍创建 ──

class StudentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    gender: Optional[str] = Field(None, pattern="^(M|F)$")
    birth_date: Optional[date] = None
    id_card: Optional[str] = Field(None, max_length=18)
    nationality: Optional[str] = Field(None, max_length=50, description="民族")
    class_id: int = Field(..., description="班级ID")
    grade_id: int = Field(..., description="年级ID")
    address: Optional[str] = Field(None, max_length=200)
    parent1_name: Optional[str] = None
    parent1_phone: Optional[str] = None
    parent1_relation: Optional[str] = None
    parent2_name: Optional[str] = None
    parent2_phone: Optional[str] = None
    parent2_relation: Optional[str] = None
    national_student_no: Optional[str] = Field(None, description="全国学籍号")
    enrollment_type: Optional[str] = Field("normal", description="入学方式")
    enrolled_at: Optional[date] = None
    auto_generate_no: bool = Field(True, description="是否自动生成学号")


class StudentUpdate(BaseModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[date] = None
    id_card: Optional[str] = None
    nationality: Optional[str] = None
    address: Optional[str] = None
    parent1_name: Optional[str] = None
    parent1_phone: Optional[str] = None
    parent1_relation: Optional[str] = None
    parent2_name: Optional[str] = None
    parent2_phone: Optional[str] = None
    parent2_relation: Optional[str] = None
    national_student_no: Optional[str] = None


# ── 学籍输出 ──

class StudentOut(BaseModel):
    id: int
    name: str
    student_no: str
    school_id: int
    class_id: int
    grade_id: int
    gender: Optional[str] = None
    id_card: Optional[str] = None
    nationality: Optional[str] = None
    birth_date: Optional[date] = None
    address: Optional[str] = None
    parent1_name: Optional[str] = None
    parent1_phone: Optional[str] = None
    parent1_relation: Optional[str] = None
    parent2_name: Optional[str] = None
    parent2_phone: Optional[str] = None
    parent2_relation: Optional[str] = None
    is_active: bool
    enrolled_at: Optional[date] = None
    tags: Optional[list] = None
    # 扩展字段
    registry_status: Optional[str] = "active"
    national_student_no: Optional[str] = None
    enrollment_type: Optional[str] = None
    sync_status: Optional[str] = "native"
    # 冗余
    class_name: Optional[str] = None
    grade_name: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class StudentBrief(BaseModel):
    id: int
    name: str
    student_no: str
    class_id: int
    class_name: Optional[str] = None
    registry_status: Optional[str] = "active"

    model_config = {"from_attributes": True}


# ── 状态变更 ──

class StatusChangeCreate(BaseModel):
    change_type: str = Field(..., description="transfer/suspend/resume/graduate/inactive")
    reason: Optional[str] = Field(None, max_length=500)
    target_school: Optional[str] = Field(None, description="转入学校（转学用）")
    expected_resume_date: Optional[date] = Field(None, description="预计复学日期（休学用）")
    remark: Optional[str] = None


class StatusChangeOut(BaseModel):
    id: int
    student_id: int
    from_status: str
    to_status: str
    change_type: str
    reason: Optional[str] = None
    target_school: Optional[str] = None
    expected_resume_date: Optional[date] = None
    operated_by: int
    operator_name: Optional[str] = None
    sync_status: Optional[str] = "native"
    remark: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── 批量导入 ──

class BatchImportResult(BaseModel):
    total: int
    success: int
    failed: int
    errors: List[dict] = Field(default_factory=list)
    imported_ids: List[int] = Field(default_factory=list)


# ── 统计 ──

class RegistryStatsOut(BaseModel):
    total_students: int
    by_status: dict  # {"active": 800, "suspended": 5, ...}
    by_grade: dict   # {"七年级": 400, "八年级": 380, ...}
    by_gender: dict  # {"M": 420, "F": 380}
    sync_summary: dict  # {"native": 700, "legacy": 100, "imported": 50}


# ── 分页 ──

class PaginatedStudents(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[StudentOut]
