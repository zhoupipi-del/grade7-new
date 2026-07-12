"""
modules/reports/manifest.py — 德育报告引擎模块声明 v2.0

双轨架构:
  PDF异步轨: Celery 异步队列 → POST秒回task_id + GET轮询 → ReportLab编译
  RDI白皮书轨: 同步实时聚合 → 全校态势白皮书 + 高危花名册 + 班主任班级报告

核心能力:
  - Celery异步PDF生成: 接入 Redis DB 2/3，双端点分流
  - RDI四维聚合引擎: 从 risk_warnings 聚合全校风险态势
  - 高危花名册: intervention级学生四维breakdown + AI处方摘要
  - 班主任一键报告: 本班RDI分布 + 考勤/违纪/学业概览

依赖链路: core(必装) → risk_models, ai_prescription(RDI数据源) → evaluation, red_flag, behavior, attendance(PDF数据源)
"""

MODULE_CODE = "reports"
MODULE_NAME = "德育报告引擎"
MODULE_CATEGORY = "report"
MODULE_DEPENDENCIES = ["risk_models"]  # RDI聚合需要 risk_warnings 数据源
ENABLED_BY_DEFAULT = False  # 需学校管理员手动开启


def register(router_prefix="/api/v1/reports"):
    """
    模块注册入口 — 由 ModuleLoader 在 lifespan 阶段调用。

    注册7端点:
      PDF异步轨: /export/moral-report, /tasks/{id}, /export/grade-report, /batch-export
      RDI白皮书轨: /rdi-summary, /export/high-risk, /class-report/{cid}
    """
    from modules.reports.routers import router
    return router, router_prefix
