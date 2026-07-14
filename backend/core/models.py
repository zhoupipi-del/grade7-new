"""
core/models.py — Wings 3.0 多租户核心数据模型

8 张基础表 + 1 张模块开关控制表 + 1 张级联配置表，构成整个 SaaS 平台的地基。
所有业务模块的模型继承 SchoolMixin 实现租户隔离。
三级组织架构: Organization(集团) → Branch(校区) → School(学校)
"""

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def get_local_now() -> datetime:
    """统一时区函数 — 返回 UTC+8 当前时间 (naive datetime)"""
    from datetime import timedelta, timezone

    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)


# ═══════════════════════════════════════════════════════════════
# 角色枚举 — 三级 RBAC
# ═══════════════════════════════════════════════════════════════


class UserRole(str, enum.Enum):
    MS_ADMIN = "ms_admin"  # 德育处管理员（单校最高权限，等同 SCHOOL_ADMIN）
    GROUP_ADMIN = "group_admin"  # 集团管理员（跨校聚合权限）
    BRANCH_ADMIN = "branch_admin"  # 片区管理员（跨校区权限）
    GRADE_LEADER = "grade_leader"  # 年级组长
    CLASS_TEACHER = "class_teacher"  # 班主任
    TEACHER = "teacher"  # 普通教师
    PARENT = "parent"  # 家长
    STUDENT = "student"  # 学生


# ═══════════════════════════════════════════════════════════════
# Scope Type 枚举 — 级联配置作用域
# ═══════════════════════════════════════════════════════════════


class ScopeType(str, enum.Enum):
    ORG = "org"  # 集团级配置
    BRANCH = "branch"  # 片区级配置
    SCHOOL = "school"  # 学校级配置


# ═══════════════════════════════════════════════════════════════
# 多租户 Mixin — 所有业务表必须继承
# ═══════════════════════════════════════════════════════════════


class SchoolMixin:
    """租户隔离 Mixin：所有业务模块的表都带上 school_id"""

    school_id = Column(BigInteger, ForeignKey("schools.id"), nullable=False, index=True)


# ═══════════════════════════════════════════════════════════════
# 表 1 — 集团/教育集团（Organization）
# ═══════════════════════════════════════════════════════════════


class Organization(Base):
    """
    三级组织架构顶层 — 集团/教育集团。
    一个集团可以包含多个片区(Branch)，每个片区包含多个学校(School)。
    向下兼容：单校场景下 Organization 可只包含 1 个 Branch + 1 个 School。
    """

    __tablename__ = "organizations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="集团名称")
    code = Column(String(50), unique=True, nullable=False, comment="集团代码，如 'lijiang-edu'")
    is_active = Column(Boolean, default=True, comment="集团是否启用")
    created_at = Column(DateTime, default=get_local_now)

    # 反向关系
    branches = relationship("Branch", back_populates="org", order_by="Branch.id")
    schools = relationship("School", back_populates="org", order_by="School.id")


# ═══════════════════════════════════════════════════════════════
# 表 2 — 片区/校区（Branch）
# ═══════════════════════════════════════════════════════════════


class Branch(Base):
    """
    三级组织架构中间层 — 片区/校区。
    如"长沙县片区"、"星沙片区"等，包含多所学校。
    向下兼容：单校场景下 Branch 可只包含 1 个 School。
    """

    __tablename__ = "branches"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    org_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False, comment="片区名称")
    code = Column(String(50), nullable=False, comment="片区代码，如 'changsha-east'")
    is_active = Column(Boolean, default=True, comment="片区是否启用")
    created_at = Column(DateTime, default=get_local_now)

    # 反向关系
    org = relationship("Organization", back_populates="branches")
    schools = relationship("School", back_populates="branch", order_by="School.id")

    __table_args__ = (UniqueConstraint("org_id", "code", name="uk_branch_org_code"),)


# ═══════════════════════════════════════════════════════════════
# 表 3 — 学校（租户）— 升级为三级架构底层
# ═══════════════════════════════════════════════════════════════


class School(Base):
    """
    三级组织架构底层 — 学校。
    新增 branch_id 和 org_id 外键，实现 Organization → Branch → School 三级关系。
    branch_id 和 org_id 均为 nullable=True，允许渐进式迁移：
    旧数据先不填，新数据先填，最后统一补齐。
    """

    __tablename__ = "schools"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="学校名称")
    school_phase = Column(
        String(20),
        nullable=False,
        default="junior",
        comment="学段类型: primary小学, junior初中, senior高中, integrated综合中学",
    )
    plugin_config = Column(JSON, nullable=True, comment="租户功能开关与灰度配置")
    branch_id = Column(
        BigInteger,
        ForeignKey("branches.id"),
        nullable=True,
        index=True,
        comment="所属片区（nullable 允许迁移过渡）",
    )
    org_id = Column(
        BigInteger,
        ForeignKey("organizations.id"),
        nullable=True,
        index=True,
        comment="所属集团（nullable 允许迁移过渡）",
    )
    is_active = Column(Boolean, default=True, comment="租户是否启用")
    created_at = Column(DateTime, default=get_local_now)

    # 反向关系
    branch = relationship("Branch", back_populates="schools")
    org = relationship("Organization", back_populates="schools")
    users = relationship("User", back_populates="school")
    students = relationship("Student", back_populates="school")
    grades = relationship("Grade", back_populates="school")
    classes = relationship("Class", back_populates="school")
    modules = relationship("SchoolModule", back_populates="school")


# ═══════════════════════════════════════════════════════════════
# 表 4 — 学校模块开关（核心控制表）
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

    __table_args__ = (UniqueConstraint("school_id", "module_code", name="uk_school_module"),)


# ═══════════════════════════════════════════════════════════════
# 表 5 — 级联配置（CascadingConfig）
# ═══════════════════════════════════════════════════════════════


class CascadingConfig(Base):
    """
    级联配置表 — 支持 Organization → Branch → School 三级配置继承。

    查找逻辑（get_effective_config）:
      1. 查 school 级 → 有则返回
      2. 查 branch 级 → 有则返回
      3. 查 org 级   → 有则返回
      4. 返回 DEFAULT_CONFIG 兜底

    级联继承意味着：上级配置作为下级的默认值，下级可以覆盖。
    例如：集团统一配置"考勤模块启用"，但某校可单独配置"考勤模块禁用"。
    """

    __tablename__ = "cascading_configs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    scope_type = Column(SAEnum(ScopeType), nullable=False, comment="作用域类型: org/branch/school")
    scope_id = Column(BigInteger, nullable=False, comment="作用域 ID（org_id/branch_id/school_id）")
    module_key = Column(String(50), nullable=False, comment="模块代码或配置分组键")
    config_data = Column(JSON, nullable=False, comment="配置内容 JSON")
    is_enabled = Column(Boolean, default=True, comment="此配置是否生效")
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        UniqueConstraint("module_key", "scope_type", "scope_id", name="uk_cascading_config_scope"),
        Index("idx_cascading_scope", "scope_type", "scope_id"),
    )


# ═══════════════════════════════════════════════════════════════
# 表 6 — 用户（扩展 org_id/branch_id）
# ═══════════════════════════════════════════════════════════════


class User(Base):
    """
    用户表 — 新增 org_id/branch_id 支持 GROUP_ADMIN/BRANCH_ADMIN 权限。

    AccessScope 逻辑:
      MS_ADMIN/GROUP_ADMIN → access_scope = 该集团所有 school_ids
      BRANCH_ADMIN          → access_scope = 该片区所有 school_ids
      其他角色               → access_scope = [user.school_id]
    """

    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(50), nullable=False)
    # NOTE: 使用 String 而非 SAEnum — SQLAlchemy 2.0 + aiomysql 的 native enum 处理器
    #       在读取已有 MySQL ENUM 列数据时会抛 LookupError（即使值完全匹配）。
    #       应用层校验由 Pydantic schemas.UserRoleEnum 负责。
    role = Column(String(50), nullable=False, default="teacher")
    school_id = Column(BigInteger, ForeignKey("schools.id"), nullable=False, index=True)
    org_id = Column(
        BigInteger,
        ForeignKey("organizations.id"),
        nullable=True,
        index=True,
        comment="集团管理员/片区管理员所属集团",
    )
    branch_id = Column(
        BigInteger,
        ForeignKey("branches.id"),
        nullable=True,
        index=True,
        comment="片区管理员所属片区",
    )
    grade_id = Column(BigInteger, ForeignKey("grades.id"), nullable=True)
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=True)
    bound_student_id = Column(BigInteger, ForeignKey("students.id"), nullable=True)
    phone = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True)
    password_change_required = Column(
        Boolean, default=False, comment="首次登录/默认密码用户强制修改密码"
    )
    created_at = Column(DateTime, default=get_local_now)
    last_login = Column(DateTime, nullable=True)

    school = relationship("School", back_populates="users")
    org = relationship("Organization")
    branch = relationship("Branch")
    grade = relationship("Grade", foreign_keys=[grade_id])
    class_ = relationship("Class", foreign_keys=[class_id])
    bound_student = relationship("Student", foreign_keys=[bound_student_id])

    __table_args__ = (Index("idx_user_school_role", "school_id", "role"),)


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
    """
    班级表 — 支持高中新高考走班制双轨模式

    class_type 区分行政班与教学班:
      - administrative: 行政班(班主任管理、考勤、德育、日常)
      - teaching: 教学班/选科班(走班上课, 按选科组合分组)

    初中/小学: 所有班级 class_type='administrative' (DEFAULT 值兼容)
    高中: 学生同时属于1个行政班 + N个教学班(通过中间表关联)
    """

    __tablename__ = "classes"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    school_id = Column(BigInteger, ForeignKey("schools.id"), nullable=False, index=True)
    grade_id = Column(BigInteger, ForeignKey("grades.id"), nullable=False, index=True)
    head_teacher_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    student_count = Column(Integer, default=0)
    class_type = Column(
        String(20),
        nullable=False,
        default="administrative",
        comment="班级类型: administrative(行政班)/teaching(教学班/选科班)",
    )
    subject_group = Column(
        String(50),
        nullable=True,
        comment="教学班选科组合: physics_group(物化生)/history_group(史政地)/custom",
    )
    grade_level = Column(
        String(10),
        nullable=True,
        comment="年级层级: senior_1(高一)/senior_2(高二)/senior_3(高三)",
    )
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

    __table_args__ = (Index("idx_student_school_class", "school_id", "class_id"),)


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
