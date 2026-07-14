"""
psych_profiles/models.py — 学生心理档案 + 筛查快照

物理表:
  1. psy_profiles            — 心理综合档案主表 (一学生一档案)
  2. psy_screening_records   — 量表筛查流水快照

非物理表 (API层联表查询):
  rdi_psy_nexus — 学业x心理双轨预警合成视图
    联表: risk_warnings (RDI四维) + student_risk_alerts (Z-Score学业) + psy_profiles (心理)
"""

from core.models import Base, SchoolMixin, get_local_now
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)


# ──────────────────────────────────────────────
# Layer 1: 心理综合档案主表
# ──────────────────────────────────────────────
class PsyProfile(Base, SchoolMixin):
    """学生心理综合档案 — 一学生一档案, 长期动态画像"""

    __tablename__ = "psy_profiles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, nullable=False, comment="学生ID (逻辑外键 students.id)")

    # ── 动态风险等级 ──
    risk_level = Column(
        String(10),
        default="green",
        comment="综合风险等级: green(正常)/yellow(关注)/orange(预警)/red(危机)",
    )
    risk_level_source = Column(
        String(20),
        default="manual",
        comment="风险等级来源: manual(手动设定)/auto(自动计算)/screening(筛查驱动)/nexus(双轨合成)",
    )
    risk_level_updated_at = Column(DateTime, comment="风险等级最后更新时间")
    risk_level_updated_by = Column(BigInteger, comment="风险等级最后更新人 user_id")

    # ── 标签云 ──
    tags = Column(JSON, default=list, comment='标签云: ["单亲家庭", "考前焦虑", "人际敏感"]')

    # ── 家校沟通 ──
    guardian_contact_status = Column(
        String(20),
        default="normal",
        comment="家校沟通状态: normal(正常)/sensitive(敏感)/restricted(受限)/blocked(阻断)",
    )
    guardian_contact_note = Column(String(200), comment="家校沟通备注(明文)")

    # ── 聚合统计 (定期从子表聚合, 非实时) ──
    total_counseling_count = Column(
        Integer, default=0, comment="累计咨询次数 (从 psy_consult_records 聚合)"
    )
    total_screening_count = Column(Integer, default=0, comment="累计筛查次数")
    total_intervention_count = Column(
        Integer, default=0, comment="累计干预次数 (从 intervention_records 聚合)"
    )
    highest_risk_level = Column(
        String(10),
        default="green",
        comment="历史最高风险等级: green/yellow/orange/red",
    )

    # ── 转介追踪 ──
    is_referred = Column(Boolean, default=False, comment="是否曾转介外部医院/机构")
    referral_status = Column(
        String(20),
        comment="转介状态: pending(待转介)/in_progress(转介中)/completed(已完成)/returned(已回转)",
    )
    referral_target = Column(String(200), comment="转介医院/机构名称")

    # ── 最近活动时间戳 ──
    last_counseling_date = Column(DateTime, comment="最近咨询日期")
    last_screening_date = Column(DateTime, comment="最近筛查日期")
    last_intervention_date = Column(DateTime, comment="最近干预日期")

    # ── 明文备注 (非敏感) ──
    notes = Column(Text, comment="档案备注(明文, 非敏感信息)")

    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        UniqueConstraint("student_id", "school_id", name="uk_psy_profile_student_school"),
        Index("idx_psy_profile_risk", "school_id", "risk_level"),
        Index("idx_psy_profile_school", "school_id"),
    )


# ──────────────────────────────────────────────
# Layer 2: 量表筛查流水快照
# ──────────────────────────────────────────────
class PsyScreeningRecord(Base, SchoolMixin):
    """量表筛查流水快照 — 每次筛查的精简记录, 便于快速查询历史"""

    __tablename__ = "psy_screening_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, nullable=False, comment="学生ID (逻辑外键 students.id)")

    # ── 量表信息 ──
    scale_name = Column(
        String(100),
        nullable=False,
        comment="量表名称: MSSMHS-55 / SCL-90 / MHT / SDS / SAS / PCE-55",
    )
    scale_version = Column(String(20), comment="量表版本")

    # ── 原始分 ──
    raw_scores = Column(JSON, comment="各因子原始分: {dimension: score}")
    total_score = Column(Float, comment="量表总分")

    # ── 风险因子 ──
    risk_factors = Column(
        JSON,
        default=list,
        comment='高风险因子列表: ["depression:4.2", "anxiety:3.8"]',
    )
    risk_level = Column(
        String(10),
        default="green",
        comment="本次筛查风险等级: green/yellow/orange/red",
    )

    # ── 结论 ──
    conclusion = Column(Text, comment="AI/专家综合判定结论")
    ai_generated = Column(Boolean, default=False, comment="结论是否AI生成")

    # ── 来源 ──
    source = Column(
        String(20),
        default="self_report",
        comment="来源: self_report(自填)/teacher_referral(教师转介)/routine(常规筛查)/external(外部导入)/synced(从mental_health_assessments同步)",
    )
    operator_id = Column(BigInteger, comment="操作人 user_id")

    # ── 关联 ──
    assessment_id = Column(BigInteger, comment="关联 mental_health_assessments.id (如从评估同步)")

    test_date = Column(DateTime, nullable=False, comment="测试日期")
    created_at = Column(DateTime, default=get_local_now)

    __table_args__ = (
        Index("idx_psy_screening_student", "school_id", "student_id", "test_date"),
        Index("idx_psy_screening_scale", "school_id", "scale_name"),
        Index("idx_psy_screening_risk", "school_id", "risk_level"),
    )
