"""
modules/growth/models.py — 成长档案模块数据模型

P0 重型增强：从只读融合模块升级为双表驱动母舰模块。

两张核心表:
  1. growth_timeline_events — 多态JSON事件流（实时时光轴）
  2. growth_periodical_snapshots — 周期快照（月度/学期五维雷达）

保留原有只读融合能力（7路数据源 → TimelineItem），新增写入+快照+全息画像。
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Float, Text, JSON, ForeignKey, Index

from core.models import Base


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


class GrowthPeriodicalSnapshot(Base):
    __tablename__ = "growth_periodical_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)

    # 快照类型: monthly / semester
    snapshot_type = Column(String(20), nullable=False)
    # 时间标签: "2026-07" / "2025-2026-2"
    period_label = Column(String(20), nullable=False)

    # 归一化五维得分 (0.0 - 100.0)
    academic_score = Column(Float, nullable=False, default=0.0)
    attendance_score = Column(Float, nullable=False, default=0.0)
    behavior_score = Column(Float, nullable=False, default=0.0)
    psych_score = Column(Float, nullable=False, default=0.0)
    activity_score = Column(Float, nullable=False, default=0.0)

    # 统计元数据 JSON
    summary_metrics = Column(JSON, nullable=True)

    # 评语与处方区
    teacher_comment = Column(Text, nullable=True)
    ai_growth_prescription = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_growth_snap_student_period", "student_id", "period_label"),
    )
