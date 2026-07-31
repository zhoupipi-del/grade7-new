"""
Data Adapter 模块清单
模块加载器通过此文件注册路由
"""

MODULE_CODE = "data_adapter"
MODULE_NAME = "数据适配器"
MODULE_CATEGORY = "infrastructure"
MODULE_DEPENDENCIES = []
ENABLED_BY_DEFAULT = True

# 仅初中/高中/integrated 学段可用（小学无Z-Score/赋分需求）
MODULE_PHASES = ["junior", "senior", "integrated"]


def register(router_prefix="/api/v1/data_adapter"):
    from modules.data_adapter.routers import router
    return router, router_prefix
