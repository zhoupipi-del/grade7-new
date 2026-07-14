"""
teacher_mgmt Pydantic 模型

Schema 类:
  TeacherCreate            — 创建教师 (User+Teacher+Extension 一步到位)
  TeacherExtensionCreate   — 更新扩展信息
  TeacherExtensionOut      — 扩展信息响应
  TeacherListItem          — 列表项
  TeacherListResponse      — 列表分页响应
  TeacherDetailOut         — 教师详情
  SubjectAssignment        — 任教学科
  SubjectAssignRequest     — 分配学科请求
  SubjectAssignResponse    — 学科分配响应
  WorkloadCreate           — 创建工作量
  WorkloadOut              — 工作量响应
  WorkloadStatsOut         — 工作量统计
  TeacherRoleAssignmentCreate  — 创建角色分配
  TeacherRoleAssignmentOut     — 角色分配响应
  EffectiveRoleOut             — 有效角色项
  EffectiveRolesOut            — 有效角色集合响应
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ═════════════════════════════════════════════════════════════════════════════════
# 创建教师 (一步到位: User+Teacher+Extension)
# ═════════════════════════════════════════════════════════════════════════════════


class TeacherCreate(BaseModel):
    """创建教师请求 — 同时创建 User+Teacher+TeacherExtension"""

    username: str = Field(..., min_length=3, max_length=50, description="登录账号")
    display_name: str = Field(..., min_length=1, max_length=50, description="显示姓名")
    password: str = Field(..., min_length=6, description="初始密码")
    phone: str | None = Field(None, max_length=20, description="手机号")
    role: str = Field("class_teacher", description="角色: class_teacher / teacher")
    subject: str | None = Field(None, max_length=50, description="主任教科目")
    employee_no: str | None = Field(None, max_length=30, description="工号")
    # TeacherExtension 字段 (可选)
    title: str | None = Field(None, description="职称")
    hired_at: str | None = Field(None, description="入职日期 YYYY-MM-DD")
    education: str | None = Field(None, description="最高学历")
    major: str | None = Field(None, max_length=50, description="专业")
    graduate_school: str | None = Field(None, max_length=100, description="毕业院校")
    max_weekly_hours: int | None = Field(None, ge=0, description="周课时上限")
    contact_phone: str | None = Field(None, max_length=20, description="联系电话")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        allowed = ["class_teacher", "teacher"]
        if v not in allowed:
            raise ValueError(f"role 必须是 {allowed} 之一")
        return v


class TeacherCreateOut(BaseModel):
    """创建教师响应"""

    user_id: int
    teacher_id: int
    extension_id: int
    username: str
    display_name: str
    role: str
    message: str = "教师创建成功"


# ═════════════════════════════════════════════════════════════════════════════════
# 教师扩展信息
# ═════════════════════════════════════════════════════════════════════════════════


class TeacherExtensionCreate(BaseModel):
    """创建/更新教师扩展信息"""

    title: str | None = Field(None, description="职称")
    hired_at: str | None = Field(None, description="入职日期 YYYY-MM-DD")
    office_phone: str | None = Field(None, max_length=20)
    office_location: str | None = Field(None, max_length=100)
    qualifications: list[str] | None = Field(None, description="资质证书列表")
    education: str | None = Field(None, description="最高学历")
    major: str | None = Field(None, max_length=50)
    graduate_school: str | None = Field(None, max_length=100)
    is_active: bool | None = True
    employee_no: str | None = Field(None, max_length=30, description="工号")
    contact_phone: str | None = Field(None, max_length=20, description="联系电话")
    max_weekly_hours: int | None = Field(None, ge=0, description="周课时上限")


class TeacherExtensionOut(BaseModel):
    """教师扩展信息响应"""

    id: int
    user_id: int
    teacher_id: int | None = None
    title: str | None = None
    hired_at: datetime | None = None
    office_phone: str | None = None
    office_location: str | None = None
    qualifications: Any | None = None
    education: str | None = None
    major: str | None = None
    graduate_school: str | None = None
    is_head_teacher: bool = False
    homeroom_grade: str | None = None
    is_active: bool = True
    employee_no: str | None = None
    contact_phone: str | None = None
    max_weekly_hours: int | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ═════════════════════════════════════════════════════════════════════════════════
# 教师列表项 (基于 User + Teacher + TeacherExtension)
# ═════════════════════════════════════════════════════════════════════════════════


class TeacherListItem(BaseModel):
    """教师列表响应项"""

    id: int  # user_id
    display_name: str  # 来自 User
    username: str  # 来自 User
    role: str  # class_teacher / teacher
    phone: str | None = None  # 来自 User
    employee_no: str | None = None  # 来自 Teacher
    subject: str | None = None  # 来自 Teacher
    title: str | None = None  # 来自 TeacherExtension
    is_homeroom: bool = False  # 来自 Teacher
    homeroom_class_id: int | None = None  # 班主任班级ID
    homeroom_class_name: str | None = None  # 班主任班级名
    subjects_taught: list[str] = []  # 任教科目列表
    max_weekly_hours: int | None = None  # 周课时上限
    is_active: bool = True
    created_at: datetime | None = None


class TeacherListResponse(BaseModel):
    """教师列表分页响应"""

    teachers: list[TeacherListItem]
    total: int
    page: int
    page_size: int


# ═════════════════════════════════════════════════════════════════════════════════
# 教师详情
# ═════════════════════════════════════════════════════════════════════════════════


class SubjectAssignment(BaseModel):
    """任教学科"""

    id: int | None = None
    subject_code: str
    subject_name: str
    is_primary: bool = True
    grade_level: str | None = None


class TeacherDetailOut(BaseModel):
    """教师详情响应"""

    user_id: int
    display_name: str
    username: str
    role: str
    phone: str | None = None
    employee_no: str | None = None
    subject: str | None = None
    extension: TeacherExtensionOut | None = None
    subjects_taught: list[SubjectAssignment] = []
    is_homeroom: bool = False
    homeroom_class_id: int | None = None
    homeroom_class_name: str | None = None
    max_weekly_hours: int | None = None
    is_active: bool = True


# ═════════════════════════════════════════════════════════════════════════════════
# 任教学科分配
# ═════════════════════════════════════════════════════════════════════════════════


class SubjectAssignRequest(BaseModel):
    """分配学科请求"""

    subjects: list[SubjectAssignment] = Field(..., min_length=1)


class SubjectAssignResponse(BaseModel):
    """学科分配响应"""

    teacher_user_id: int
    subjects: list[SubjectAssignment]
    message: str = "学科分配成功"


# ═════════════════════════════════════════════════════════════════════════════════
# 工作量统计
# ═════════════════════════════════════════════════════════════════════════════════


class WorkloadCreate(BaseModel):
    """创建工作量记录"""

    semester: str = Field(..., description="学期: 2025-2026-1")
    weekly_periods: int = Field(0, ge=0, description="周课时量")
    class_count: int = Field(0, ge=0)
    subject_count: int = Field(1, ge=1)
    extra_duties: list[str] | None = None


class WorkloadOut(BaseModel):
    """工作量记录响应"""

    id: int
    teacher_user_id: int
    semester: str
    weekly_periods: int
    class_count: int
    subject_count: int
    is_head_teacher: bool
    head_teacher_class_id: int | None = None
    extra_duties: Any | None = None
    total_workload_score: float | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkloadStatsOut(BaseModel):
    """教师工作量统计"""

    teacher_user_id: int
    display_name: str
    total_semesters: int
    avg_weekly_periods: float
    avg_class_count: float
    total_subjects: int
    workloads: list[WorkloadOut]


# ═════════════════════════════════════════════════════════════════════════════════
# 教师角色分配 (双重角色解耦 overlay — BOSS 核心需求)
# ═════════════════════════════════════════════════════════════════════════════════

# 角色类型常量
ROLE_TYPES = [
    "subject_teacher",  # 科任教师
    "homeroom_teacher",  # 班主任
    "grade_leader",  # 年级组长
    "moral_admin",  # 德育处主任
    "research_leader",  # 教研组长
    "prep_leader",  # 备课组长
    "discipline_officer",  # 纪检员
    "counselor",  # 心理辅导员
]

# 作用域类型常量
SCOPE_TYPES = [
    "school",  # 全校
    "grade",  # 年级
    "class",  # 班级
    "subject_group",  # 学科组
]


class TeacherRoleAssignmentCreate(BaseModel):
    """创建角色分配请求"""

    role_type: str = Field(..., description=f"角色类型: {ROLE_TYPES}")
    scope_type: str = Field(..., description=f"作用域类型: {SCOPE_TYPES}")
    scope_id: int | None = Field(None, description="作用域ID, school级为NULL")
    expires_at: str | None = Field(None, description="过期时间 YYYY-MM-DDTHH:MM:SS")
    notes: str | None = Field(None, max_length=255)

    @field_validator("role_type")
    @classmethod
    def validate_role_type(cls, v):
        if v not in ROLE_TYPES:
            raise ValueError(f"role_type 必须是 {ROLE_TYPES} 之一")
        return v

    @field_validator("scope_type")
    @classmethod
    def validate_scope_type(cls, v):
        if v not in SCOPE_TYPES:
            raise ValueError(f"scope_type 必须是 {SCOPE_TYPES} 之一")
        return v


class TeacherRoleAssignmentOut(BaseModel):
    """角色分配响应"""

    id: int
    teacher_user_id: int
    role_type: str
    scope_type: str
    scope_id: int | None = None
    is_active: bool = True
    assigned_at: datetime
    expires_at: datetime | None = None
    assigned_by: int | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TeacherRoleAssignmentList(BaseModel):
    """教师角色分配列表"""

    assignments: list[TeacherRoleAssignmentOut]
    total: int


# ═════════════════════════════════════════════════════════════════════════════════
# 有效角色集合 (resolve_effective_roles)
# ═════════════════════════════════════════════════════════════════════════════════


class EffectiveRoleOut(BaseModel):
    """有效角色项"""

    role_type: str
    scope_type: str
    scope_id: int | None = None
    scope_name: str | None = None  # 解析后的作用域名称 (如"初一"/"2501班")
    is_active: bool = True
    assigned_at: datetime | None = None
    expires_at: datetime | None = None


class EffectiveRolesOut(BaseModel):
    """教师有效角色集合"""

    teacher_user_id: int
    display_name: str
    primary_role: str  # User.role 主角色
    effective_roles: list[EffectiveRoleOut]  # 所有叠加角色
    workload_profile: dict | None = None  # 排课引擎供给侧数据
    permission_scopes: dict | None = None  # 审批流权限切面摘要
