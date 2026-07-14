"""
modules/lineage/manifest.py — 数据血缘追踪模块声明
"""

MODULE_CODE = "lineage"
MODULE_NAME = "数据血缘追踪"
MODULE_CATEGORY = "infrastructure"
MODULE_DEPENDENCIES = []  # 核心依赖 core 已默认加载


def register(router_prefix="/api/v1/lineage"):
    from modules.lineage.routers import router

    return router, router_prefix
