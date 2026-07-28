"""
modules/student_registry/models.py — 学籍管理数据模型

扩展 core.models.Student，增加学籍状态变更记录表和旧数据同步标记。
不修改已有 Student 表结构，通过新表实现生命周期管理。
"""

from core.models import Base, SchoolMixin, get_local_now
from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import relationship

# ═══════════════════════════════════════════════════════════════
# 学籍状态枚举
# ═══════════════════════════════════════════════════════════════

# 使用 String 存储而非 SAEnum，与 core.models 保持一致
# 状态流转：active -> suspended -> active / transferred / graduated / inactive

STUDENT_STATUS = {
    "active": "在校",
    "suspended": "休学",
    "transferred": "转出",
    "graduated": "毕业",
    "inactive": "注销",
}

# 合法状态转换
VALID_TRANSITIONS = {
    "active": ["suspended", "transferred", "graduated", "inactive"],
    "suspended": ["active", "inactive"],  # 休学可复学或注销
    "transferred": [],  # 终态
    "graduated": [],  # 终态
    "inactive": [],  # 终态
}


# ═══════════════════════════════════════════════════════════════
# 表 — 学籍状态变更记录
# ═══════════════════════════════════════════════════════════════


class StudentStatusChange(Base, SchoolMixin):
    """
    学籍状态变更记录 — 每次转学/休学/复学/毕业/注销都记录一条。
    形成学生的学籍变更时间轴，支持审计和回溯。
    """

    __tablename__ = "student_status_changes"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True)
    from_status = Column(String(20), nullable=False, comment="变更前状态")
    to_status = Column(String(20), nullable=False, comment="变更后状态")
    change_type = Column(
        String(30), nullable=False, comment="变更类型: transfer/suspend/resume/graduate/inactive"
    )
    reason = Column(String(500), nullable=True, comment="变更原因")
    # 转学专用
    target_school = Column(String(100), nullable=True, comment="转入学校名称")
    target_school_id = Column(BigInteger, nullable=True, comment="转入学校ID（如系统内）")
    # 休学专用
    expected_resume_date = Column(Date, nullable=True, comment="预计复学日期")
    # 操作人
    operated_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    operator_name = Column(String(50), nullable=True, comment="操作人姓名（冗余）")
    # 审批
    approval_id = Column(BigInteger, nullable=True, comment="关联审批记录ID（如有）")
    # 血缘追踪 — BOSS要求的 sync_status
    sync_status = Column(
        String(20),
        default="native",
        comment="数据来源: native(原生) / legacy(旧系统同步) / imported(批量导入)",
    )
    lineage_ref = Column(String(100), nullable=True, comment="血缘引用ID，关联 lineage 模块记录")
    # 备注
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_local_now)

    student = relationship("Student")
    operator = relationship("User")

    __table_args__ = (
        Index("idx_status_change_student", "student_id", "created_at"),
        Index("idx_status_change_school_type", "school_id", "change_type"),
    )


# ═══════════════════════════════════════════════════════════════
# 表 — 学籍扩展信息（不修改 core Student 表，通过一对一扩展）
# ═══════════════════════════════════════════════════════════════


class StudentRegistryExt(Base, SchoolMixin):
    """
    学籍扩展信息 — 存储 Student 表中未覆盖的学籍管理字段。
    与 core.students 表一对一关联，不侵入原有表结构。
    """

    __tablename__ = "student_registry_ext"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(
        BigInteger, ForeignKey("students.id"), unique=True, nullable=False, index=True
    )
    # 学籍状态（独立于 is_active，支持更细粒度的状态管理）
    registry_status = Column(
        String(20),
        default="active",
        nullable=False,
        index=True,
        comment="学籍状态: active/suspended/transferred/graduated/inactive",
    )
    # 学籍号（教育部学籍号，与 student_no 校内学号区分）
    national_student_no = Column(String(50), nullable=True, index=True, comment="全国学籍号")
    # 入学方式
    enrollment_type = Column(
        String(30), nullable=True, comment="入学方式: normal/transfer/art/sports"
    )
    # 毕业信息
    graduation_date = Column(Date, nullable=True)
    graduation_school = Column(String(100), nullable=True, comment="升入学校")
    # 血缘追踪
    sync_status = Column(String(20), default="native", comment="native/legacy/imported")
    legacy_student_id = Column(String(50), nullable=True, comment="旧系统学生ID（迁移用）")
    lineage_ref = Column(String(100), nullable=True, comment="血缘追踪引用")
    # 时间戳
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    student = relationship("Student")

    __table_args__ = (Index("idx_registry_ext_status", "school_id", "registry_status"),)


# ═══════════════════════════════════════════════════════════════
# 表 — 学年学籍快照（冷冻快照 / 晋升映射溯源）
# ═══════════════════════════════════════════════════════════════


class StudentYearHistory(Base, SchoolMixin):
    """
    学年学籍快照 — 每次新学年滚动(rollover)执行前，对全体在校生做一次冷冻快照。
    记录 (school_id, student_id, school_year, grade_id, class_id)，
    用于晋升后溯源「某学生某学年在哪个年级/班级」，以及 P2 数据校验。
    不侵入 core.students 表，只读历史。
    """

    __tablename__ = "student_year_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # school_id 由 SchoolMixin 提供: BigInteger FK->schools.id NOT NULL index
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True)
    school_year = Column(String(20), nullable=False, comment="学年标识，如 2026-2027")
    grade_id = Column(BigInteger, ForeignKey("grades.id"), nullable=False, index=True)
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=get_local_now)

    __table_args__ = (Index("idx_syh_school_year", "school_id", "school_year"),)


# ═══════════════════════════════════════════════════════════════
# 表 — 滚动晋升锁（幂等护栏）
# ═══════════════════════════════════════════════════════════════


class RolloverLock(Base, SchoolMixin):
    """
    滚动晋升锁 — 防重复调用导致 7->8->9 二次晋升的护栏。
    唯一约束 (school_id, school_year) 保证每校每学年至多一条锁记录。
    released_at IS NULL 表示仍处锁定态（已完成/进行中），任何重入请求必须先查此表。
    """

    __tablename__ = "rollover_lock"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # school_id 由 SchoolMixin 提供: BigInteger FK->schools.id NOT NULL index
    school_year = Column(String(20), nullable=False, comment="学年标识，如 2026-2027")
    locked_by = Column(BigInteger, ForeignKey("users.id"), nullable=False, comment="加锁人 user_id")
    locked_at = Column(DateTime, default=get_local_now, comment="加锁时间")
    note = Column(String(255), nullable=True, comment="加锁备注 / 批次号")
    released_at = Column(DateTime, nullable=True, comment="释放时间（NULL=仍锁）")
    created_at = Column(DateTime, default=get_local_now)

    __table_args__ = (
        Index(
            "uk_rollover_lock_school_year",
            "school_id",
            "school_year",
            unique=True,
        ),
    )
