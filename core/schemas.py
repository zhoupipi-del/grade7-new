"""
core/schemas.py — Wings 3.0 核心 Pydantic 数据模型
"""

from typing import Optional, List, Any
from datetime import datetime, date
from pydantic import BaseModel, Field
from enum import Enum


class UserRoleEnum(str, Enum):
    MS_ADMIN = "ms_admin"
    GRADE_LEADER = "grade_leader"
    CLASS_TEACHER = "class_teacher"
    TEACHER = "teacher"
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


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: UserRoleEnum
    school_id: int
    school_name: Optional[str] = None
    grade_id: Optional[int] = None
    class_id: Optional[int] = None
    is_active: bool

    model_config = {"from_attributes": True}


# ── 学校 ──

class SchoolOut(BaseModel):
    id: int
    name: str
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SchoolCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)


# ── 模块配置 ──

class SchoolModuleOut(BaseModel):
    id: int
    school_id: int
    module_code: str
    enabled: bool
    config: Optional[dict] = None
    enabled_at: Optional[datetime] = None
    disabled_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SchoolModuleUpdate(BaseModel):
    enabled: bool
    config: Optional[dict] = None


# ── 学生 ──

class StudentOut(BaseModel):
    id: int
    name: str
    student_no: str
    school_id: int
    class_id: int
    grade_id: int
    gender: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


# ── 通用 ──

class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None
