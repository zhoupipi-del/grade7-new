"""
modules/research_ai/models_essay.py
====================================
AI 作文批改记录数据模型。

表：essay_grade_records
  - 支持语文 / 英语
  - AI 初评 + 教师复核工作流（pending → reviewed）
  - 所有表带 school_id（SchoolMixin）做多租户隔离
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
)

from core.models import Base, SchoolMixin, get_local_now


class EssayGradeRecord(Base, SchoolMixin):
    """作文批改记录（AI 初评 + 教师复核）。"""

    __tablename__ = "essay_grade_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    teacher_id = Column(BigInteger, nullable=False, index=True, comment="批改教师")
    student_id = Column(BigInteger, nullable=True, comment="关联学生（可选）")
    student_name = Column(String(100), nullable=True, comment="学生姓名（显示用）")

    # 输入
    subject = Column(String(20), nullable=False, comment="chinese / english")
    grade = Column(String(20), nullable=False, comment="年级")
    total_score_config = Column(
        SmallInteger, nullable=False, default=60, comment="总分配置"
    )
    essay_prompt = Column(Text, nullable=False, comment="作文题面")
    essay_text = Column(Text, nullable=False, comment="学生作文")
    rubric = Column(Text, nullable=True, comment="自定义评分标准")

    # AI 返回
    ai_total_score = Column(SmallInteger, nullable=True)
    ai_grade_label = Column(String(50), nullable=True)
    ai_dimensions = Column(JSON, nullable=True, comment="维度评分")
    ai_annotations = Column(JSON, nullable=True, comment="逐段批注")
    ai_grammar_errors = Column(JSON, nullable=True, comment="语法错误（英语）")
    ai_comment = Column(Text, nullable=True, comment="总体评语")
    ai_chinese_summary = Column(Text, nullable=True, comment="中文概要（英语）")
    ai_refined_essay = Column(Text, nullable=True, comment="润色范文")
    ai_tips = Column(JSON, nullable=True, comment="提升建议")
    ai_raw_json = Column(JSON, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)

    # 教师复核
    # pending / reviewed
    review_status = Column(String(20), nullable=False, default="pending", index=True)
    final_score = Column(SmallInteger, nullable=True, comment="教师最终分数")
    teacher_comment = Column(Text, nullable=True, comment="教师评语")
    reviewed_by = Column(BigInteger, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=get_local_now, nullable=False, index=True)

    __table_args__ = (
        Index("idx_essay_school_teacher", "school_id", "teacher_id"),
    )
