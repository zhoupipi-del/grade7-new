"""
modules/ai_teacher_assistant/manifest.py — 模块声明
"""

MODULE_CODE = "ai_teacher_assistant"
MODULE_NAME = "AI 教师助手"
MODULE_CATEGORY = "academic"
MODULE_DEPENDENCIES: list[str] = []
MODULE_SORT_ORDER = 900


def register(router_prefix: str = "/api/v1/ai-teacher-assistant"):
    """ModuleLoader 入口：返回 (FastAPI Router, prefix)。"""
    # ★ 绝对 import：loader 用 spec_from_file_location 加载本文件，
    #    相对 import 在 synthetic package 上下文无效
    from modules.ai_teacher_assistant.routers import router as r

    return r, router_prefix
