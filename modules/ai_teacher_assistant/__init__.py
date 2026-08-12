"""
modules/ai_teacher_assistant/__init__.py — AI 教师助手模块
"""

from .manifest import MODULE_CODE, MODULE_LABEL, MODULE_ROUTES_PREFIX
from .routers import router

__all__ = ["MODULE_CODE", "MODULE_LABEL", "MODULE_ROUTES_PREFIX", "router"]
