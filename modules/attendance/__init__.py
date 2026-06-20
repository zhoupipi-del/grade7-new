"""
modules/attendance/__init__.py
Wings 3.0 考勤管理模块 — 首个验证模块
"""

from .manifest import MODULE_CODE, MODULE_NAME, MODULE_CATEGORY
from .routers import router

__all__ = ["MODULE_CODE", "MODULE_NAME", "MODULE_CATEGORY", "router"]
