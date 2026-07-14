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
