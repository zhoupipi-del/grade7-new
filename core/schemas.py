"""
core/schemas.py — Wings 3.0 核心 Pydantic 数据模型
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class UserRoleEnum(str, Enum):  # noqa: UP042 — 保持 str+Enum 兼容 Python<3.11,不改 StrEnum
    MS_ADMIN = "ms_admin"
    GRADE_LEADER = "grade_leader"
    CLASS_TEACHER = "class_teacher"
    TEACHER = "teacher"
    COUNSELOR = "counselor"
    GROUP_ADMIN = "group_admin"
    BRANCH_ADMIN = "branch_admin"
    PARENT = "parent"
    STUDENT = "student"


# ── 认证 ──


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"
    password_change_required: bool = False


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: UserRoleEnum
    school_id: int
    school_name: str | None = None
    school_phase: str | None = "junior"
    plugin_config: dict | None = None
    grade_id: int | None = None
    class_id: int | None = None
    is_active: bool
    password_change_required: bool = False

    model_config = {"from_attributes": True}


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


# ── 学校 ──


class SchoolOut(BaseModel):
    id: int
    name: str
    school_phase: str | None = "junior"
    plugin_config: dict | None = None
    is_active: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SchoolCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)


# ── 模块配置 ──


class SchoolModuleOut(BaseModel):
    id: int
    school_id: int
    module_code: str
    enabled: bool
    config: dict | None = None
    enabled_at: datetime | None = None
    disabled_at: datetime | None = None

    model_config = {"from_attributes": True}


class SchoolModuleUpdate(BaseModel):
    enabled: bool
    config: dict | None = None


# ── 学生 ──


class StudentOut(BaseModel):
    id: int
    name: str
    student_no: str
    school_id: int
    class_id: int
    grade_id: int
    gender: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class StudentBrief(BaseModel):
    """列表用轻量学生视图"""

    id: int
    name: str
    student_no: str
    class_id: int
    grade_id: int
    gender: str | None = None
    is_active: bool
    class_name: str | None = None
    grade_name: str | None = None

    model_config = {"from_attributes": True}


# ── 班级 ──


class ClassOut(BaseModel):
    id: int
    name: str
    school_id: int
    grade_id: int
    head_teacher_id: int | None = None
    student_count: int
    is_active: bool
    grade_name: str | None = None
    head_teacher_name: str | None = None

    model_config = {"from_attributes": True}


# ── 年级 ──


class GradeOut(BaseModel):
    id: int
    name: str
    school_id: int
    sort_order: int
    is_active: bool

    model_config = {"from_attributes": True}


# ── 分页 ──


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    per_page: int
    pages: int


# ── 通用 ──


class MessageResponse(BaseModel):
    message: str
    detail: str | None = None


# ── 工作台（Workstation，2026-08-13）──


class WorkstationOut(BaseModel):
    identity: str
    label: str
    scope_type: str
    scope_id: Optional[int] = None
    scope_name: str = ""
    title: str = ""
    is_default: bool = False


class WorkstationsOut(BaseModel):
    workstations: list[WorkstationOut]
    default_identity: Optional[str] = None


# ── 工作台摘要（Workspace Summary，2026-08-13 班主任工作台 V1）──


class WorkspaceScopeOut(BaseModel):
    type: str
    id: Optional[int] = None
    name: str = ""


class WorkspaceCardsOut(BaseModel):
    student_count: Optional[int] = None
    class_count: Optional[int] = None
    trusted_behavior_count: Optional[int] = None
    trusted_praise_count: Optional[int] = None
    open_tasks: Optional[list] = None


class WorkspaceAttentionItem(BaseModel):
    type: str
    level: str = "info"
    title: str
    hint: str = ""


class WorkspaceDataQualityOut(BaseModel):
    behavior: str = "source_unverified"
    praise: str = "source_unverified"
    attendance: str = "source_unverified"
    grades: str = "source_unverified"


class WorkspaceSummaryOut(BaseModel):
    workspace: str
    scope: WorkspaceScopeOut
    cards: WorkspaceCardsOut
    attention: list[WorkspaceAttentionItem] = []
    class_compare: list[dict] = []
    data_quality: WorkspaceDataQualityOut


# ── 责任归属解析（ResponsibleOwnerResolver V1，2026-08-13）──


class ResolveConflictItem(BaseModel):
    user_id: int
    username: Optional[str] = None


class ResolveOut(BaseModel):
    resolved: bool
    owner: Optional[int] = None
    owner_name: Optional[str] = None
    owner_role: Optional[str] = None
    role_type: Optional[str] = None
    scope_type: Optional[str] = None
    scope_id: Optional[int] = None
    source: str = "unresolved"
    confidence: Optional[str] = None
    unresolved_reason: Optional[str] = None
    conflict: list[ResolveConflictItem] = []
