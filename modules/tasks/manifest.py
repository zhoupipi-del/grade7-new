"""
modules/tasks/manifest.py — Task Center Foundation V1 模块声明
"""

MODULE_CODE = "tasks"
MODULE_NAME = "任务中心（责任闭环底座）"
MODULE_CATEGORY = "governance"
MODULE_DEPENDENCIES = []  # 核心依赖 core 已默认加载；Resolver 在 core.resolver


def register(router_prefix="/api/v1/tasks"):
    from modules.tasks.routers import router

    return router, router_prefix
