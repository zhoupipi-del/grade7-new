"""
modules/class_mgmt/models.py — 班级管理数据模型

扩展 core.models.Class，增加班级变更记录和班级档案。
"""

from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, Date, DateTime,
    ForeignKey, JSON, Text, Index,
)
from sqlalchemy.orm import relationship

from core.models import Base, SchoolMixin, get_local_now


class ClassChangeLog(Base, SchoolMixin):
    """
    班级变更记录 — 分班/调班/合并/拆分/班主任变更的审计日志。
    """
    __tablename__ = "class_change_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=False, index=True)
    change_type = Column(String(30), nullable=False, comment="assign/transfer/merge/split/teacher_change")
    # 涉及的学生ID列表（JSON）
    affected_students = Column(JSON, nullable=True, comment="受影响的学生ID列表")
    # 变更详情
    from_class_id = Column(BigInteger, nullable=True, comment="调班/合并/拆分的源班级")
    to_class_id = Column(BigInteger, nullable=True, comment="调班/合并/拆分的目标班级")
    # 操作人
    operated_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    operator_name = Column(String(50), nullable=True)
    # 备注
    remark = Column(Text, nullable=True)
    # 血缘追踪
    sync_status = Column(String(20), default="native")
    created_at = Column(DateTime, default=get_local_now)

    cls = relationship("Class", foreign_keys=[class_id])
    operator = relationship("User")

    __table_args__ = (
        Index("idx_class_change_log", "class_id", "created_at"),
    )


class ClassProfileExt(Base, SchoolMixin):
    """
    班级档案扩展 — 存储 Class 表中未覆盖的档案信息。
    与 core.classes 表一对一关联。
    """
    __tablename__ = "class_profile_ext"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    class_id = Column(BigInteger, ForeignKey("classes.id"), unique=True, nullable=False, index=True)
    # 班级特色
    class_slogan = Column(String(200), nullable=True, comment="班级口号")
    class_features = Column(JSON, nullable=True, comment="班级特色标签")
    # 班委信息
    class_committee = Column(JSON, nullable=True, comment="班委信息JSON: {monitor: id, vice_monitor: id, ...}")
    # 班级荣誉
    honors = Column(JSON, nullable=True, comment="班级荣誉列表")
    # 班级档案
    profile = Column(Text, nullable=True, comment="班级详细档案")
    # 创建时间
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    cls = relationship("Class")
