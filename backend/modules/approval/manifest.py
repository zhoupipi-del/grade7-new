"""
modules/approval/manifest.py — 审批引擎模块元信息

Phase 2B: 双轨超时扫描器 (Celery 异步)
Phase 3B: 多租户动态审批链 (TenantApprovalChain CRUD API)
"""

MODULE_CODE = "approval"
MODULE_NAME = "审批引擎"
MODULE_CATEGORY = "behavior"
MODULE_DEPENDENCIES = ["notifications", "evaluation", "discipline"]
ENABLED_BY_DEFAULT = True


def register(router_prefix="/api/v1/approval"):
    """注册审批模块路由 — 返回 (router, prefix) 供 module_loader 使用"""
    from modules.approval.routers import router

    return router, router_prefix
