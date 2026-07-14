"""
modules/red_flag/models.py — 流动红旗数据模型

三张核心表：
  - RoutineScore:  日常检查原始评分（卫生/纪律/两操/礼仪/自习）
  - FlagEvaluation: 三维度加权汇总（草稿→发布状态机）
  - FlagArchiveReport: 不可变历史快照（防篡改）

跨模块数据依赖：
  - attendance_records → 考勤异常次数 → attendance_deduction
  - discipline_records → 违纪总扣分 → discipline_deduction
"""

import json

from core.models import Base, SchoolMixin, get_local_now
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)


class RoutineScore(SchoolMixin, Base):
    """日常常规评分 — 班主任/年级组/德育处按类别打分"""

    __tablename__ = "routine_scores"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    class_id = Column(BigInteger, nullable=False, index=True)
    grade_id = Column(BigInteger, nullable=False, index=True)
    category = Column(String(40), nullable=False, comment="评分类别: 卫生/纪律/两操/礼仪/自习")
    score = Column(Integer, nullable=False, comment="评分 0-100")
    note = Column(Text, nullable=True)
    inspector = Column(String(64), nullable=True, comment="检查人")
    scorer_type = Column(
        String(20),
        nullable=False,
        index=True,
        comment="评分人类型: class_teacher/grade_leader/ms_admin",
    )
    record_date = Column(Date, index=True, nullable=False)
    created_at = Column(DateTime, default=get_local_now)

    __table_args__ = (
        UniqueConstraint(
            "class_id",
            "category",
            "record_date",
            "scorer_type",
            name="uq_routine_class_cat_date_scorer",
        ),
        {"comment": "常规评分原始数据"},
    )


class FlagEvaluation(SchoolMixin, Base):
    """流动红旗评价汇总 — 三维度加权 + 违纪/考勤扣分"""

    __tablename__ = "flag_evaluations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    period_type = Column(
        String(10), nullable=False, index=True, comment="评价周期: week/month/term"
    )
    period_label = Column(String(60), nullable=False, comment="周期标签: 第12周/2026年3月")
    grade_id = Column(BigInteger, nullable=False, index=True)
    class_id = Column(BigInteger, nullable=False, index=True)

    # ── 三维度原始均分 ──
    self_score = Column(Float, nullable=True, comment="班主任自评均分")
    grade_score = Column(Float, nullable=True, comment="年级组评级均分")
    ms_score = Column(Float, nullable=True, comment="德育处评级均分")

    # ── 实际权重（维度缺失自适应重分配）──
    self_weight = Column(Float, nullable=False, default=0.2)
    grade_weight = Column(Float, nullable=False, default=0.3)
    ms_weight = Column(Float, nullable=False, default=0.5)

    # ── 加权底分（扣分前）──
    base_score = Column(Float, nullable=True, comment="加权底分")

    # ── 违纪扣分 ──
    discipline_points = Column(Float, nullable=True, comment="违纪总分")
    discipline_deduction = Column(Float, nullable=True, comment="违纪扣分 = points × 系数")

    # ── 考勤扣分 ──
    attendance_exceptions = Column(Integer, nullable=True, comment="考勤异常次数")
    attendance_deduction = Column(Float, nullable=True, comment="考勤扣分 = exceptions × 系数")

    # ── 最终得分 ──
    final_score = Column(Float, nullable=False, default=0.0)
    rank = Column(Integer, nullable=True, comment="年级内排名（发布时计算）")

    status = Column(
        String(10), nullable=False, default="draft", index=True, comment="draft/published"
    )
    created_at = Column(DateTime, default=get_local_now)
    published_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "period_type",
            "period_label",
            "grade_id",
            "class_id",
            "school_id",
            name="uq_flag_eval_period_class",
        ),
        {"comment": "流动红旗评价汇总"},
    )


class FlagArchiveReport(SchoolMixin, Base):
    """流动红旗归档快照 — 不可变历史记录"""

    __tablename__ = "flag_archive_reports"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    period_type = Column(String(10), nullable=False, index=True)
    period_label = Column(String(60), nullable=False)
    grade_id = Column(BigInteger, nullable=False, index=True)
    class_id = Column(BigInteger, nullable=False)

    final_score = Column(Float, nullable=False)
    rank = Column(Integer, nullable=False)
    has_flag = Column(Boolean, default=False, comment="是否获得流动红旗（前2名）")

    base_score = Column(Float, nullable=True)
    discipline_deduction = Column(Float, default=0.0)
    attendance_deduction = Column(Float, default=0.0)

    # 深度冷冻快照 JSON
    snapshot_data_json = Column(Text, nullable=False, comment="完整快照JSON")

    archived_at = Column(DateTime, default=get_local_now)
    archived_by = Column(BigInteger, nullable=False)

    @property
    def snapshot_data(self) -> dict:
        return json.loads(self.snapshot_data_json) if self.snapshot_data_json else {}

    @snapshot_data.setter
    def snapshot_data(self, value: dict):
        self.snapshot_data_json = json.dumps(value, ensure_ascii=False, default=str)

    __table_args__ = (
        UniqueConstraint(
            "period_type", "period_label", "class_id", name="uq_flag_archive_period_class"
        ),
        {"comment": "流动红旗归档快照（不可变）"},
    )
