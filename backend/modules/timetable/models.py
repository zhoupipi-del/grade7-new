"""
timetable 数据模型 — 适配生产DB列结构

四张表:
  classrooms        — 教室/场所
  courses           — 课程定义
  course_slots      — 课节安排 (时间+地点+教师+课程)
  schedule_conflicts — 排课冲突记录
"""

from sqlalchemy import (
    Column, BigInteger, String, Integer, DateTime, Boolean,
    UniqueConstraint, Index, SmallInteger,
    ForeignKey,
)
from core.models import Base, SchoolMixin, get_local_now


class Classroom(Base, SchoolMixin):
    """教室/场所表"""
    __tablename__ = "classrooms"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="教室名称")
    building = Column(String(50), nullable=True, comment="教学楼")
    floor = Column(Integer, nullable=True, comment="楼层")
    capacity = Column(Integer, nullable=False, default=50, comment="容量")
    room_type = Column(String(30), nullable=False, default="standard", comment="standard/lab/music/art/gym")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        UniqueConstraint("school_id", "name", name="uk_school_name"),
        Index("idx_school_id", "school_id"),
        {"comment": "教室"},
    )


class Course(Base, SchoolMixin):
    """课程定义表"""
    __tablename__ = "courses"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="课程名称")
    short_name = Column(String(20), nullable=True, comment="简称")
    subject_category = Column(String(20), nullable=False, default="elective", comment="mandatory/preferred/elective")
    color = Column(String(20), nullable=True, default="#409EFF", comment="课表显示颜色")
    weekly_slots = Column(Integer, nullable=False, default=1, comment="每周课时数")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        UniqueConstraint("school_id", "name", name="uk_school_course"),
        Index("idx_school_id", "school_id"),
        {"comment": "课程"},
    )


class CourseSlot(Base, SchoolMixin):
    """课节安排表"""
    __tablename__ = "course_slots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=False, index=True, comment="班级")
    course_id = Column(BigInteger, ForeignKey("courses.id"), nullable=False, index=True, comment="课程")
    teacher_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True, comment="教师 user_id")
    classroom_id = Column(BigInteger, ForeignKey("classrooms.id"), nullable=True, index=True, comment="教室")
    day_of_week = Column(SmallInteger, nullable=False, comment="星期 1-7")
    slot_number = Column(SmallInteger, nullable=False, comment="第几节 1-10")
    semester = Column(String(20), nullable=False, comment="学期")
    week_pattern = Column(String(50), nullable=False, default="all", comment="all/odd/even/custom")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        UniqueConstraint("class_id", "day_of_week", "slot_number", "semester", name="uk_class_day_slot_semester"),
        Index("idx_teacher_day", "teacher_id", "day_of_week"),
        Index("idx_classroom_day", "classroom_id", "day_of_week"),
        Index("idx_school_id", "school_id"),
        Index("idx_course_id", "course_id"),
        {"comment": "课节安排"},
    )


class ScheduleConflict(Base, SchoolMixin):
    """排课冲突记录表"""
    __tablename__ = "schedule_conflicts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    slot_id_1 = Column(BigInteger, nullable=False, comment="冲突课节1")
    slot_id_2 = Column(BigInteger, nullable=False, comment="冲突课节2")
    conflict_type = Column(String(30), nullable=False, comment="teacher/classroom/class")
    description = Column(String(500), nullable=True, comment="冲突描述")
    severity = Column(String(20), nullable=False, default="warning", comment="info/warning/error")
    is_resolved = Column(Boolean, default=False, comment="是否已解决")
    resolved_by = Column(BigInteger, nullable=True, comment="解决人 user_id")
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=get_local_now)

    __table_args__ = (
        Index("idx_school_id", "school_id"),
        Index("idx_slot_1", "slot_id_1"),
        Index("idx_slot_2", "slot_id_2"),
        Index("idx_conflict_type", "conflict_type"),
        {"comment": "排课冲突"},
    )
