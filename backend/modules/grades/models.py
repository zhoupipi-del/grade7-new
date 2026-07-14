"""
modules/grades/models.py — 成绩管理模块数据模型

3 张核心表:
- GradeSubject: 科目表（语数英理化等，含满分值）
- GradeExam:    考试表（月考/期中/期末，关联年级+学期）
- GradeRecord:  成绩记录表（学生×考试×科目 → 分数+排名）

1 张审计表:
- GradeAuditLog: 成绩变更审计日志（谁改了什么分）
"""

from core.models import Base, SchoolMixin, get_local_now
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)


class GradeSubject(Base, SchoolMixin):
    """科目表 — 定义学校开设的考试科目

    subject_category 三分类(新高考 3+1+2):
      - mandatory:  必考科目(语数英)，原始分直接计入总分
      - preferred:  首选科目(物理/历史)，原始分直接计入总分
      - elective:   再选科目(化/生/政/地)，等级赋分计入总分

    初中/小学所有科目默认 subject_category='mandatory'(兼容)
    """

    __tablename__ = "grades_subjects"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, comment="科目名称（语文/数学/英语...）")
    code = Column(String(30), nullable=False, comment="科目代码（chinese/math/english...）")
    full_score = Column(Numeric(6, 2), default=100.00, comment="满分值（如 100/120/150）")
    subject_category = Column(
        String(20),
        nullable=False,
        default="mandatory",
        comment="科目分类: mandatory(必考:语数英)/preferred(首选:物史)/elective(再选:化生政地)",
    )
    is_scaling_target = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否需要等级赋分(仅再选科目为TRUE)",
    )
    scaling_score_range = Column(
        String(20),
        nullable=True,
        comment="赋分分值区间(如 '30-100' 表示再选科目赋分区间)",
    )
    sort_order = Column(Integer, default=0, comment="排序权重")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=get_local_now, comment="创建时间")

    __table_args__ = (
        UniqueConstraint("school_id", "code", name="uk_grades_subject_code"),
        Index("idx_gsubject_school", "school_id"),
    )


class GradeExam(Base, SchoolMixin):
    """考试表 — 每次考试的元信息"""

    __tablename__ = "grades_exams"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="考试名称（如 2025秋季期中考试）")
    exam_type = Column(String(20), default="midterm", comment="类型: monthly/midterm/final/quiz")
    grade_id = Column(BigInteger, nullable=False, index=True, comment="年级 ID")
    semester = Column(String(20), default="2025-1", comment="学期标识（如 2025-1 / 2025-2）")
    exam_date = Column(DateTime, nullable=True, comment="考试日期")
    status = Column(String(20), default="draft", comment="状态: draft/published/archived")
    created_by = Column(BigInteger, nullable=True, comment="创建者 user_id")
    created_at = Column(DateTime, default=get_local_now, comment="创建时间")
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now, comment="更新时间")

    __table_args__ = (
        Index("idx_gexam_school_grade", "school_id", "grade_id"),
        Index("idx_gexam_semester", "semester"),
        Index("idx_gexam_status", "status"),
    )


class GradeRecord(Base, SchoolMixin):
    """成绩记录表 — 学生×考试×科目 → 分数 + 排名

    排名字段在批量录入后由服务层统一计算并回填。
    class_rank / grade_rank 为 NULL 表示尚未计算。
    """

    __tablename__ = "grades_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exam_id = Column(BigInteger, nullable=False, index=True, comment="考试 ID")
    student_id = Column(BigInteger, nullable=False, index=True, comment="学生 ID")
    subject_id = Column(BigInteger, nullable=False, index=True, comment="科目 ID")
    score = Column(Numeric(6, 2), nullable=True, comment="得分（NULL 表示缺考）")
    class_rank = Column(Integer, nullable=True, comment="班级排名")
    grade_rank = Column(Integer, nullable=True, comment="年级排名")
    is_absent = Column(Boolean, default=False, comment="是否缺考")
    remark = Column(String(200), nullable=True, comment="备注")
    created_at = Column(DateTime, default=get_local_now, comment="创建时间")
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now, comment="更新时间")

    __table_args__ = (
        UniqueConstraint(
            "school_id", "exam_id", "student_id", "subject_id", name="uk_grades_record"
        ),
        Index("idx_grecord_exam_student", "exam_id", "student_id"),
        Index("idx_grecord_student", "student_id"),
    )


class GradeAuditLog(Base, SchoolMixin):
    """成绩变更审计日志 — 记录每次成绩修改"""

    __tablename__ = "grades_audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exam_id = Column(BigInteger, nullable=False, index=True, comment="考试 ID")
    student_id = Column(BigInteger, nullable=False, comment="学生 ID")
    subject_id = Column(BigInteger, nullable=False, comment="科目 ID")
    old_score = Column(Numeric(6, 2), nullable=True, comment="修改前分数")
    new_score = Column(Numeric(6, 2), nullable=True, comment="修改后分数")
    action = Column(String(20), default="upsert", comment="操作: upsert/delete")
    operator_id = Column(BigInteger, nullable=True, comment="操作者 user_id")
    operator_name = Column(String(50), nullable=True, comment="操作者姓名")
    created_at = Column(DateTime, default=get_local_now, comment="操作时间")

    __table_args__ = (
        Index("idx_gaudit_exam", "exam_id"),
        Index("idx_gaudit_created", "created_at"),
    )
