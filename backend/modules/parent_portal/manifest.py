"""
modules/parent_portal/manifest.py — 家长门户模块声明

只读聚合网关 + 反馈/申诉独立写操作:
  - 仪表盘/概览: 直连 evaluation/attendance/behavior/risk_models/growth Service
  - 反馈闭环: parent_feedbacks 表（双向：家长→班主任→家长）
  - 申诉代理: parent_appeals_proxy 表（Facade 路由到 discipline/behavior）
  - 越权铁闸: parent_id → bound_student_id 绑定校验
"""

MODULE_CODE = "parent_portal"
MODULE_NAME = "家长门户"
MODULE_CATEGORY = "parent"
MODULE_DEPENDENCIES = ["evaluation", "attendance", "behavior", "risk_models", "growth"]


def register(router_prefix="/api/v1/parent_portal"):
    from modules.parent_portal.routers import router

    return router, router_prefix
