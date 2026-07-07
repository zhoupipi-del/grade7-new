"""
modules/attendance/manifest.py — 考勤管理模块元信息

Wings 3.0 首个验证模块，无前置依赖，独立可插拔。
"""

MODULE_CODE = "attendance"
MODULE_NAME = "考勤管理"
MODULE_CATEGORY = "behavior"
MODULE_DEPENDENCIES = []  # 首期验证模块，零依赖
ENABLED_BY_DEFAULT = True  # 新学校默认开启考勤


def register(router_prefix="/api/v1/attendance"):
    """
    模块注册入口 — 由 module_loader 调用。

    返回 (APIRouter, prefix) 元组。
    """
    from modules.attendance.routers import router
    return router, router_prefix
