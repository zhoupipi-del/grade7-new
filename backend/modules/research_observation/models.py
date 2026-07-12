"""
research_observation/models.py — 听课评课量化追踪

物理表:
  1. research_class_observations    — 听课记录主表 (血缘咬合 lesson_plan_id)
  2. research_observation_rubrics   — 多维量化打分快照表 (JSON动态评分矩阵)
  3. research_observation_appeals   — 教师确认/申诉状态机表

反馈状态机:
  PENDING (待教师确认)
    → CONFIRMED (教师已确认)
    → APPEALED (教师申诉中) → RESOLVED (申诉已处理)
"""

from sqlalchemy import (
    Column, BigInteger, String, Integer, Float, Boolean, DateTime, Text, JSON,
    ForeignKey, Index, UniqueConstraint,
)

from core.models import Base, get_local_now
from core.models import SchoolMixin


# ──────────────────────────────────────────────
# 反馈状态枚举
# ──────────────────────────────────────────────
FEEDBACK_PENDING = "pending"        # 待教师确认
FEEDBACK_CONFIRMED = "confirmed"    # 教师已确认
FEEDBACK_APPEALED = "appealed"      # 教师申诉中
FEEDBACK_RESOLVED = "resolved"      # 申诉已处理

VALID_FEEDBACK_TRANSITIONS = {
    FEEDBACK_PENDING: [FEEDBACK_CONFIRMED, FEEDBACK_APPEALED],
    FEEDBACK_CONFIRMED: [],  # 终态
    FEEDBACK_APPEALED: [FEEDBACK_RESOLVED],
    FEEDBACK_RESOLVED: [],   # 终态
}

# 听课类型
OBS_TYPE_ROUTINE = "routine"        # 常规推门听课
OBS_TYPE_SCHEDULED = "scheduled"    # 计划性听课
OBS_TYPE_PUBLIC = "public"          # 公开课
OBS_TYPE_DEMO = "demo"              # 示范课
OBS_TYPE_COMPETITION = "competition"  # 比赛课


class ResearchClassObservation(Base, SchoolMixin):
    """听课记录主表 — 血缘咬合集体备课教案"""

    __tablename__ = "research_class_observations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # ── 人员 ──
    observer_id = Column(BigInteger, nullable=False, comment="听课人 user_id")
    teacher_id = Column(BigInteger, nullable=False, comment="授课人 user_id")
    class_id = Column(BigInteger, nullable=False, comment="班级ID")

    # ── 教学信息 ──
    subject_code = Column(String(20), nullable=False, comment="学科代码")
    lesson_title = Column(String(200), comment="课题名称")
    observation_type = Column(
        String(20), default=OBS_TYPE_ROUTINE,
        comment="听课类型: routine/scheduled/public/demo/competition",
    )

    # ── 血缘咬合集体备课 ──
    lesson_plan_id = Column(BigInteger, comment="关联 research_lesson_plans.id (可空, 无教案时为NULL)")
    plan_version_number = Column(Integer, comment="听课时教案版本号 (锁定快照)")

    # ── 量化评分 ──
    score_total = Column(Float, comment="量化总分 (从rubric自动计算)")
    score_max = Column(Float, default=100.0, comment="满分分值")
    score_percentage = Column(Float, comment="得分率%")

    # ── 评级 ──
    grade = Column(
        String(10),
        comment="等级: excellent(优)/good(良)/fair(中)/needs_improvement(待改进)",
    )

    # ── 文本反馈 ──
    text_feedback = Column(
        JSON,
        comment='结构化文本: {highlights:[], suggestions:[], overall_comment}',
    )

    # ── 教案执行度 ──
    plan_adherence = Column(
        String(20),
        comment="教案执行度: full(完全执行)/partial(部分调整)/deviated(明显偏离)",
    )
    plan_deviation_note = Column(Text, comment="偏离说明 (如果partial/deviated)")

    # ── 反馈状态机 ──
    feedback_status = Column(
        String(20), default=FEEDBACK_PENDING, nullable=False,
        comment="反馈状态: pending/confirmed/appealed/resolved",
    )
    feedback_status_updated_at = Column(DateTime, comment="反馈状态最后变更时间")
    teacher_viewed_at = Column(DateTime, comment="教师首次查看时间")

    # ── 时间 ──
    observed_at = Column(DateTime, nullable=False, comment="听课日期时间")
    duration_minutes = Column(Integer, default=45, comment="听课时长(分钟)")

    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        Index("idx_rco_school_observer", "school_id", "observer_id", "observed_at"),
        Index("idx_rco_school_teacher", "school_id", "teacher_id", "observed_at"),
        Index("idx_rco_school_status", "school_id", "feedback_status"),
        Index("idx_rco_plan", "school_id", "lesson_plan_id"),
    )


class ResearchObservationRubric(Base, SchoolMixin):
    """多维量化打分快照 — JSON动态评分矩阵"""

    __tablename__ = "research_observation_rubrics"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    observation_id = Column(BigInteger, nullable=False, comment="关联 research_class_observations.id")

    # ── 评分模板信息 ──
    template_name = Column(String(100), comment="评分模板名称 (如: 常规听课评分表/公开课评分表)")
    template_version = Column(String(20), comment="模板版本")

    # ── 多维评分矩阵 ──
    rubric_metrics = Column(
        JSON, nullable=False,
        comment=(
            "多维动态评分: ["
            '{name, score, max, weight, comment}'
            "] 示例: [{name:'教学引入',score:9,max:10,comment:'导入自然'}]"
        ),
    )

    # ── 汇总 ──
    total_score = Column(Float, nullable=False, comment="总分 (各维度score之和)")
    max_score = Column(Float, nullable=False, default=100.0, comment="满分")
    percentage = Column(Float, comment="得分率%")

    # ── 评分人 ──
    scorer_id = Column(BigInteger, nullable=False, comment="评分人 user_id")

    created_at = Column(DateTime, default=get_local_now)

    __table_args__ = (
        UniqueConstraint("observation_id", "school_id", name="uk_ror_obs_school"),
        Index("idx_ror_observation", "school_id", "observation_id"),
    )


class ResearchObservationAppeal(Base, SchoolMixin):
    """教师确认/申诉记录 — 状态机追踪"""

    __tablename__ = "research_observation_appeals"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    observation_id = Column(BigInteger, nullable=False, comment="关联 research_class_observations.id")
    teacher_id = Column(BigInteger, nullable=False, comment="教师 user_id")

    # ── 申诉/确认类型 ──
    action_type = Column(
        String(20), nullable=False,
        comment="动作类型: confirm(确认) / appeal(申诉) / resolve(处理申诉)",
    )

    # ── 申诉内容 ──
    appeal_reason = Column(Text, comment="申诉理由 (action_type=appeal时填写)")
    appealed_dimensions = Column(
        JSON, comment="申诉维度列表: ['重难点突出', '生生互动']",
    )

    # ── 处理结果 ──
    resolution = Column(Text, comment="处理结论 (action_type=resolve时填写)")
    resolved_by = Column(BigInteger, comment="处理人 user_id")
    score_adjusted = Column(Boolean, default=False, comment="是否调整了评分")
    adjusted_total_score = Column(Float, comment="调整后总分")

    # ── 时间 ──
    created_at = Column(DateTime, default=get_local_now)
    resolved_at = Column(DateTime, comment="处理时间")

    __table_args__ = (
        Index("idx_rap_observation", "school_id", "observation_id"),
        Index("idx_rap_teacher", "school_id", "teacher_id"),
    )
