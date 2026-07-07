"""
AI 德育处方大脑 — 模块注册声明
ModuleLoader 发现入口
"""
from __future__ import annotations

MODULE_CODE = "ai_prescription"
MODULE_DEPENDENCIES: list[str] = []


def register(router_prefix: str = "/api/v1/ai_prescription"):
    """
    模块注册入口（由 ModuleLoader 调用）
    返回：(FastAPI Router, prefix)
    """
    from modules.ai_prescription.routers import router
    return router, router_prefix
