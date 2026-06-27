"""
modules/growth/manifest.py — 家长端成长时间轴模块元信息

Wings 3.0 数据融合只读模块，无自身 DB 表，
聚合 discipline_records + discipline_sanctions + attendance_records 生成统一时间轴。
"""
MODULE_CODE = "growth"
MODULE_NAME = "成长时间轴"
MODULE_CATEGORY = "engagement"
MODULE_DEPENDENCIES = ["behavior", "discipline", "attendance"]
ENABLED_BY_DEFAULT = True


def register(router_prefix="/api/v1/growth"):
    """
    模块注册入口 — 由 module_loader 调用。

    返回 (APIRouter, prefix) 元组。
    """
    from modules.growth.routers import router
    return router, router_prefix
