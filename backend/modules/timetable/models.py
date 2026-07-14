"""
timetable 数据模型 — 适配生产DB列结构

四张表:
  classrooms        — 教室/场所
  courses           — 课程定义
  course_slots      — 课节安排 (时间+地点+教师+课程)
  schedule_conflicts — 排课冲突记录
"""

from core.models import Base, SchoolMixin, get_local_now
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship


class Classroom(Base, SchoolMixin):
    """教室/场所表"""

    __tablename__ = "classrooms"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="教室名称")
    building = Column(String(50), nullable=True, comment="教学楼")
    floor = Column(Integer, nullable=True, comment="楼层")
    capacity = Column(Integer, nullable=False, default=50, comment="容量")
    room_type = Column(
        String(30), nullable=False, default="standard", comment="standard/lab/music/art/gym"
    )
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
    subject_category = Column(
        String(20), nullable=False, default="elective", comment="mandatory/preferred/elective"
    )
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
    class_id = Column(
        BigInteger, ForeignKey("classes.id"), nullable=False, index=True, comment="班级"
    )
    course_id = Column(
        BigInteger, ForeignKey("courses.id"), nullable=False, index=True, comment="课程"
    )
    teacher_id = Column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True, comment="教师 user_id"
    )
    classroom_id = Column(
        BigInteger, ForeignKey("classrooms.id"), nullable=True, index=True, comment="教室"
    )
    day_of_week = Column(SmallInteger, nullable=False, comment="星期 1-7")
    slot_number = Column(SmallInteger, nullable=False, comment="第几节 1-10")
    semester = Column(String(20), nullable=False, comment="学期")
    week_pattern = Column(String(50), nullable=False, default="all", comment="all/odd/even/custom")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        UniqueConstraint(
            "class_id", "day_of_week", "slot_number", "semester", name="uk_class_day_slot_semester"
        ),
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


# ═══════════════════════════════════════════════════════════════
# Wings 3.1 时空连续体 — 物理节次坐标系 + 日历级实例网格
# ═══════════════════════════════════════════════════════════════


class TimetableSlot(Base, SchoolMixin):
    """
    战线①：物理时空节次定义表
    明确定义每一节课、大课间、午休、晚自习的绝对时间分钟区间。
    这是整个时空坐标系的"标尺"——所有时间戳判定都以此为基准。
    """

    __tablename__ = "timetable_slots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    period_index = Column(Integer, nullable=False, comment="第几节 1-8")
    slot_type = Column(
        String(20),
        nullable=False,
        default="LESSON",
        comment="LESSON:正课, BREAK:大课间, LUNCH:午休, MORNING_READING:早读, EVENING:晚自习",
    )
    name = Column(String(50), nullable=False, comment="如: 第一节课、眼保健操")
    start_time = Column(Time, nullable=False, comment="开始时间 08:00:00")
    end_time = Column(Time, nullable=False, comment="结束时间 08:45:00")
    is_active = Column(Boolean, default=True, comment="是否启用")

    __table_args__ = (
        UniqueConstraint("school_id", "period_index", "slot_type", name="uix_school_period_type"),
        Index("idx_slots_school", "school_id"),
        {"comment": "物理时空节次定义"},
    )


class TimetableScheduleInstance(Base, SchoolMixin):
    """
    战线②：日历级课表实例表（时空网格核心）
    打破 week_pattern 星期概念，全面映射到真实日历 date。
    13路时序流碰撞的终极靶盘——所有事件反查都是这张表。

    每日凌晨由 Celery Beat 根据模板自动生成未来 7 天实例，
    或由调课/代课动作改写 is_adjusted=True 并记录 adjustment_log_id。
    """

    __tablename__ = "timetable_schedule_instances"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    class_id = Column(BigInteger, nullable=False, comment="班级ID")
    date = Column(Date, nullable=False, comment="真实日期 2026-07-13")
    slot_id = Column(Integer, ForeignKey("timetable_slots.id"), nullable=False, comment="节次定义")
    period_index = Column(Integer, nullable=False, comment="冗余: 第几节，加速无需JOIN的查询")

    # 动态业务挂钩（支持调代课重写，可能与模板不同）
    subject_id = Column(Integer, nullable=False, comment="学科ID")
    teacher_id = Column(BigInteger, nullable=False, comment="教师 user_id")
    classroom_id = Column(Integer, nullable=True, comment="跑班教室ID")

    # 调代课看守
    is_adjusted = Column(Boolean, default=False, comment="是否被调代课动作改写过")
    adjustment_log_id = Column(Integer, nullable=True, comment="溯源日志ID")

    # 正向关联
    slot = relationship("TimetableSlot", lazy="joined")

    # ⚡ 工业级高能索引
    __table_args__ = (
        UniqueConstraint("class_id", "date", "slot_id", name="uix_class_date_slot"),
        Index("idx_timetable_query_class", "school_id", "date", "class_id"),
        Index("idx_timetable_query_teacher", "school_id", "date", "teacher_id"),
        Index("idx_school_id", "school_id"),
        {"comment": "日历级课表实例"},
    )
