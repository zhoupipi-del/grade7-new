"""
modules/grades/manifest.py — 成绩管理模块声明
"""

MODULE_CODE = "grades"
MODULE_NAME = "成绩管理"
MODULE_CATEGORY = "academic"
MODULE_DEPENDENCIES = []  # 核心依赖 core 已默认加载


def register(router_prefix="/api/v1/grades"):
    from modules.grades.routers import router

    return router, router_prefix
