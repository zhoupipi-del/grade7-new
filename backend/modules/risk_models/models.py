"""
modules/risk_models/models.py — 风险预警雷达数据模型

表:
  - risk_warnings: 风险预警记录主表
  - warning_feedback: 预警反馈表 (教师处置记录)
  - risk_baselines: 风险基线表 (学生行为基线动态更新)
"""

from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, Date, DateTime,
    ForeignKey, Text, Index, Float,
)
from sqlalchemy.orm import relationship
from core.models import Base, SchoolMixin, get_local_now


class RiskWarning(Base, SchoolMixin):
    """风险预警记录 — 继承 SchoolMixin 实现多租户隔离"""
    __tablename__ = "risk_warnings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True)
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=False, index=True)
    grade_id = Column(BigInteger, ForeignKey("grades.id"), nullable=False, index=True)

    # RDI 风险偏离指数
    rdi_score = Column(Float, nullable=False, comment="RDI 风险偏离指数 (Z-Score)")
    risk_level = Column(String(20), nullable=False, comment="normal/attention/intervention")

    # 三维度偏离详情 (JSON 存储)
    behavior_deviation = Column(Float, default=0.0, comment="行为维度偏离度 (Z-Score)")
    attendance_deviation = Column(Float, default=0.0, comment="考勤维度偏离度 (Z-Score)")
    score_deviation = Column(Float, default=0.0, comment="评价维度偏离度 (Z-Score)")

    # 滑动窗口配置
    window_short = Column(Integer, default=7, comment="短窗口天数 (默认7天)")
    window_medium = Column(Integer, default=30, comment="中窗口天数 (默认30天)")
    window_long = Column(Integer, default=90, comment="长窗口天数 (默认90天)")

    # EWMA 趋势检测
    ewma_trend = Column(Float, default=0.0, comment="EWMA 指数加权移动平均趋势")
    is_escalating = Column(Boolean, default=False, comment="是否呈 escalation 趋势")

    # 预警状态
    status = Column(String(20), default="active", comment="active/handled/false_positive/expired")
    handled_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    handled_at = Column(DateTime, nullable=True)
    handling_note = Column(Text, nullable=True, comment="处置备注 (谈心/家访/ Behavior Intervention Plan)")

    # 触发事件
    trigger_event_type = Column(String(40), nullable=True, comment="触发事件类型 (fighting/lateness/...)")
    trigger_event_id = Column(BigInteger, nullable=True, comment="触发事件ID")

    # 时间戳
    warned_at = Column(DateTime, default=get_local_now, comment="预警生成时间")
    expires_at = Column(DateTime, nullable=True, comment="预警过期时间 (默认7天后)")

    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    # 关系
    student = relationship("core.models.Student", lazy="selectin")
    handler = relationship("core.models.User", foreign_keys=[handled_by], lazy="selectin")

    __table_args__ = (
        Index("idx_rw_student_warned", "student_id", "warned_at"),
        Index("idx_rw_class_status", "class_id", "status"),
        Index("idx_rw_rdi_score", "rdi_score"),
    )


class WarningFeedback(Base, SchoolMixin):
    """预警反馈 — 教师处置记录"""
    __tablename__ = "warning_feedback"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    warning_id = Column(BigInteger, ForeignKey("risk_warnings.id"), nullable=False, index=True)
    teacher_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)

    # 处置动作
    action_taken = Column(String(40), nullable=False, comment="heart_to_heart/talk_to_parent/intervention_plan/dismiss")
    action_detail = Column(Text, nullable=True, comment="处置详细说明")

    # 效果评估
    effectiveness = Column(String(20), nullable=True, comment="effective/partially/pending/ineffective")
    follow_up_needed = Column(Boolean, default=False)

    # 时间戳
    created_at = Column(DateTime, default=get_local_now)

    # 关系
    warning = relationship("RiskWarning", backref="feedback_records")
    teacher = relationship("core.models.User", lazy="selectin")

    __table_args__ = (
        Index("idx_wf_warning", "warning_id"),
    )


class RiskBaseline(Base, SchoolMixin):
    """风险基线 — 学生行为基线动态更新 (滑动窗口均值/标准差)"""
    __tablename__ = "risk_baselines"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True)
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=False)

    # 基线类型
    baseline_type = Column(String(20), nullable=False, comment="behavior/attendance/score")
    window_days = Column(Integer, nullable=False, comment="滑动窗口天数 (7/30/90)")

    # 统计基线 (SPC)
    mean_value = Column(Float, default=0.0, comment="窗口内均值")
    std_value = Column(Float, default=0.0, comment="窗口内标准差")
    sample_size = Column(Integer, default=0, comment="样本量")

    # EWMA 参数
    ewma_value = Column(Float, default=0.0, comment="EWMA 指数加权移动平均")
    lambda_param = Column(Float, default=0.3, comment="EWMA 平滑系数 λ")

    # 最后更新
    last_updated = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        Index("idx_rb_student_type", "student_id", "baseline_type", "window_days"),
    )
