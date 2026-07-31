"""
modules/red_flag/manifest.py — 流动红旗引擎模块声明

班级维度三维加权评价引擎：
  - 数据源: RoutineScore（日常评分 × 三维度聚合）
  - 跨模块: attendance_records（考勤扣分）+ discipline_records（违纪扣分）
  - 输出: 流动红旗排行榜 → 归档快照

核心依赖: attendance（考勤数据）+ behavior（违纪数据）
"""

MODULE_CODE = "red_flag"
MODULE_NAME = "流动红旗引擎"
MODULE_CATEGORY = "evaluation"
MODULE_DEPENDENCIES = ["attendance", "behavior"]


def register(router_prefix="/api/v1/red-flag"):
    from modules.red_flag.routers import router
    return router, router_prefix
