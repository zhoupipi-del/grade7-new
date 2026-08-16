"""
modules/research_ai/manifest.py
================================
WINGS 模块注册声明（ModuleLoader 自动发现入口）。

模块代码：research_ai
模块名称：教研 AI 工具集
路由前缀：/api/v1/research_ai
依赖模块：research_lesson_prep（共享教研业务域，非强依赖）

功能：
  - 批量教案 AI 生成
  - AI 作文批改（语文/英语）
  - 分层作业设计
  - AI 试卷命制（V2.2）
  - AI 学情分析报告（V2.2）
  - AI 学生评语生成（V2.2）
"""
from __future__ import annotations

MODULE_CODE = "research_ai"
MODULE_NAME = "教研 AI 工具集"
MODULE_CATEGORY = "research"
MODULE_DEPENDENCIES: list[str] = ["research_lesson_prep"]
ENABLED_BY_DEFAULT = False
MODULE_PHASES = ["junior", "senior", "primary", "integrated"]


def register(router_prefix: str = "/api/v1/research_ai"):
    """
    模块注册入口（由 ModuleLoader 调用）。
    返回：(FastAPI Router, prefix)
    """
    from modules.research_ai.routers import router

    return router, router_prefix
