"""
modules/growth/manifest.py — 成长档案模块元信息

P0 重型母舰模块：双表驱动（timeline_events + periodical_snapshots），
聚合 7 路数据源 + 五维归一化快照引擎 + 全息画像。
"""
MODULE_CODE = "growth"
MODULE_NAME = "成长档案"
MODULE_CATEGORY = "engagement"
MODULE_DEPENDENCIES = ["behavior", "discipline", "attendance", "grades", "error_funnel", "psych_profiles"]
ENABLED_BY_DEFAULT = True


def register(router_prefix="/api/v1/growth"):
    """
    模块注册入口 — 由 module_loader 调用。

    返回 (APIRouter, prefix) 元组。
    """
    from modules.growth.routers import router
    return router, router_prefix
