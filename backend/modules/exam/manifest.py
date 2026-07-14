"""
modules/exam/manifest.py — 考试管理模块声明
"""

MODULE_CODE = "exam"
MODULE_NAME = "考试管理"
MODULE_CATEGORY = "academic"
MODULE_DEPENDENCIES = ["grades"]  # 依赖 grades 模块（grades_exams + grades_subjects）


def register(router_prefix="/api/v1/exam"):
    from modules.exam.routers import router

    return router, router_prefix
