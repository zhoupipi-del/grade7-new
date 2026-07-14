"""
modules/dashboard/manifest.py — 大数据看板模块声明
功能: 德育大数据聚合看板 — 班级晴雨表 + 违纪收敛趋势 + 德育成绩关联
"""

MODULE_CODE = "dashboard"
MODULE_NAME = "大数据看板"
MODULE_CATEGORY = "analytics"
MODULE_DEPENDENCIES = ["behavior", "evaluation"]


def register(router_prefix="/api/v1/dashboard"):
    from modules.dashboard.routers import router

    return router, router_prefix
