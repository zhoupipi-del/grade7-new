"""
research_observation/manifest.py — 模块声明契约

听课评课量化追踪：与集体备课教案血缘咬合，多维评分+确认/申诉状态机。
"""

MODULE_CODE = "research_observation"
MODULE_NAME = "听课评课量化追踪"
MODULE_CATEGORY = "research"
MODULE_DEPENDENCIES = ["research_lesson_prep", "teacher_mgmt"]
ENABLED_BY_DEFAULT = False
MODULE_PHASES = ["junior", "senior", "primary"]


def register(router_prefix="/api/v1/research_observation"):
    from modules.research_observation.routers import router

    return router, router_prefix
