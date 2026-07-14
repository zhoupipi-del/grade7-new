"""error_funnel 模块清单"""

MODULE_CODE = "error_funnel"
MODULE_NAME = "错题断层漏斗引擎"
MODULE_DESCRIPTION = "错题归集、知识点聚类、断层诊断预警、AI处方对接"
MODULE_VERSION = "1.0.0"
MODULE_DEPENDENCIES = ["grades", "homework_mgmt"]
MODULE_ROLES = ["MS_ADMIN", "GRADE_LEADER", "CLASS_TEACHER", "PARENT"]

MODULE_MODELS = ["error_funnel.models"]


def register(router_prefix="/api/v1/error_funnel"):
    """模块注册入口 — 由 module_loader 调用。返回 (APIRouter, prefix) 元组。"""
    from modules.error_funnel.routers import router

    return router, router_prefix
