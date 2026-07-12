"""
Teacher Management 模块清单
"""

MODULE_CODE = "teacher_mgmt"
MODULE_NAME = "教师管理"
MODULE_CATEGORY = "core"
MODULE_DEPENDENCIES = []
ENABLED_BY_DEFAULT = True
MODULE_PHASES = ["junior", "senior", "primary", "integrated"]


def register(router_prefix="/api/v1/teacher-mgmt"):
    from modules.teacher_mgmt.routers import router
    return router, router_prefix
