"""
modules/behavior/models.py — 违纪行为数据模型

表:
  - discipline_records: 违纪记录主表
  - discipline_appeals: 违纪申诉表
"""

from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, Date, DateTime,
    ForeignKey, Text, Index,
)
from sqlalchemy.orm import relationship
from core.models import Base, SchoolMixin, get_local_now


class DisciplineRecord(Base, SchoolMixin):
    """违纪记录 — 继承 SchoolMixin 实现多租户隔离"""
    __tablename__ = "discipline_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True)
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=False, index=True)
    grade_id = Column(BigInteger, ForeignKey("grades.id"), nullable=False, index=True)
    type = Column(String(20), nullable=False, comment="违纪级别: warning/minor/major/serious")
    category = Column(String(40), nullable=True, comment="违纪类别: 打架/吸烟/迟到/仪容/课堂/其他")
    description = Column(Text, nullable=False, comment="违纪详情描述")
    action_taken = Column(Text, nullable=True, comment="处理措施")
    points = Column(Integer, default=0, comment="扣分值")
    status = Column(String(20), default="active", comment="active/resolved/appealed")
    verify_status = Column(String(20), default="DRAFT", index=True, comment="DRAFT/VERIFIED")
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=get_local_now)
    resolved_at = Column(DateTime, nullable=True)
    incident_date = Column(Date, nullable=True, comment="事发日期")

    # 关系
    student = relationship("core.models.Student", lazy="selectin")
    creator = relationship("core.models.User", foreign_keys=[created_by], lazy="selectin")

    __table_args__ = (
        Index("idx_dr_class_date", "class_id", "incident_date"),
        Index("idx_dr_student_status", "student_id", "status"),
    )


class DisciplineAppeal(Base, SchoolMixin):
    """违纪申诉"""
    __tablename__ = "discipline_appeals"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    discipline_id = Column(BigInteger, ForeignKey("discipline_records.id"), nullable=False, index=True)
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True)
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=False)
    grade_id = Column(BigInteger, ForeignKey("grades.id"), nullable=False)
    applicant_id = Column(BigInteger, ForeignKey("users.id"), nullable=True, comment="申诉人(家长)")
    reason = Column(Text, nullable=False, comment="申诉理由")
    status = Column(String(20), default="pending", comment="pending/reviewing/approved/rejected")
    review_comment = Column(Text, nullable=True, comment="复核意见")
    reviewed_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    # 关系
    discipline = relationship("DisciplineRecord", backref="appeals")
    student = relationship("core.models.Student")
    applicant = relationship("core.models.User", foreign_keys=[applicant_id])
    reviewer = relationship("core.models.User", foreign_keys=[reviewed_by])
