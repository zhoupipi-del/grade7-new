"""
research_lesson_prep/manifest.py — 模块声明契约

集体备课协同编辑引擎：版本控制+批注评审+状态机闭环。
"""

MODULE_CODE = "research_lesson_prep"
MODULE_NAME = "集体备课协同编辑引擎"
MODULE_CATEGORY = "research"
MODULE_DEPENDENCIES = ["teacher_mgmt", "class_mgmt"]
ENABLED_BY_DEFAULT = False
MODULE_PHASES = ["junior", "senior", "primary"]


def register(router_prefix="/api/v1/research_lesson_prep"):
    from modules.research_lesson_prep.routers import router
    return router, router_prefix
