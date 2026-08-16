"""
modules/research_ai/models_lesson_plan.py
=========================================
批量教案生成数据模型。

V2.1 修复：
  - [P0] items relationship 改为 lazy="selectin"，避免 Async SQLAlchemy lazy-load 500
  - [P1] 移除 concurrency 列（假配置，实际由 Celery worker 并发控制）

表：
  lesson_plan_tasks — 批量任务（一个任务包含多篇教案）
  lesson_plan_items — 单篇教案
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from core.models import Base, SchoolMixin, get_local_now


class LessonPlanTask(Base, SchoolMixin):
    """教案批量生成任务（一个任务可包含多个课题）。"""

    __tablename__ = "lesson_plan_tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_by = Column(BigInteger, nullable=False, comment="创建人 user_id")
    task_name = Column(String(200), nullable=False, comment="任务名称")
    # pending / processing / completed / partial_failed / failed
    status = Column(String(20), nullable=False, default="pending", index=True)
    total_count = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    fail_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=get_local_now, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    # [P0] lazy="selectin"：Async 会话中 Pydantic 序列化 items 时不会触发
    # MissingGreenlet / 隐式异步 IO。查询时自动预加载。
    items = relationship(
        "LessonPlanItem",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_lpt_school_created", "school_id", "created_at"),
    )


class LessonPlanItem(Base, SchoolMixin):
    """单篇教案。"""

    __tablename__ = "lesson_plan_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(
        BigInteger,
        ForeignKey("lesson_plan_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject = Column(String(50), nullable=False, comment="学科")
    textbook = Column(String(100), nullable=True, comment="教材版本")
    grade = Column(String(50), nullable=False, comment="年级")
    unit = Column(String(200), nullable=True, comment="单元/章节")
    topic = Column(String(200), nullable=False, comment="课题")
    periods = Column(Integer, nullable=False, default=1, comment="课时数")
    key_point = Column(String(500), nullable=True, comment="教师指定重点")
    diff_point = Column(String(500), nullable=True, comment="教师指定难点")
    # pending / processing / success / failed
    status = Column(String(20), nullable=False, default="pending", index=True)
    file_path = Column(String(500), nullable=True, comment="docx 相对路径")
    file_name = Column(String(255), nullable=True, comment="下载文件名")
    ai_raw_json = Column(JSON, nullable=True, comment="AI 返回原始 JSON")
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    error_msg = Column(Text, nullable=True)
    elapsed_sec = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=get_local_now, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    task = relationship(
        "LessonPlanTask",
        back_populates="items",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_lpi_school_task", "school_id", "task_id"),
    )
