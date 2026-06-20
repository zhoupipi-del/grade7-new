"""
core/models.py — Wings 3.0 多租户核心数据模型

6 张基础表 + 1 张模块开关控制表，构成整个 SaaS 平台的地基。
所有业务模块的模型继承 SchoolMixin 实现租户隔离。
"""

import enum
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, Date, DateTime,
    ForeignKey, JSON, Text, Enum as SAEnum, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


def get_local_now() -> datetime:
    """统一时区函数 — 返回 UTC+8 当前时间 (naive datetime)"""
    from datetime import timezone, timedelta
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)


# ═══════════════════════════════════════════════════════════════
# 角色枚举
# ═══════════════════════════════════════════════════════════════

class UserRole(str, enum.Enum):
    MS_ADMIN = "ms_admin"           # 德育处管理员
    GRADE_LEADER = "grade_leader"   # 年级组长
    CLASS_TEACHER = "class_teacher" # 班主任
    TEACHER = "teacher"             # 普通教师
    PARENT = "parent"               # 家长
    STUDENT = "student"             # 学生


# ═══════════════════════════════════════════════════════════════
# 多租户 Mixin — 所有业务表必须继承
# ═══════════════════════════════════════════════════════════════

class SchoolMixin:
    """租户隔离 Mixin：所有业务模块的表都带上 school_id"""
    school_id = Column(BigInteger, ForeignKey("schools.id"), nullable=False, index=True)


# ═══════════════════════════════════════════════════════════════
# 表 1 — 学校（租户）
# ═══════════════════════════════════════════════════════════════

class School(Base):
    __tablename__ = "schools"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="学校名称")
    is_active = Column(Boolean, default=True, comment="租户是否启用")
    created_at = Column(DateTime, default=get_local_now)

    # 反向关系
    users = relationship("User", back_populates="school")
    students = relationship("Student", back_populates="school")
    grades = relationship("Grade", back_populates="school")
    classes = relationship("Class", back_populates="school")
    modules = relationship("SchoolModule", back_populates="school")


# ═══════════════════════════════════════════════════════════════
# 表 2 — 学校模块开关（核心控制表）
# ═══════════════════════════════════════════════════════════════

class SchoolModule(Base):
    """
    每个学校独立控制哪些模块启用/禁用。
    禁用时不删数据，仅置 enabled=False，做到「软开关 + 数据保留」。
    """
    __tablename__ = "school_modules"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    school_id = Column(BigInteger, ForeignKey("schools.id"), nullable=False)
    module_code = Column(String(50), nullable=False, comment="模块代码，如 'attendance'")
    enabled = Column(Boolean, default=False, comment="该校是否启用此模块")
    config = Column(JSON, nullable=True, comment="模块级定制参数")
    enabled_at = Column(DateTime, nullable=True, comment="首次启用时间")
    disabled_at = Column(DateTime, nullable=True, comment="最近禁用时间")

    school = relationship("School", back_populates="modules")

    __table_args__ = (
        UniqueConstraint("school_id", "module_code", name="uk_school_module"),
    )


# ═══════════════════════════════════════════════════════════════
# 表 3 — 用户
# ═══════════════════════════════════════════════════════════════

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(50), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.TEACHER)
    school_id = Column(BigInteger, ForeignKey("schools.id"), nullable=False, index=True)
    grade_id = Column(BigInteger, ForeignKey("grades.id"), nullable=True)
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=True)
    bound_student_id = Column(BigInteger, ForeignKey("students.id"), nullable=True)
    phone = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=get_local_now)
    last_login = Column(DateTime, nullable=True)

    school = relationship("School", back_populates="users")
    grade = relationship("Grade", foreign_keys=[grade_id])
    class_ = relationship("Class", foreign_keys=[class_id])
    bound_student = relationship("Student", foreign_keys=[bound_student_id])

    __table_args__ = (
        Index("idx_user_school_role", "school_id", "role"),
    )


# ═══════════════════════════════════════════════════════════════
# 表 4 — 年级
# ═══════════════════════════════════════════════════════════════

class Grade(Base):
    __tablename__ = "grades"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    school_id = Column(BigInteger, ForeignKey("schools.id"), nullable=False, index=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    school = relationship("School", back_populates="grades")
    classes = relationship("Class", back_populates="grade")


# ═══════════════════════════════════════════════════════════════
# 表 5 — 班级
# ═══════════════════════════════════════════════════════════════

class Class(Base):
    __tablename__ = "classes"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    school_id = Column(BigInteger, ForeignKey("schools.id"), nullable=False, index=True)
    grade_id = Column(BigInteger, ForeignKey("grades.id"), nullable=False, index=True)
    head_teacher_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    student_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    school = relationship("School", back_populates="classes")
    grade = relationship("Grade", back_populates="classes")
    head_teacher = relationship("User", foreign_keys=[head_teacher_id])
    students = relationship("Student", back_populates="class_")


# ═══════════════════════════════════════════════════════════════
# 表 6 — 学生
# ═══════════════════════════════════════════════════════════════

class Student(Base):
    __tablename__ = "students"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    student_no = Column(String(30), unique=True, nullable=False, index=True)
    school_id = Column(BigInteger, ForeignKey("schools.id"), nullable=False, index=True)
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=False, index=True)
    grade_id = Column(BigInteger, ForeignKey("grades.id"), nullable=False, index=True)
    gender = Column(String(10), nullable=True)
    id_card = Column(String(18), nullable=True)
    nationality = Column(String(50), nullable=True, comment="民族")
    ethnicity = Column(String(50), nullable=True)
    birth_date = Column(Date, nullable=True)
    address = Column(String(200), nullable=True)
    parent1_name = Column(String(50), nullable=True)
    parent1_phone = Column(String(20), nullable=True)
    parent1_relation = Column(String(20), nullable=True)
    parent2_name = Column(String(50), nullable=True)
    parent2_phone = Column(String(20), nullable=True)
    parent2_relation = Column(String(20), nullable=True)
    primary_school = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    enrolled_at = Column(Date, nullable=True)
    tags = Column(JSON, nullable=True, comment="学生标签 JSON 数组")
    created_at = Column(DateTime, default=get_local_now)

    school = relationship("School", back_populates="students")
    class_ = relationship("Class", back_populates="students")
    grade = relationship("Grade")

    __table_args__ = (
        Index("idx_student_school_class", "school_id", "class_id"),
    )


# ═══════════════════════════════════════════════════════════════
# 表 7 — 教师（扩展信息）
# ═══════════════════════════════════════════════════════════════

class Teacher(Base):
    """教师扩展信息表，与 User 一对一关联"""
    __tablename__ = "teachers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), unique=True, nullable=False)
    school_id = Column(BigInteger, ForeignKey("schools.id"), nullable=False, index=True)
    subject = Column(String(50), nullable=True, comment="任教科目")
    title = Column(String(50), nullable=True, comment="职称")
    employee_no = Column(String(30), nullable=True, comment="工号")
    is_homeroom = Column(Boolean, default=False, comment="是否班主任")
    created_at = Column(DateTime, default=get_local_now)

    user = relationship("User")
    school = relationship("School")
