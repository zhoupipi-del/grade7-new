"""
modules/student_registry/manifest.py — 学籍管理模块声明
"""

MODULE_CODE = "student_registry"
MODULE_NAME = "学籍管理"
MODULE_CATEGORY = "core"
MODULE_DEPENDENCIES = []
ENABLED_BY_DEFAULT = True
MODULE_PHASES = []  # 全学段开放

def register(router_prefix="/api/v1/student-registry"):
    from modules.student_registry.routers import router
    return router, router_prefix
