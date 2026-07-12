"""
Timetable 模块清单
"""

MODULE_CODE = "timetable"
MODULE_NAME = "课程表管理"
MODULE_CATEGORY = "academic"
MODULE_DEPENDENCIES = ["teacher_mgmt"]
ENABLED_BY_DEFAULT = True
MODULE_PHASES = ["junior", "senior", "primary", "integrated"]


def register(router_prefix="/api/v1/timetable"):
    from modules.timetable.routers import router
    return router, router_prefix
