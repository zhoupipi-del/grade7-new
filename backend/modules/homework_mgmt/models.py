"""
homework_mgmt/models.py — 结构化作业管理

物理表:
  1. hw_assignments   — 作业布置表 (教师发布)
  2. hw_submissions   — 学生提交表
  3. hw_grading       — 教师批改表 (含错题标记)

状态机:
  作业: draft → published → closed
  提交: pending → submitted/late → graded → (missing)
"""

from core.models import Base, SchoolMixin, get_local_now
from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)

# ──────────────────────────────────────────────
# 状态枚举常量
# ──────────────────────────────────────────────

# 作业状态
ASSIGNMENT_DRAFT = "draft"
ASSIGNMENT_PUBLISHED = "published"
ASSIGNMENT_CLOSED = "closed"

# 提交状态
SUBMISSION_PENDING = "pending"
SUBMISSION_SUBMITTED = "submitted"
SUBMISSION_LATE = "late"
SUBMISSION_GRADED = "graded"
SUBMISSION_MISSING = "missing"

# 作业类型
HW_DAILY = "daily"
HW_WEEKLY = "weekly"
HW_UNIT_REVIEW = "unit_review"
HW_EXAM_PREP = "exam_prep"

# 批改等级
GRADE_EXCELLENT = "excellent"
GRADE_GOOD = "good"
GRADE_FAIR = "fair"
GRADE_NEEDS_IMPROVEMENT = "needs_improvement"


class HwAssignment(Base, SchoolMixin):
    """作业布置表 — 教师发布的作业"""

    __tablename__ = "hw_assignments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    teacher_id = Column(BigInteger, nullable=False, comment="布置教师 user_id")
    subject_id = Column(BigInteger, nullable=False, comment="科目 grades_subjects.id")
    class_id = Column(BigInteger, comment="指定班级 NULL=全年级")
    grade_id = Column(BigInteger, comment="指定年级")

    title = Column(String(200), nullable=False, comment="作业标题")
    description = Column(Text, comment="作业说明/要求")
    homework_type = Column(
        String(20),
        default=HW_DAILY,
        comment="类型: daily/weekly/unit_review/exam_prep",
    )
    assigned_date = Column(DateTime, nullable=False, comment="布置日期")
    due_date = Column(DateTime, nullable=False, comment="截止日期")
    status = Column(
        String(20),
        default=ASSIGNMENT_PUBLISHED,
        comment="状态: draft/published/closed",
    )

    knowledge_point_ids = Column(JSON, comment="关联知识点ID数组")
    attachment_url = Column(String(500), comment="作业附件")
    total_score = Column(Numeric(6, 2), default=100.00, comment="作业总分")

    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        Index("idx_hw_assign_school_class", "school_id", "class_id"),
        Index("idx_hw_assign_school_teacher", "school_id", "teacher_id"),
        Index("idx_hw_assign_status", "school_id", "status", "due_date"),
    )


class HwSubmission(Base, SchoolMixin):
    """学生提交表 — 学生/家长提交作业"""

    __tablename__ = "hw_submissions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    assignment_id = Column(
        BigInteger, ForeignKey("hw_assignments.id", ondelete="CASCADE"), nullable=False
    )
    student_id = Column(BigInteger, nullable=False, comment="学生 students.id")

    content = Column(Text, comment="文字作答")
    attachment_url = Column(String(500), comment="拍照附件")
    submitted_at = Column(DateTime, comment="提交时间")
    status = Column(
        String(20),
        default=SUBMISSION_PENDING,
        comment="状态: pending/submitted/late/graded/missing",
    )
    late_minutes = Column(Integer, default=0, comment="迟交分钟数")

    created_at = Column(DateTime, default=get_local_now)

    __table_args__ = (
        UniqueConstraint(
            "school_id", "assignment_id", "student_id", name="uk_hw_sub_school_assign_student"
        ),
        Index("idx_hw_sub_school_student", "school_id", "student_id"),
        Index("idx_hw_sub_assign", "assignment_id", "status"),
    )


class HwGrading(Base, SchoolMixin):
    """教师批改表 — 含错题标记"""

    __tablename__ = "hw_grading"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    submission_id = Column(
        BigInteger, ForeignKey("hw_submissions.id", ondelete="CASCADE"), nullable=False
    )
    teacher_id = Column(BigInteger, nullable=False, comment="批改教师 user_id")

    score = Column(Numeric(6, 2), comment="得分")
    max_score = Column(Numeric(6, 2), default=100.00)
    score_percentage = Column(Numeric(5, 2), comment="得分率")
    grade = Column(
        String(20),
        comment="等级: excellent/good/fair/needs_improvement",
    )

    feedback = Column(Text, comment="文字反馈")
    error_items = Column(JSON, comment="错题标记数组")
    error_count = Column(Integer, default=0, comment="错题数量")

    graded_at = Column(DateTime, default=get_local_now)
    created_at = Column(DateTime, default=get_local_now)

    __table_args__ = (
        UniqueConstraint("school_id", "submission_id", name="uk_hw_grade_sub"),
        Index("idx_hw_grade_teacher", "school_id", "teacher_id", "graded_at"),
    )
