"""
modules/student_registry/schemas.py — 学籍管理 Pydantic 数据模型
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

# ── 学籍创建 ──


class StudentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    gender: str | None = Field(None, pattern="^(M|F)$")
    birth_date: date | None = None
    id_card: str | None = Field(None, max_length=18)
    nationality: str | None = Field(None, max_length=50, description="民族")
    class_id: int = Field(..., description="班级ID")
    grade_id: int = Field(..., description="年级ID")
    address: str | None = Field(None, max_length=200)
    parent1_name: str | None = None
    parent1_phone: str | None = None
    parent1_relation: str | None = None
    parent2_name: str | None = None
    parent2_phone: str | None = None
    parent2_relation: str | None = None
    national_student_no: str | None = Field(None, description="全国学籍号")
    enrollment_type: str | None = Field("normal", description="入学方式")
    enrolled_at: date | None = None
    auto_generate_no: bool = Field(True, description="是否自动生成学号")


class StudentUpdate(BaseModel):
    name: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    id_card: str | None = None
    nationality: str | None = None
    address: str | None = None
    parent1_name: str | None = None
    parent1_phone: str | None = None
    parent1_relation: str | None = None
    parent2_name: str | None = None
    parent2_phone: str | None = None
    parent2_relation: str | None = None
    national_student_no: str | None = None


# ── 学籍输出 ──


class StudentOut(BaseModel):
    id: int
    name: str
    student_no: str
    school_id: int
    class_id: int
    grade_id: int
    gender: str | None = None
    id_card: str | None = None
    nationality: str | None = None
    birth_date: date | None = None
    address: str | None = None
    parent1_name: str | None = None
    parent1_phone: str | None = None
    parent1_relation: str | None = None
    parent2_name: str | None = None
    parent2_phone: str | None = None
    parent2_relation: str | None = None
    is_active: bool
    enrolled_at: date | None = None
    tags: list | None = None
    # 扩展字段
    registry_status: str | None = "active"
    national_student_no: str | None = None
    enrollment_type: str | None = None
    sync_status: str | None = "native"
    # 冗余
    class_name: str | None = None
    grade_name: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class StudentBrief(BaseModel):
    """
    列表视图专用 —— 刻意不含 PII。
    ⚠️ 任何时候要往这里加字段，先问：这个字段能不能被全校任意账号批量拉走？
       能容忍才加。id_card / address / parent*_phone / nationality 永远不进这里。
    """

    id: int
    name: str
    student_no: str
    class_id: int
    class_name: str | None = None
    registry_status: str | None = "active"
    # ── 2026-07-23 补：列表页表格渲染需要，均非 PII ──
    grade_name: str | None = None
    gender: str | None = None
    sync_status: str | None = "native"
    enrolled_at: date | None = None

    model_config = {"from_attributes": True}


# ── 状态变更 ──


class StatusChangeCreate(BaseModel):
    change_type: str = Field(..., description="transfer/suspend/resume/graduate/inactive")
    reason: str | None = Field(None, max_length=500)
    target_school: str | None = Field(None, description="转入学校（转学用）")
    expected_resume_date: date | None = Field(None, description="预计复学日期（休学用）")
    remark: str | None = None


class StatusChangeOut(BaseModel):
    id: int
    student_id: int
    from_status: str
    to_status: str
    change_type: str
    reason: str | None = None
    target_school: str | None = None
    expected_resume_date: date | None = None
    operated_by: int
    operator_name: str | None = None
    sync_status: str | None = "native"
    remark: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── 批量导入 ──


class BatchImportResult(BaseModel):
    total: int
    success: int
    failed: int
    errors: list[dict] = Field(default_factory=list)
    imported_ids: list[int] = Field(default_factory=list)


# ── 统计 ──


class RegistryStatsOut(BaseModel):
    total_students: int
    by_status: dict  # {"active": 800, "suspended": 5, ...}
    by_grade: dict  # {"七年级": 400, "八年级": 380, ...}
    by_gender: dict  # {"M": 420, "F": 380}
    sync_summary: dict  # {"native": 700, "legacy": 100, "imported": 50}


# ── 分页 ──


class PaginatedStudents(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[StudentBrief]


# ── 新学年滚动晋升 ──


class RolloverRequest(BaseModel):
    school_year: str | None = Field(
        None, description="学年标识，如 2026-2027；不传则按当前年自动推导"
    )
    dry_run: bool = Field(False, description="预览模式：只做预检与计数，不执行任何写操作")
    note: str | None = Field(None, description="加锁备注 / 批次号")
    freshmen: list[dict] | None = Field(
        None, description="可选新生名单（每条需含 name、class_name 等），导入到最低年级"
    )


class RolloverClassInfo(BaseModel):
    grade_id: int
    class_id: int
    name: str


class RolloverResult(BaseModel):
    school_year: str
    status: str
    school_id: int
    lock_id: int | None = None
    snapshot_count: int = 0
    graduated_count: int = 0
    promoted_count: int = 0
    promoted_detail: dict = Field(default_factory=dict)
    freshmen_count: int = 0
    created_classes: list[RolloverClassInfo] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    message: str | None = None
    # 预览模式扩展字段
    total_active_students: int | None = None
    grade_active_counts: dict | None = None
    will_graduate_grade: str | None = None
    will_graduate_count: int | None = None
    will_promote: list[str] | None = None
    freshmen_provided: bool | None = None
