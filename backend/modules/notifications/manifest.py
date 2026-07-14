"""
modules/notifications/manifest.py — 系统通知引擎模块声明

三层触发架构:
  1. discipline 服务层 Hook 注入（状态变更→通知推送）
  2. 数据库 notifications 表持久化
  3. 前端轮询 API（列表/已读/未读计数）

为后续企业微信/钉钉推送预留扩展点。
"""

MODULE_CODE = "notifications"
MODULE_NAME = "系统通知引擎"
MODULE_CATEGORY = "core"
MODULE_DEPENDENCIES = []  # 核心依赖 core 已默认加载


def register(router_prefix="/api/v1/notifications"):
    from modules.notifications.routers import router

    return router, router_prefix
