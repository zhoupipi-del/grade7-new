"""
teacher_mgmt 数据模型

四张表:
  teacher_extensions      — 教师扩展信息(职称/科目/工号/入职日期/周课时上限)
  teacher_subjects        — 教师任教学科映射(多对多)
  teacher_workloads       — 教师工作量日志
  teacher_role_assignments — 教师多重角色解耦overlay(排课/审批/大盘权限切面)
"""

from sqlalchemy import (
    Column, BigInteger, String, Integer, DateTime, Date,
    Float, Boolean, JSON, UniqueConstraint, Index,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from core.models import Base, SchoolMixin, get_local_now


class TeacherExtension(Base, SchoolMixin):
    """
    教师扩展信息表

    与 core Teacher 表 1:1 关联 (user_id),
    存储职称/入职日期/办公地点/资质证书/周课时上限等信息。

    DB列名映射:
      hire_date (DB) → hired_at (ORM属性)
    """
    __tablename__ = "teacher_extensions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger, ForeignKey("users.id"), unique=True, nullable=False, index=True,
        comment="关联 users 表",
    )
    teacher_id = Column(
        BigInteger, ForeignKey("teachers.id"), nullable=True, index=True,
        comment="关联 teachers 表",
    )
    title = Column(String(50), nullable=True, comment="职称: 特级/高级/一级/二级/三级/未定级")
    hired_at = Column("hire_date", Date, nullable=True, comment="入职日期")  # DB列名hire_date→ORM属性hired_at
    office_location = Column(String(100), nullable=True, comment="办公地点")
    qualifications = Column(JSON, nullable=True, comment="资质证书列表 ['教师资格证','心理咨询师',...]")
    education = Column(String(30), nullable=True, comment="最高学历: 博士/硕士/本科/大专")
    major = Column(String(50), nullable=True, comment="所学专业")
    graduate_school = Column(String(100), nullable=True, comment="毕业院校")
    is_head_teacher = Column(Boolean, default=False, comment="是否班主任")
    homeroom_grade = Column(String(20), nullable=True, comment="带班组年级")
    is_active = Column(Boolean, default=True, comment="是否在职")
    # ─── DB 已有但 ORM 之前缺的列 ───
    employee_no = Column(String(30), nullable=True, comment="工号")
    contact_phone = Column(String(20), nullable=True, comment="联系电话")
    max_weekly_hours = Column(Integer, nullable=True, comment="周课时上限(排课引擎供给侧标尺)")
    notes = Column(String(255), nullable=True, comment="备注")
    # ─── 时间戳 ───
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        UniqueConstraint("school_id", "user_id", name="uk_teacher_ext_user"),
        {"comment": "教师扩展信息表"},
    )


class TeacherSubject(Base, SchoolMixin):
    """
    教师任教学科映射表

    一个教师可任教多个学科 (多对多),
    例如: 数学教师可教数学+信息技术。
    """
    __tablename__ = "teacher_subjects"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    teacher_user_id = Column(
        BigInteger, nullable=False, index=True, comment="教师 user_id",
    )
    subject_code = Column(
        String(30), nullable=False, comment="学科代码: chinese/math/english/...",
    )
    subject_name = Column(
        String(50), nullable=False, comment="学科名称: 语文/数学/英语/...",
    )
    grade_id = Column(
        BigInteger, ForeignKey("grades.id"), nullable=True, comment="执教年级ID",
    )
    is_primary = Column(Boolean, default=True, comment="是否主教科任")
    grade_level = Column(
        String(20), nullable=True, comment="执教年级: 初一/初二/初三/高一/高二/高三",
    )
    created_at = Column(DateTime, default=get_local_now)

    __table_args__ = (
        UniqueConstraint(
            "school_id", "teacher_user_id", "subject_code",
            name="uk_teacher_subject",
        ),
        Index("idx_ts_subject", "subject_code"),
        Index("idx_ts_teacher", "teacher_user_id"),
        {"comment": "教师任教学科映射表"},
    )


class TeacherWorkload(Base, SchoolMixin):
    """
    教师工作量日志表

    记录教师每学期/每学年的课时量、带班数、兼任情况。
    按 semester 分区聚合。
    """
    __tablename__ = "teacher_workloads"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    teacher_user_id = Column(
        BigInteger, nullable=False, index=True, comment="教师 user_id",
    )
    semester = Column(
        String(20), nullable=False, comment="学期: 2025-2026-1 / 2025-2026-2",
    )
    weekly_periods = Column(
        Integer, nullable=False, default=0, comment="周课时量",
    )
    class_count = Column(
        Integer, nullable=False, default=0, comment="执教班级数",
    )
    subject_count = Column(
        Integer, nullable=False, default=1, comment="任教科目数",
    )
    is_head_teacher = Column(Boolean, default=False, comment="是否担任班主任")
    head_teacher_class_id = Column(
        BigInteger, ForeignKey("classes.id"), nullable=True, index=True,
        comment="班主任所在班级",
    )
    extra_duties = Column(
        JSON, nullable=True, comment='兼任职务: ["年级组长","教研组长","备课组长",...]',
    )
    total_workload_score = Column(
        Float, nullable=True, comment="工作量综合评分 (自动计算)",
    )
    notes = Column(String(255), nullable=True, comment="备注")
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        UniqueConstraint(
            "school_id", "teacher_user_id", "semester",
            name="uk_workload_teacher_semester",
        ),
        Index("idx_tw_semester", "semester"),
        {"comment": "教师工作量日志表"},
    )


# ═════════════════════════════════════════════════════════════════════════════════
# 教师多重角色解耦 overlay — BOSS 核心需求
# ═════════════════════════════════════════════════════════════════════════════════

# 角色类型枚举值:
#   subject_teacher   — 科任教师
#   homeroom_teacher  — 班主任
#   grade_leader      — 年级组长
#   moral_admin       — 德育处主任/德育管理员
#   research_leader   — 教研组长
#   prep_leader       — 备课组长
#   discipline_officer — 纪检员
#   counselor         — 心理辅导员

# 作用域类型枚举值:
#   school          — 全校范围 (scope_id=NULL)
#   grade           — 年级范围 (scope_id=grade_id)
#   class           — 班级范围 (scope_id=class_id)
#   subject_group   — 学科组范围 (scope_id=subject_group_id)


class TeacherRoleAssignment(Base, SchoolMixin):
    """
    教师角色分配表（多重角色解耦 overlay）

    一个教师可以同时拥有多个角色:
      张老师 = subject_teacher(class=5) + grade_leader(grade=1) + moral_admin(school)

    在不同业务场景切换不同权限切面:
      - 排课引擎: subject_teacher 角色决定课时负载
      - 审批流:   grade_leader/moral_admin 角色决定审批权限
      - 大盘视角: 所有角色叠加决定数据可见范围
    """
    __tablename__ = "teacher_role_assignments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    teacher_user_id = Column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True,
        comment="教师 user_id",
    )
    role_type = Column(
        String(30), nullable=False,
        comment="角色类型: subject_teacher/homeroom_teacher/grade_leader/moral_admin/research_leader/...",
    )
    scope_type = Column(
        String(20), nullable=False,
        comment="作用域类型: school/grade/class/subject_group",
    )
    scope_id = Column(
        BigInteger, nullable=True,
        comment="作用域ID (grade_id/class_id等), school级为NULL",
    )
    is_active = Column(Boolean, default=True, comment="是否启用")
    assigned_at = Column(DateTime, default=get_local_now, comment="分配时间")
    expires_at = Column(DateTime, nullable=True, comment="过期时间(可选)")
    assigned_by = Column(BigInteger, nullable=True, comment="分配人 user_id")
    notes = Column(String(255), nullable=True, comment="备注")
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        UniqueConstraint(
            "school_id", "teacher_user_id", "role_type", "scope_type", "scope_id",
            name="uk_role_assignment",
        ),
        Index("idx_tra_teacher", "teacher_user_id"),
        Index("idx_tra_role_type", "role_type"),
        Index("idx_tra_scope", "scope_type", "scope_id"),
        {"comment": "教师角色分配表（多重角色解耦overlay）"},
    )
