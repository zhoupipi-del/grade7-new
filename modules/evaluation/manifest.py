"""
modules/evaluation/manifest.py — 素质评价引擎模块声明

五维素质评价引擎 — 事件驱动 CQRS 架构：
  - 写模型: EvaluationScore（事件源）
  - 读模型: StudentScore（预计算快照）
  - 审计链: ScoreLog（完整溯源）
  - 配置: EvaluationRule（多租户可定制）
  - 指标: EvaluationIndicator（五维二级指标体系）
"""

MODULE_CODE = "evaluation"
MODULE_NAME = "素质评价引擎"
MODULE_CATEGORY = "evaluation"
MODULE_DEPENDENCIES = []  # 核心依赖 core 已默认加载

def register(router_prefix="/api/v1/evaluation"):
    from modules.evaluation.routers import router
    return router, router_prefix
