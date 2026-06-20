"""
core — Wings 3.0 核心不可禁用模块
提供多租户底座、组织架构、认证鉴权等系统级能力。

所有业务模块的必装前置依赖。
"""

from .models import School, User, Student, Grade, Class, Teacher, SchoolModule
from .services import AuthService, OrgService
from .routers import router as core_router

__all__ = [
    "School", "User", "Student", "Grade", "Class", "Teacher", "SchoolModule",
    "AuthService", "OrgService",
    "core_router",
]
