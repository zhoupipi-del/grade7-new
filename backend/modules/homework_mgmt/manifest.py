"""homework_mgmt 模块清单"""

MODULE_CODE = "homework_mgmt"
MODULE_NAME = "结构化作业管理"
MODULE_DESCRIPTION = "教师发布作业、学生提交、教师批改+错题标记、统计看板"
MODULE_VERSION = "1.0.0"
MODULE_DEPENDENCIES = ["grades", "error_funnel"]
MODULE_ROLES = ["MS_ADMIN", "GRADE_LEADER", "CLASS_TEACHER", "PARENT"]

MODULE_MODELS = ["homework_mgmt.models"]


def register(router_prefix="/api/v1/homework_mgmt"):
    """模块注册入口 — 由 module_loader 调用。返回 (APIRouter, prefix) 元组。"""
    from modules.homework_mgmt.routers import router

    return router, router_prefix
