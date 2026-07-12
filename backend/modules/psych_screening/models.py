"""
Psych Screening 数据模型 — 心理筛查与干预全生命周期

表归属:
  - psych_surveys / mental_health_assessments: 由 risk_models 模块管理 (已含 ETL + 四维桥接)
  - mental_health_questions:   量表问题库 (种子数据) ← 本模块
  - mental_health_answers:     学生答题明细 ← 本模块
  - intervention_records:      绿洲干预追踪 ← 本模块

为避免与 risk_models 的表定义冲突，PsychSurvey 和 MentalHealthAssessment 从此处导入:
  from modules.risk_models.models import PsychSurvey, MentalHealthAssessment
"""

from sqlalchemy import (
    Column, BigInteger, String, Integer, Float, Boolean, Date, DateTime,
    Text, ForeignKey, JSON,
)
from sqlalchemy.orm import relationship
from core.models import Base, SchoolMixin, get_local_now

# 从 risk_models 导入已存在的模型 (避免 Metadata 冲突)
from modules.risk_models.models import PsychSurvey, MentalHealthAssessment  # noqa: F401

__all__ = [
    "PsychSurvey",
    "MentalHealthAssessment",
    "MentalHealthQuestion",
    "MentalHealthAnswer",
    "InterventionRecord",
]


# ============================================================
# 表 1 — 量表问题库
# ============================================================

class MentalHealthQuestion(Base, SchoolMixin):
    """
    量表问题库表

    存储 MSSMHS-55 / SCL-90 等量表的题目。
    option_type: likert5 (1-5 级评分) / boolean
    reverse_scoring: True 表示反向计分 (6 - 选项值)
    """
    __tablename__ = "mental_health_questions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    scale_name = Column(String(100), nullable=False, index=True,
                        comment="量表名称: MSSMHS-55 / SCL-90")
    dimension = Column(String(50), nullable=False, comment="所属维度 (10 维度之一)")
    question_no = Column(Integer, nullable=False, comment="题号 (1-55)")
    question_text = Column(Text, nullable=False, comment="题目文本")
    option_type = Column(String(20), default="likert5", comment="likert5 / boolean")
    reverse_scoring = Column(Boolean, default=False, comment="是否反向计分")
    sort_order = Column(Integer, comment="排序权重")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=get_local_now)


# ============================================================
# 表 2 — 学生答题明细
# ============================================================

class MentalHealthAnswer(Base, SchoolMixin):
    """
    学生答题明细表

    每条记录对应一道题的作答，关联到一次评估记录。
    answer_value: 1-5 的评分值
    answer_text:  开放题文本 (备用)
    """
    __tablename__ = "mental_health_answers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    assessment_id = Column(BigInteger, ForeignKey("mental_health_assessments.id"),
                           nullable=False, index=True)
    question_id = Column(BigInteger, ForeignKey("mental_health_questions.id"),
                         nullable=False, index=True)
    answer_value = Column(Integer, comment="1-5 评分")
    answer_text = Column(Text, comment="开放题文本")
    created_at = Column(DateTime, default=get_local_now)

    # 关联
    assessment = relationship("MentalHealthAssessment", lazy="selectin")
    question = relationship("MentalHealthQuestion", lazy="selectin")


# ============================================================
# 表 3 — 绿洲干预追踪
# ============================================================

class InterventionRecord(Base, SchoolMixin):
    """
    心理健康干预追踪记录表

    在评估创建后，由教师发起干预 (谈话/辅导/联动家长/转介)。
    支持随访闭环：follow_up_done → effect_rating → mh_risk_improved
    """
    __tablename__ = "intervention_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True)
    teacher_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True,
                        comment="干预教师")
    assessment_id = Column(BigInteger, ForeignKey("mental_health_assessments.id"),
                           index=True, comment="关联评估 (可选)")
    mh_risk_before = Column(String(20), comment="干预前风险等级: low/medium/high")
    mh_risk_after = Column(String(20), comment="随访后风险等级: low/medium/high")
    intervention_type = Column(String(50), nullable=False, index=True,
                               comment="心理谈话/家长联动/心理辅导/危机干预/转介专业机构/其他")
    notes = Column(Text, comment="干预记录/谈话摘要")
    parent_feedback = Column(Text, comment="家长反馈")
    effect_rating = Column(String(20), index=True,
                           comment="效果评定: 显著好转/略有好转/无变化/恶化")
    intervention_date = Column(Date, index=True, comment="干预日期")
    follow_up_date = Column(Date, comment="计划随访日期")
    follow_up_done = Column(Boolean, default=False, comment="随访是否完成")
    follow_up_notes = Column(Text, comment="随访记录")
    status = Column(String(20), nullable=False, default="tracking",
                    comment="tracking / completed / cancelled")
    created_at = Column(DateTime, default=get_local_now, index=True)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    # 关联
    student = relationship("Student", foreign_keys=[student_id], lazy="selectin")
    teacher = relationship("User", foreign_keys=[teacher_id], lazy="selectin")
    assessment = relationship("MentalHealthAssessment", lazy="selectin")

    # 辅助属性
    @property
    def is_effective(self):
        """干预是否有效 (显著好转 或 略有好转)"""
        return self.effect_rating in ("显著好转", "略有好转")

    @property
    def mh_risk_improved(self):
        """风险等级是否改善 (high→medium→low)"""
        risk_order = {"low": 1, "medium": 2, "high": 3}
        before = risk_order.get(self.mh_risk_before, 0)
        after = risk_order.get(self.mh_risk_after, 0)
        if before == 0 or after == 0:
            return None  # 无法判定
        return after < before
