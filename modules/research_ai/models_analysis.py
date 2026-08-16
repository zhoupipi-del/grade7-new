"""
modules/research_ai/models_analysis.py
=======================================
AI 学情分析报告数据模型。

表：analysis_tasks
  - 用户提供学情数据摘要（分数段分布/知识点正确率等文本或结构化描述）
  - LLM 生成班级/年级学情分析报告，输出 Word
  - school_id（SchoolMixin）多租户隔离
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
)

from core.models import Base, SchoolMixin, get_local_now


class AnalysisTask(Base, SchoolMixin):
    """学情分析报告任务（一次请求生成一份报告）。"""

    __tablename__ = "analysis_tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_by = Column(BigInteger, nullable=False, comment="创建人 user_id")

    # 输入
    scope_name = Column(String(100), nullable=False, comment="分析对象（班级/年级名称）")
    subject = Column(String(50), nullable=False, comment="学科")
    grade = Column(String(50), nullable=False, comment="年级")
    exam_name = Column(String(200), nullable=True, comment="考试名称")
    # 学情数据摘要：用户粘贴/填写的分数段、知识点正确率等（不包含学生姓名学号）
    data_summary = Column(Text, nullable=False, comment="学情数据摘要（LLM 分析依据）")
    analysis_focus = Column(Text, nullable=True, comment="关注点（可选）")

    # 状态 / 结果
    # pending / processing / success / failed
    status = Column(String(20), nullable=False, default="pending", index=True)
    file_path = Column(String(500), nullable=True, comment="docx 相对路径")
    file_name = Column(String(255), nullable=True, comment="下载文件名")
    ai_raw_json = Column(JSON, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    error_msg = Column(Text, nullable=True)
    elapsed_sec = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=get_local_now, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_analysis_school_user", "school_id", "created_by"),
    )
