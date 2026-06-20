"""
modules/attendance/models.py — 考勤数据模型

继承 SchoolMixin 实现多租户隔离。
"""

from datetime import date, datetime
from sqlalchemy import (
    Column, BigInteger, String, Date, DateTime, ForeignKey, Text, Index,
)
from sqlalchemy.orm import relationship

from core.models import Base, SchoolMixin, get_local_now


class AttendanceRecord(Base, SchoolMixin):
    """
    考勤记录表

    每条记录 = 某学生某日的出勤状态。
    status 枚举: present(出勤) / late(迟到) / early(早退) / absent(缺勤) / leave(请假)
    """
    __tablename__ = "attendance_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True)
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=False, index=True)
    grade_id = Column(BigInteger, ForeignKey("grades.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, comment="present/late/early/absent/leave")
    record_date = Column(Date, default=date.today, index=True)
    note = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=get_local_now)

    student = relationship("Student")
    class_ = relationship("Class")
    grade = relationship("Grade")

    __table_args__ = (
        Index("idx_att_student_date", "student_id", "record_date"),
        Index("idx_att_class_date", "class_id", "record_date"),
        Index("idx_att_school_date", "school_id", "record_date"),
    )


class LeaveRequest(Base, SchoolMixin):
    """
    请假申请表

    审批流程: pending → class_approved → grade_approved
    审批通过后自动创建 AttendanceRecord。
    """
    __tablename__ = "leave_requests"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True)
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=False)
    grade_id = Column(BigInteger, ForeignKey("grades.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(
        String(20), default="pending",
        comment="pending/class_approved/grade_approved/rejected"
    )
    submitted_by = Column(BigInteger, ForeignKey("users.id"), nullable=True, comment="申请人（家长）")
    approved_by_class = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    approved_by_grade = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    approved_at_class = Column(DateTime, nullable=True)
    approved_at_grade = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=get_local_now)

    student = relationship("Student")
    class_ = relationship("Class")
    grade = relationship("Grade")
    submitter = relationship("User", foreign_keys=[submitted_by])

    __table_args__ = (
        Index("idx_leave_student", "student_id"),
        Index("idx_leave_status", "status"),
    )
