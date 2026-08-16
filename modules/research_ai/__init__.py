"""
modules/research_ai/__init__.py
==============================
WINGS 教研 AI 工具集（独立模块包）。

路径：/opt/wings3/current/modules/research_ai/
功能：
  - 批量教案 AI 生成（Celery 异步 + Word 输出）
  - AI 作文批改（语文/英语，同步调用 + 教师复核）
  - 分层作业设计（Celery 异步 + Word 输出）
  - AI 试卷命制（V2.2，Celery 异步 + Word 输出）
  - AI 学情分析报告（V2.2，Celery 异步 + Word 输出）
  - AI 学生评语生成（V2.2，Celery 异步 + Word 输出，姓名不送 LLM）

模块注册：通过 manifest.py 被 ModuleLoader 自动发现，
路由前缀 /api/v1/research_ai。
"""

MODULE_CODE = "research_ai"
