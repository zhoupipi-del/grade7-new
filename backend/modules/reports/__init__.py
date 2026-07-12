# modules/reports — 德育报告引擎 v2.0
#
# 双轨架构:
#   PDF异步轨: Celery → ReportLab 编译 → 静态文件服务
#   RDI白皮书轨: 同步聚合 → 全校态势 + 高危花名册 + 班级报告
#
# 7端点:
#   POST /export/moral-report     — 班级德育PDF异步生成
#   GET  /tasks/{task_id}         — 任务状态轮询
#   POST /export/grade-report     — 全年级批量导出
#   GET  /batch-export            — 批量导出前端工作台
#   GET  /rdi-summary             — 全校RDI态势白皮书 (新增)
#   POST /export/high-risk        — 高危学生花名册导出 (新增)
#   GET  /class-report/{class_id} — 班主任班级报告 (新增)
#
# 6件套: __init__.py, manifest.py, models.py, schemas.py, services.py, routers.py
# + 辅助: pdf_utils.py, tasks.py, celery_app.py
