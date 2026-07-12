"""
research_activities/manifest.py — 模块声明契约

教研活动管理：活动计划/记录/总结，关联备课教案+听课记录，完成教研全链路闭环。
"""

MODULE_CODE = "research_activities"
MODULE_NAME = "教研活动管理"
MODULE_CATEGORY = "research"
MODULE_DEPENDENCIES = ["research_lesson_prep", "research_observation", "teacher_mgmt"]
ENABLED_BY_DEFAULT = False
MODULE_PHASES = ["junior", "senior", "primary"]


def register(router_prefix="/api/v1/research_activities"):
    from modules.research_activities.routers import router
    return router, router_prefix
