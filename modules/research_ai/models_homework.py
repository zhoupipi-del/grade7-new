"""
modules/research_ai/models_homework.py
======================================
分层作业设计数据模型。

表：homework_tasks
  - 三层（基础/提高/拓展）题量配置，默认 8-5-3
  - 难易比例（易/中/难），默认 4-4-2
  - Celery 异步生成，输出 Word
  - 所有表带 school_id（SchoolMixin）做多租户隔离
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
)

from core.models import Base, SchoolMixin, get_local_now


class HomeworkTask(Base, SchoolMixin):
    """分层作业生成任务（一次请求生成一份三层作业）。"""

    __tablename__ = "homework_tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_by = Column(BigInteger, nullable=False, comment="创建人 user_id")

    # 输入
    subject = Column(String(50), nullable=False, comment="学科")
    grade = Column(String(50), nullable=False, comment="年级")
    textbook = Column(String(100), nullable=True, comment="教材版本")
    unit = Column(String(200), nullable=True, comment="单元/章节")
    topic = Column(String(200), nullable=False, comment="本节课主题")
    knowledge_points = Column(Text, nullable=True, comment="知识点（逗号分隔）")
    class_profile = Column(Text, nullable=True, comment="班级学情描述")
    # 每层题量：基础/提高/拓展，如 "8-5-3"
    question_counts = Column(String(20), nullable=False, default="8-5-3")
    # 难易比例：易/中/难，如 "4-4-2"
    difficulty_distribution = Column(String(20), nullable=False, default="4-4-2")
    estimated_minutes = Column(Integer, nullable=False, default=40)
    include_answers = Column(Boolean, nullable=False, default=True)
    extra_requirements = Column(Text, nullable=True)

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
        Index("idx_hw_school_user", "school_id", "created_by"),
    )
