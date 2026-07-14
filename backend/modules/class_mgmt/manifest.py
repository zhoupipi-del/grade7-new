"""
modules/class_mgmt/manifest.py — 班级管理模块声明
"""

MODULE_CODE = "class_mgmt"
MODULE_NAME = "班级管理"
MODULE_CATEGORY = "core"
MODULE_DEPENDENCIES = ["student_registry"]
ENABLED_BY_DEFAULT = True
MODULE_PHASES = []


def register(router_prefix="/api/v1/class-mgmt"):
    from modules.class_mgmt.routers import router

    return router, router_prefix
