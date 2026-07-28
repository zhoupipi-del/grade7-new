"""
research_profile/manifest.py — 模块声明契约

教师教研全息画像：跨模块聚合，不建新表。
"""

MODULE_CODE = "research"
MODULE_NAME = "教师教研全息画像"
MODULE_CATEGORY = "research"
MODULE_DEPENDENCIES = [
    "research_lesson_prep",
    "research_observation",
    "research_activities",
    "error_funnel",
    "teacher_mgmt",
]
ENABLED_BY_DEFAULT = False
MODULE_PHASES = ["junior", "senior", "primary"]


def register(router_prefix="/api/v1/research"):
    from modules.research_profile.routers import router

    return router, router_prefix
