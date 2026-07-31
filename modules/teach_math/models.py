"""
modules/teach_math/models.py — 数学教学辅助模块数据模型

- MathLesson: 数学课件（幻灯片集合 + JSON 存储）
- TranslationRecord: 审题翻译记录（输入题目 → AI 逐句翻译）
"""

from sqlalchemy import Column, BigInteger, String, Text, DateTime, Integer, Boolean, JSON, Index
from core.models import Base, SchoolMixin, get_local_now


class MathLesson(Base, SchoolMixin):
    """数学课件 — 幻灯片集合的 JSON 存储"""

    __tablename__ = "teach_math_lessons"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False, comment="课件标题")
    subject = Column(String(50), default="math", comment="科目（暂固定 math）")
    grade_level = Column(String(20), default="七年级", comment="年级")
    knowledge_point = Column(String(100), nullable=True, comment="知识点")
    slides = Column(JSON, default=list, comment="幻灯片 JSON 数组")
    status = Column(String(20), default="draft", comment="状态: draft/published/archived")
    created_by = Column(BigInteger, nullable=True, comment="创建者 user_id")
    created_at = Column(DateTime, default=get_local_now, comment="创建时间")
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now, comment="更新时间")

    __table_args__ = (
        Index("idx_lesson_school", "school_id"),
        Index("idx_lesson_grade", "grade_level"),
        Index("idx_lesson_status", "status"),
    )


class TranslationRecord(Base, SchoolMixin):
    """审题翻译记录 — 学生输入题目 → AI 输出逐句翻译"""

    __tablename__ = "teach_math_translations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    question_text = Column(Text, nullable=False, comment="原始题目文本")
    grade_level = Column(String(20), default="七年级", comment="年级")
    knowledge_point = Column(String(100), nullable=True, comment="关联知识点")
    llm_response = Column(JSON, default=dict, comment="LLM 完整响应 JSON")
    translation_score = Column(Integer, nullable=True, comment="翻译质量评分 (1-5)")
    student_id = Column(BigInteger, nullable=True, comment="学生 user_id（可选）")
    teacher_id = Column(BigInteger, nullable=True, comment="教师 user_id")
    created_at = Column(DateTime, default=get_local_now, comment="创建时间")

    __table_args__ = (
        Index("idx_translation_school", "school_id"),
        Index("idx_translation_student", "student_id"),
        Index("idx_translation_created", "created_at"),
    )
