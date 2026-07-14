"""
modules/behavior/manifest.py — 违纪行为管理模块声明
"""

MODULE_CODE = "behavior"
MODULE_NAME = "违纪行为管理"
MODULE_CATEGORY = "discipline"
MODULE_DEPENDENCIES = []  # 核心依赖 core 已默认加载


def register(router_prefix="/api/v1/behavior"):
    from modules.behavior.routers import router

    return router, router_prefix
