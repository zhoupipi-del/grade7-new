"""
Psych Screening 模块清单
模块加载器通过此文件注册路由
"""

MODULE_CODE = "psych_screening"
MODULE_NAME = "心理筛查与干预"
MODULE_CATEGORY = "wellness"
MODULE_DEPENDENCIES = []
ENABLED_BY_DEFAULT = True

# 初中/高中/融合教育学段可用 (小学也可用但量表年龄适配需关注)
MODULE_PHASES = ["junior", "senior", "integrated", "primary"]


def register(router_prefix="/api/v1/psych-screening"):
    from modules.psych_screening.routers import router
    return router, router_prefix
