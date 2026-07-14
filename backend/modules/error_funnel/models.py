"""
error_funnel/models.py — 错题断层漏斗引擎

物理表:
  1. knowledge_points   — 知识点表 (新系统首创)
  2. error_book_items   — 错题本条目表
  3. knowledge_gaps     — 知识点断层记录表 (聚合+AI处方)

漏斗逻辑:
  error_book_items (原始错题) → knowledge_gaps (知识点聚合)
  consecutive_errors >= 3 → gap_level=critical → 触发AI处方
"""

from core.models import Base, SchoolMixin, get_local_now
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

# ──────────────────────────────────────────────
# 错误类型
# ──────────────────────────────────────────────
ERROR_CONCEPTUAL = "conceptual"  # 概念性错误
ERROR_PROCEDURAL = "procedural"  # 过程性错误
ERROR_CARELESS = "careless"  # 粗心错误
ERROR_OMISSION = "omission"  # 遗漏错误
ERROR_UNKNOWN = "unknown"  # 未知错误

# 来源类型
SOURCE_HOMEWORK = "homework"
SOURCE_EXAM = "exam"
SOURCE_MANUAL = "manual"

# 断层等级
GAP_NONE = "none"
GAP_WATCH = "watch"
GAP_WARNING = "warning"
GAP_CRITICAL = "critical"

# 断层状态
GAP_ACTIVE = "active"
GAP_RESOLVED = "resolved"

# AI状态
AI_PENDING = "pending"
AI_COMPLETED = "completed"
AI_FAILED = "failed"


class KnowledgePoint(Base, SchoolMixin):
    """知识点表 — 学科知识体系树"""

    __tablename__ = "knowledge_points"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    subject_id = Column(BigInteger, nullable=False, comment="科目 grades_subjects.id")
    name = Column(String(100), nullable=False, comment="知识点名称")
    code = Column(String(50), comment="知识点代码")
    description = Column(Text)
    parent_id = Column(BigInteger, comment="父知识点 (树形结构)")
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=get_local_now)

    __table_args__ = (
        UniqueConstraint("school_id", "subject_id", "code", name="uk_kp_school_subject_code"),
        Index("idx_kp_school_subject", "school_id", "subject_id", "is_active"),
        Index("idx_kp_parent", "parent_id"),
    )


class ErrorBookItem(Base, SchoolMixin):
    """错题本条目 — 每一道错题的原始记录"""

    __tablename__ = "error_book_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    student_id = Column(BigInteger, nullable=False, comment="学生 students.id")
    subject_id = Column(BigInteger, nullable=False, comment="科目 grades_subjects.id")

    source_type = Column(String(20), nullable=False, comment="来源: homework/exam/manual")
    source_id = Column(BigInteger, comment="来源ID: assignment_id/exam_id")
    source_desc = Column(String(200), comment="来源描述")

    question_content = Column(Text, nullable=False, comment="题目内容")
    question_type = Column(String(20), comment="题型: choice/fill/short_answer/essay/calculation")
    student_answer = Column(Text)
    correct_answer = Column(Text)

    error_type = Column(
        String(20),
        nullable=False,
        comment="错误类型: conceptual/procedural/careless/omission/unknown",
    )
    knowledge_point_ids = Column(JSON, comment="关联知识点ID数组")
    difficulty = Column(String(10), comment="难度: easy/medium/hard")

    ai_analysis = Column(Text, comment="AI分析结果")
    ai_status = Column(String(20), default=AI_PENDING, comment="AI状态: pending/completed/failed")

    is_resolved = Column(Boolean, default=False, comment="学生是否已纠错掌握")
    resolved_at = Column(DateTime)

    created_at = Column(DateTime, default=get_local_now)

    __table_args__ = (
        Index("idx_ebi_school_student", "school_id", "student_id"),
        Index("idx_ebi_school_subject", "school_id", "subject_id"),
        Index("idx_ebi_source", "school_id", "source_type", "source_id"),
        Index("idx_ebi_error_type", "school_id", "error_type"),
        Index("idx_ebi_resolved", "school_id", "is_resolved"),
    )


class KnowledgeGap(Base, SchoolMixin):
    """知识点断层记录 — 聚合表 + AI处方"""

    __tablename__ = "knowledge_gaps"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    student_id = Column(BigInteger, nullable=False)
    subject_id = Column(BigInteger, nullable=False)
    knowledge_point_id = Column(BigInteger, nullable=False)
    knowledge_point_name = Column(String(100), comment="冗余存储方便查询")

    error_count = Column(Integer, default=0, comment="累计错误次数")
    consecutive_errors = Column(Integer, default=0, comment="连续错误次数")
    last_error_date = Column(DateTime)
    last_error_source = Column(String(200))

    gap_level = Column(
        String(20), default=GAP_WATCH, comment="断层等级: none/watch/warning/critical"
    )
    gap_status = Column(String(20), default=GAP_ACTIVE, comment="状态: active/resolved")

    resolved_at = Column(DateTime)

    ai_prescription = Column(Text, comment="AI处方")
    ai_prescription_generated_at = Column(DateTime)

    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        UniqueConstraint(
            "school_id", "student_id", "knowledge_point_id", name="uk_kg_school_student_kp"
        ),
        Index("idx_kg_school_student", "school_id", "student_id"),
        Index("idx_kg_school_subject", "school_id", "subject_id"),
        Index("idx_kg_gap_level", "school_id", "gap_level", "gap_status"),
        Index("idx_kg_status", "school_id", "gap_status"),
    )
