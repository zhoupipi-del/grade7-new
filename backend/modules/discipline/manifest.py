"""
modules/discipline/manifest.py — 处分管理模块声明
功能: 处分行政审批 + 生命周期状态机 + 违纪一键升级
"""

MODULE_CODE = "discipline"
MODULE_NAME = "处分管理"
MODULE_CATEGORY = "discipline"
MODULE_DEPENDENCIES = ["behavior"]  # 依赖违纪模块（处分与违纪记录关联）


def register(router_prefix="/api/v1/discipline"):
    from modules.discipline.routers import router

    return router, router_prefix
