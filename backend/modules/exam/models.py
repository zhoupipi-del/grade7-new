"""
modules/exam/models.py — 考试管理模块数据模型

6 张核心表:
- ExamSubject:        考试科目安排（每场考试考哪些科目×时间×满分）
- ExamRoom:           考场（教室/体育馆/实验室）
- ExamArrangement:    考试安排（科目×考场×时间段 = 一场具体考试）
- ExamSeatAssignment: 座位分配（随机/蛇形/手动，含人工覆盖保护）
- ExamInvigilator:    监考安排（主/副监考×冲突检测在 service 层）
- ExamScoreEntryWindow: 成绩录入窗口（pending→open→closed 状态机）

依赖: grades_exams(考试主表), grades_subjects(科目) — 不改现有结构，纯增量
"""

from core.models import Base, SchoolMixin, get_local_now
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Time,
    UniqueConstraint,
)


class ExamSubject(Base, SchoolMixin):
    """考试科目安排 — 每场考试考哪些科目，每科的考试日期/时间段/满分"""

    __tablename__ = "exam_subjects"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exam_id = Column(BigInteger, nullable=False, index=True, comment="考试ID (FK→grades_exams.id)")
    subject_id = Column(
        BigInteger, nullable=False, index=True, comment="科目ID (FK→grades_subjects.id)"
    )
    exam_date = Column(Date, nullable=False, comment="该科目考试日期")
    start_time = Column(Time, nullable=True, comment="开始时间 (如 08:00)")
    end_time = Column(Time, nullable=True, comment="结束时间 (如 09:30)")
    full_score = Column(
        Numeric(6, 2),
        nullable=True,
        comment="本次考试该科目满分 (NULL则取grades_subjects.full_score)",
    )
    is_active = Column(Boolean, default=True, comment="是否启用")
    sort_order = Column(Integer, default=0, comment="排序 (按考试日程顺序)")
    created_at = Column(DateTime, default=get_local_now, comment="创建时间")
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now, comment="更新时间")

    __table_args__ = (
        UniqueConstraint("school_id", "exam_id", "subject_id", name="uk_exam_subject"),
        Index("idx_esubject_exam", "exam_id"),
        Index("idx_esubject_date", "exam_date", "start_time"),
        Index("idx_esubject_school", "school_id"),
    )


class ExamRoom(Base, SchoolMixin):
    """考场 — 教室/体育馆/实验室等可用作考试的场所"""

    __tablename__ = "exam_rooms"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    room_name = Column(String(50), nullable=False, comment="考场名称 (如 2401班教室)")
    room_code = Column(String(30), nullable=True, comment="考场编号 (如 R-2401)")
    building = Column(String(50), nullable=True, comment="楼栋")
    floor = Column(Integer, nullable=True, comment="楼层")
    capacity = Column(Integer, nullable=False, default=30, comment="可用座位数")
    room_type = Column(String(20), default="classroom", comment="类型: classroom/hall/lab")
    class_id = Column(
        BigInteger, nullable=True, index=True, comment="关联班级ID (教室归属, NULL=公共考场)"
    )
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=get_local_now, comment="创建时间")
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now, comment="更新时间")

    __table_args__ = (
        UniqueConstraint("school_id", "room_code", name="uk_exam_room_code"),
        Index("idx_eroom_type", "room_type"),
        Index("idx_eroom_class", "class_id"),
        Index("idx_eroom_school", "school_id"),
    )


class ExamArrangement(Base, SchoolMixin):
    """考试安排 — 科目 × 考场 × 时间段 = 一场具体考试"""

    __tablename__ = "exam_arrangements"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exam_id = Column(BigInteger, nullable=False, index=True, comment="考试ID")
    subject_id = Column(BigInteger, nullable=False, index=True, comment="科目ID")
    room_id = Column(BigInteger, nullable=False, index=True, comment="考场ID")
    exam_date = Column(Date, nullable=False, comment="考试日期")
    start_time = Column(Time, nullable=False, comment="开始时间")
    end_time = Column(Time, nullable=False, comment="结束时间")
    notes = Column(String(200), nullable=True, comment="备注 (如 特殊考生安排)")
    created_at = Column(DateTime, default=get_local_now, comment="创建时间")
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now, comment="更新时间")

    __table_args__ = (
        UniqueConstraint("school_id", "exam_id", "subject_id", "room_id", name="uk_exam_arrange"),
        Index("idx_earrange_exam_subject", "exam_id", "subject_id"),
        Index("idx_earrange_room_date", "room_id", "exam_date"),
        Index("idx_earrange_date", "exam_date"),
        Index("idx_earrange_school", "school_id"),
    )


class ExamSeatAssignment(Base, SchoolMixin):
    """座位分配 — 学生在哪个考场哪个座位号

    支持三种编排方式:
    - random:     随机混编
    - serpentine: 蛇形按总分排名分配（防优生扎堆）
    - manual:     手动指定

    ⚠️ 补丁3: is_manual_override=1 的座位在算法重排时跳过，保护特殊需求。
    """

    __tablename__ = "exam_seat_assignments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exam_id = Column(BigInteger, nullable=False, index=True, comment="考试ID")
    subject_id = Column(BigInteger, nullable=False, index=True, comment="科目ID")
    student_id = Column(BigInteger, nullable=False, index=True, comment="学生ID")
    room_id = Column(BigInteger, nullable=False, index=True, comment="考场ID")
    seat_number = Column(Integer, nullable=False, comment="座位号 (1~capacity)")
    arrangement_method = Column(
        String(20), default="random", comment="编排方式: random/serpentine/manual"
    )
    is_manual_override = Column(
        Boolean, default=False, comment="是否人工强改座位 (1=算法重排时跳过)"
    )
    remark = Column(String(200), nullable=True, comment="备注 (如 骨折/视力障碍/靠门第一排)")
    created_at = Column(DateTime, default=get_local_now, comment="创建时间")

    __table_args__ = (
        UniqueConstraint(
            "school_id", "exam_id", "subject_id", "student_id", name="uk_exam_seat_student"
        ),
        UniqueConstraint(
            "school_id",
            "exam_id",
            "subject_id",
            "room_id",
            "seat_number",
            name="uk_exam_seat_position",
        ),
        Index("idx_eseat_student", "student_id"),
        Index("idx_eseat_room", "room_id"),
        Index("idx_eseat_exam_subject", "exam_id", "subject_id"),
        Index("idx_eseat_school", "school_id"),
    )


class ExamInvigilator(Base, SchoolMixin):
    """监考安排 — 教师监考哪个考场哪个时段，主/副监考

    ⚠️ 补丁2: UNIQUE KEY 只能防同一考场重复指派，无法防时间重叠冲突
       (同一教师同一时段被指派到两个不同考场)
       时间重叠冲突必须在 services.py 的 assign_invigilator() 中做前置校验。
    """

    __tablename__ = "exam_invigilators"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exam_id = Column(BigInteger, nullable=False, index=True, comment="考试ID")
    subject_id = Column(BigInteger, nullable=False, index=True, comment="科目ID")
    room_id = Column(BigInteger, nullable=False, index=True, comment="考场ID")
    user_id = Column(BigInteger, nullable=False, index=True, comment="监考教师用户ID (FK→users.id)")
    role = Column(String(20), default="chief", comment="监考角色: chief(主监考)/assistant(副监考)")
    exam_date = Column(Date, nullable=False, comment="考试日期")
    start_time = Column(Time, nullable=False, comment="开始时间")
    end_time = Column(Time, nullable=False, comment="结束时间")
    notes = Column(String(200), nullable=True, comment="备注")
    created_at = Column(DateTime, default=get_local_now, comment="创建时间")
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now, comment="更新时间")

    __table_args__ = (
        UniqueConstraint(
            "school_id", "exam_id", "subject_id", "room_id", "user_id", name="uk_exam_invigilator"
        ),
        Index("idx_einv_user", "user_id"),
        Index("idx_einv_date_time", "exam_date", "start_time"),
        Index("idx_einv_exam_subject", "exam_id", "subject_id"),
        Index("idx_einv_school", "school_id"),
    )


class ExamScoreEntryWindow(Base, SchoolMixin):
    """成绩录入窗口 — 控制哪个科目哪个班级的成绩录入开关

    状态机: pending → open → closed
    班主任只能在自己班级的窗口 open 时录入成绩。

    ⚠️ 补丁1: class_id 可为 NULL，NULL 代表全校该科目通开（粗粒度场景）
       非NULL时精确到班级，防止跨班级篡改和进度不一。
    """

    __tablename__ = "exam_score_entry_windows"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exam_id = Column(BigInteger, nullable=False, index=True, comment="考试ID")
    subject_id = Column(BigInteger, nullable=False, index=True, comment="科目ID")
    class_id = Column(
        BigInteger,
        nullable=True,
        index=True,
        comment="班级ID (NULL=全校该科通开, 非NULL=精确到班级)",
    )
    status = Column(String(20), default="pending", comment="状态: pending/open/closed")
    opened_at = Column(DateTime, nullable=True, comment="开放时间")
    closed_at = Column(DateTime, nullable=True, comment="关闭时间")
    opened_by = Column(BigInteger, nullable=True, comment="开放操作者 user_id")
    closed_by = Column(BigInteger, nullable=True, comment="关闭操作者 user_id")
    entry_count = Column(Integer, default=0, comment="已录入成绩条数")
    expected_count = Column(Integer, nullable=True, comment="应录入条数 (班级人数)")
    created_at = Column(DateTime, default=get_local_now, comment="创建时间")
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now, comment="更新时间")

    __table_args__ = (
        UniqueConstraint("school_id", "exam_id", "subject_id", "class_id", name="uk_exam_entry"),
        Index("idx_eentry_status", "status"),
        Index("idx_eentry_class", "class_id"),
        Index("idx_eentry_exam_subject", "exam_id", "subject_id"),
        Index("idx_eentry_school", "school_id"),
    )
