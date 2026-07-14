"""
modules/risk_models/manifest.py — 风险预警雷达模块声明
"""

MODULE_CODE = "risk_models"
MODULE_NAME = "风险预警雷达"
MODULE_CATEGORY = "ai"
MODULE_DEPENDENCIES = ["behavior", "attendance", "evaluation"]
ENABLED_BY_DEFAULT = False


def register(router_prefix="/api/v1/risk_models"):
    from modules.risk_models.routers import router

    return router, router_prefix
