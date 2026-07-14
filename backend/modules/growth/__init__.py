"""
modules/growth/__init__.py
Wings 3.0 家长端成长时间轴模块 — 数据融合只读 API
"""

from .manifest import MODULE_CATEGORY, MODULE_CODE, MODULE_NAME
from .routers import router

__all__ = ["MODULE_CODE", "MODULE_NAME", "MODULE_CATEGORY", "router"]
