"""
modules/growth/models.py — 成长档案模块数据模型

P0 重型增强：从只读融合模块升级为双表驱动母舰模块。

两张核心表:
  1. growth_timeline_events — 多态JSON事件流（实时时光轴）
  2. growth_periodical_snapshots — 周期快照（月度/学期五维雷达）

保留原有只读融合能力（7路数据源 → TimelineItem），新增写入+快照+全息画像。

枚举类:
  GrowthDimension — 五育维度 (学业/考勤/行为/心理/活动)
  EventSeverity  — 事件严重度 (常态/正向加分/轻度预警/严重红灯)
"""

import enum
from datetime import datetime

from core.models import Base
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

# ═══════════════════════════════════════════════════════════════
#  枚举定义 — 与 BOSS 设计图纸对齐
# ═══════════════════════════════════════════════════════════════


class GrowthDimension(str, enum.Enum):
    """成长五育维度 — 对应五维雷达画像的5个轴"""

    ACADEMIC = "academic"  # 学业：考试均分 + 错题断层收敛率
    ATTENDANCE = "attendance"  # 考勤：出勤异常扣分
    BEHAVIOR = "behavior"  # 行为：违纪处分扣分 + 表彰加分
    PSYCHOLOGY = "psychology"  # 心理：风险等级映射
    ACTIVITY = "activity"  # 活动：教研/课外活动参与度


class EventSeverity(str, enum.Enum):
    """事件严重度4级 — 驱动时光轴卡片渲染和考勤/行为扣分权重"""

    INFO = "info"  # 常态事件：日常记录，不扣分
    BONUS = "bonus"  # 正向加分：表彰/荣誉/进步
    WARNING = "warning"  # 轻度预警：迟到/作业缺交/轻微违纪
    CRITICAL = "critical"  # 严重红灯：处分/严重违纪/心理高危


# ═══════════════════════════════════════════════════════════════
#  表1: 成长时光轴事件 — 高频流式多态事件表
# ═══════════════════════════════════════════════════════════════


class GrowthTimelineEvent(Base):
    __tablename__ = "growth_timeline_events"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)

    # 五育维度: academic / attendance / behavior / psychology / activity
    dimension = Column(String(20), nullable=False, index=True)
    # 严重/激励级别: info / bonus / warning / critical
    severity = Column(String(20), nullable=False, default="info")

    # 具体事件标识，如 "hw_missing", "gap_critical", "discipline_punish"
    event_type = Column(String(50), nullable=False)
    # 页面显示标题
    title = Column(String(200), nullable=False)
    # 事件真实发生时间
    occurred_at = Column(DateTime, nullable=False, index=True)

    # 多态载荷：根据 event_type 存放不同结构化指标
    payload = Column(JSON, nullable=True)

    # 记录人（系统触发则为NULL）
    reporter_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_growth_events_student_time", "student_id", "occurred_at"),
        Index("ix_growth_events_school_dim", "school_id", "dimension"),
    )


# ═══════════════════════════════════════════════════════════════
#  表2: 周期成长快照 — 低频归一化五维雷达画像表
# ═══════════════════════════════════════════════════════════════


class GrowthPeriodicalSnapshot(Base):
    __tablename__ = "growth_periodical_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)

    # 快照类型: monthly / semester
    snapshot_type = Column(String(20), nullable=False)
    # 时间标签: "2026-07" / "2025-2026-2"
    period_label = Column(String(20), nullable=False)

    # 归一化五维得分 (0.0 - 100.0)，默认100.0（满分基准，扣分制）
    academic_score = Column(Float, nullable=False, default=100.0)
    attendance_score = Column(Float, nullable=False, default=100.0)
    behavior_score = Column(Float, nullable=False, default=100.0)
    psych_score = Column(Float, nullable=False, default=100.0)
    activity_score = Column(Float, nullable=False, default=100.0)

    # 统计元数据 JSON
    summary_metrics = Column(JSON, nullable=True)

    # 评语与处方区
    teacher_comment = Column(Text, nullable=True)
    ai_growth_prescription = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_growth_snap_student_period", "student_id", "period_label"),)


# ═══════════════════════════════════════════════════════════════
#  表3: 主动复合预警 — CEP (Complex Event Processing) 拦截器持久化
# ═══════════════════════════════════════════════════════════════


class ActiveCompositeAlert(Base):
    """
    主动复合预警记录 — 当考勤危机 × 学业断层在 48h 滑动时间窗内交汇时，
    CEP 拦截器自动唤醒 V3 AI 引擎生成靶向处方，持久化至此表。

    生命周期: CRITICAL_COMPOSITE → RESOLVED (班主任/德育处确认处理)
    冷却机制: 同一学生 3 天内仅触发一次 (Redis SETNX 冷却锁)
    """

    __tablename__ = "growth_active_composite_alerts"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)

    # 预警类型: CRITICAL_COMPOSITE (考勤×学业), 后续可扩展更多组合
    alert_type = Column(String(50), nullable=False, default="CRITICAL_COMPOSITE")
    # 预警标题: "复合预警: 连续缺勤3天 + 知识断层critical"
    title = Column(String(200), nullable=False)

    # 触发元数据 JSON — 记录哪两个事件在什么时间交汇
    # 例: {"attendance": {"consecutive": 3, "window_key": "..."}, "error_funnel": {"kp": "...", "level": "critical", "window_key": "..."}}
    reason_meta = Column(Text, nullable=False)

    # V3 AI 引擎生成的靶向处方 (Markdown)
    ai_prescription = Column(Text, nullable=False)

    # 处置状态
    is_resolved = Column(Boolean, default=False, index=True)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Human-in-the-Loop 微调区 — 班主任/德育处签署归档时填入
    resolution_note = Column(Text, nullable=True, comment="处置备注（教师手动填写）")
    final_prescription = Column(
        Text, nullable=True, comment="人工微调后的最终处方（V3原始→教师修正）"
    )

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_growth_alert_school_student", "school_id", "student_id"),
        Index("ix_growth_alert_unresolved", "is_resolved", "created_at"),
    )
