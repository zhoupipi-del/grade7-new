"""
modules/research_ai/models_comment.py
=====================================
AI 学生评语生成数据模型。

表：comment_tasks
  - 批量学生评语：输入学生名单（姓名+表现关键词），LLM 逐人生成
  - 隐私边界：学生姓名存库仅供教师本地显示与回填；
    发送给 LLM 的 prompt 一律用"学生1/学生2"匿名编号，
    评语正文用"该同学"占位，回填时再替换真实姓名。
  - 输出 Word（批量评语）
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


class CommentTask(Base, SchoolMixin):
    """学生评语生成任务（一次请求批量生成多位学生评语）。"""

    __tablename__ = "comment_tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_by = Column(BigInteger, nullable=False, comment="创建人 user_id")

    # 输入
    class_name = Column(String(100), nullable=False, comment="班级名称")
    term = Column(String(100), nullable=False, comment="学期，如 2025-2026学年第一学期")
    # 评语类型：品德评语 / 学期评语 / 家校沟通
    comment_type = Column(String(50), nullable=False, default="semester")
    # 学生名单：[{"name": "张三", "keywords": "课堂积极，作业认真"}]
    students = Column(JSON, nullable=False, comment="学生名单（姓名+表现关键词）")
    student_count = Column(Integer, nullable=False, default=0)
    style = Column(Text, nullable=True, comment="风格/字数要求")

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
        Index("idx_comment_school_user", "school_id", "created_by"),
    )
