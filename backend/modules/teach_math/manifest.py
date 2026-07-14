"""
modules/teach_math/manifest.py — 数学教学辅助模块声明
"""

MODULE_CODE = "teach_math"
MODULE_NAME = "数学教学辅助"
MODULE_CATEGORY = "academic"
MODULE_DEPENDENCIES = []  # 核心依赖 core 已默认加载


def register(router_prefix="/api/v1/teach-math"):
    from modules.teach_math.routers import router

    return router, router_prefix
