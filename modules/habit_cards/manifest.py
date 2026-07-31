"""
Habit Cards 模块清单
模块加载器通过此文件注册路由
"""

MODULE_CODE = "habit_cards"
MODULE_NAME = "虚拟萌卡激励系统"
MODULE_CATEGORY = "engagement"
MODULE_DEPENDENCIES = []
ENABLED_BY_DEFAULT = False  # 小学专属插件，需手动启用

# 仅小学/integrated 学段可用
MODULE_PHASES = ["primary", "integrated"]


def register(router_prefix="/api/v1/habit-cards"):
    from modules.habit_cards.routers import router
    return router, router_prefix
