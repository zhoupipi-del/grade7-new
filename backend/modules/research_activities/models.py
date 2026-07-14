"""
research_activities/models.py — 教研活动管理

物理表:
  1. research_activities            — 活动主表 (计划/记录/总结)
  2. research_activity_participants — 参与人员表 (签到/角色/贡献度)
  3. research_activity_agendas      — 议题/议程表 (讨论记录/决议/关联备课听课)

活动状态机:
  PLANNED → IN_PROGRESS → COMPLETED
  PLANNED → CANCELLED
"""

from core.models import Base, SchoolMixin, get_local_now
from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

# ──────────────────────────────────────────────
# 状态枚举
# ──────────────────────────────────────────────
ACT_PLANNED = "planned"  # 已计划
ACT_IN_PROGRESS = "in_progress"  # 进行中
ACT_COMPLETED = "completed"  # 已完成
ACT_CANCELLED = "cancelled"  # 已取消

VALID_ACT_TRANSITIONS = {
    ACT_PLANNED: [ACT_IN_PROGRESS, ACT_CANCELLED],
    ACT_IN_PROGRESS: [ACT_COMPLETED],
    ACT_COMPLETED: [],
    ACT_CANCELLED: [],
}

# 活动类型
ACT_TYPE_REGULAR = "regular_meeting"  # 常规教研会
ACT_TYPE_SPECIAL = "special_topic"  # 专题研讨
ACT_TYPE_LESSON_STUDY = "lesson_study"  # 课例研究
ACT_TYPE_TRAINING = "training"  # 培训进修
ACT_TYPE_EXCHANGE = "exchange"  # 交流观摩

# 参与角色
PART_ORGANIZER = "organizer"  # 组织者
PART_PRESENTER = "presenter"  # 主讲人
PART_RECORDER = "recorder"  # 记录人
PART_PARTICIPANT = "participant"  # 参与者

# 考勤状态
ATTEND_REGISTERED = "registered"  # 已报名
ATTEND_PRESENT = "present"  # 出席
ATTEND_LATE = "late"  # 迟到
ATTEND_ABSENT = "absent"  # 缺席
ATTEND_LEAVE = "leave"  # 请假

# 议题状态
AGENDA_PENDING = "pending"  # 待讨论
AGENDA_DISCUSSING = "discussing"  # 讨论中
AGENDA_RESOLVED = "resolved"  # 已决议
AGENDA_DEFERRED = "deferred"  # 暂缓


class ResearchActivity(Base, SchoolMixin):
    """教研活动主表 — 计划/记录/总结一体"""

    __tablename__ = "research_activities"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # ── 活动基本信息 ──
    title = Column(String(200), nullable=False, comment="活动标题")
    description = Column(Text, comment="活动简介")
    activity_type = Column(
        String(30),
        default=ACT_TYPE_REGULAR,
        comment="类型: regular_meeting/special_topic/lesson_study/training/exchange",
    )

    # ── 学科/年级 ──
    subject_code = Column(String(20), nullable=False, comment="学科代码")
    grade_level = Column(String(20), comment="年级 (可空=跨年级)")

    # ── 时间地点 ──
    planned_at = Column(DateTime, nullable=False, comment="计划开始时间")
    planned_end_at = Column(DateTime, comment="计划结束时间")
    actual_start_at = Column(DateTime, comment="实际开始时间")
    actual_end_at = Column(DateTime, comment="实际结束时间")
    location = Column(String(200), comment="活动地点")

    # ── 状态机 ──
    status = Column(
        String(20),
        default=ACT_PLANNED,
        nullable=False,
        comment="状态: planned/in_progress/completed/cancelled",
    )
    status_updated_at = Column(DateTime, comment="状态最后变更时间")
    status_updated_by = Column(BigInteger, comment="状态变更操作人")
    cancel_reason = Column(Text, comment="取消原因")

    # ── 组织人 ──
    organizer_id = Column(BigInteger, nullable=False, comment="组织人 user_id")

    # ── 活动总结 ──
    summary = Column(Text, comment="活动总结")
    decisions = Column(
        JSON,
        default=list,
        comment='决议事项: ["统一函数章节进度", "下周集体备课主备人:张老师"]',
    )
    attachments = Column(
        JSON,
        default=list,
        comment="附件列表: [{name, url, type}]",
    )

    # ── 血缘咬合备课+听课 ──
    linked_plan_ids = Column(
        JSON,
        default=list,
        comment="关联备课教案ID列表: [1, 3, 7]",
    )
    linked_observation_ids = Column(
        JSON,
        default=list,
        comment="关联听课记录ID列表: [12, 15]",
    )

    # ── 统计 ──
    participant_count = Column(Integer, default=0, comment="参与人数 (缓存)")
    agenda_count = Column(Integer, default=0, comment="议题数 (缓存)")

    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        Index("idx_ra_school_status", "school_id", "status"),
        Index("idx_ra_school_subject", "school_id", "subject_code", "planned_at"),
        Index("idx_ra_organizer", "school_id", "organizer_id"),
        Index("idx_ra_planned", "school_id", "planned_at"),
    )


class ResearchActivityParticipant(Base, SchoolMixin):
    """参与人员表 — 角色/考勤/贡献度"""

    __tablename__ = "research_activity_participants"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    activity_id = Column(BigInteger, nullable=False, comment="关联 research_activities.id")
    user_id = Column(BigInteger, nullable=False, comment="参与者 user_id")

    # ── 角色 ──
    role = Column(
        String(20),
        default=PART_PARTICIPANT,
        comment="角色: organizer/presenter/recorder/participant",
    )

    # ── 考勤 ──
    attendance_status = Column(
        String(20),
        default=ATTEND_REGISTERED,
        comment="考勤: registered/present/late/absent/leave",
    )
    check_in_at = Column(DateTime, comment="签到时间")
    check_out_at = Column(DateTime, comment="签退时间")

    # ── 贡献度 ──
    contribution_score = Column(
        Integer,
        comment="参与贡献度 1-5 (活动后由组织者评定)",
    )
    contribution_note = Column(String(200), comment="贡献度备注")

    # ── 备注 ──
    note = Column(String(200), comment="备注")

    created_at = Column(DateTime, default=get_local_now)

    __table_args__ = (
        UniqueConstraint("activity_id", "user_id", "school_id", name="uk_rap_act_user_school"),
        Index("idx_rap_activity", "school_id", "activity_id"),
        Index("idx_rap_user", "school_id", "user_id"),
    )


class ResearchActivityAgenda(Base, SchoolMixin):
    """议题/议程表 — 讨论记录/决议/关联备课听课"""

    __tablename__ = "research_activity_agendas"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    activity_id = Column(BigInteger, nullable=False, comment="关联 research_activities.id")
    seq = Column(Integer, default=1, comment="议程排序 (从1递增)")

    # ── 议题内容 ──
    title = Column(String(200), nullable=False, comment="议题标题")
    presenter_id = Column(BigInteger, comment="议题主讲人 user_id")
    content = Column(Text, comment="议题内容/讨论记录")

    # ── 时间 ──
    planned_duration = Column(Integer, comment="预计时长(分钟)")
    actual_duration = Column(Integer, comment="实际时长(分钟)")

    # ── 决议 ──
    decision = Column(Text, comment="决议结果")
    status = Column(
        String(20),
        default=AGENDA_PENDING,
        comment="议题状态: pending/discussing/resolved/deferred",
    )

    # ── 血缘咬合 ──
    linked_plan_id = Column(BigInteger, comment="关联备课教案ID")
    linked_observation_id = Column(BigInteger, comment="关联听课记录ID")

    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        Index("idx_rag_activity", "school_id", "activity_id", "seq"),
        Index("idx_rag_status", "school_id", "activity_id", "status"),
    )
