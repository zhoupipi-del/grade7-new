"""
modules/risk_models/models.py — 风险预警雷达数据模型

表:
  - risk_warnings: 风险预警记录主表 (四维: behavior/attendance/score/psych)
  - warning_feedback: 预警反馈表 (教师处置记录)
  - risk_baselines: 风险基线表 (学生行为基线动态更新)
  - psych_surveys: 心理筛查问卷原始数据表 (v3.1 四维桥接)
  - mental_health_assessments: 心理健康评估结论表 (v3.1)
  - psych_cross_analyses: 跨维度交叉分析表 (v3.1)

v3.1 四维桥接:
  - RiskWarning 新增 psych_deviation / psych_veto_triggered / veto_dimension
  - 三张 psych 表 ORM 落地，school_id 多租户索引 + source_id 追溯外键对齐
"""

from core.models import Base, SchoolMixin, get_local_now
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship


class RiskWarning(Base, SchoolMixin):
    """风险预警记录 — 继承 SchoolMixin 实现多租户隔离 (四维版)"""

    __tablename__ = "risk_warnings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True)
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=False, index=True)
    grade_id = Column(BigInteger, ForeignKey("grades.id"), nullable=False, index=True)

    # RDI 风险偏离指数
    rdi_score = Column(Float, nullable=False, comment="RDI 风险偏离指数 (Z-Score)")
    risk_level = Column(String(20), nullable=False, comment="normal/attention/intervention")

    # 四维度偏离详情 (v3.1: 新增 psych 维度)
    behavior_deviation = Column(Float, default=0.0, comment="行为维度偏离度 (Z-Score)")
    attendance_deviation = Column(Float, default=0.0, comment="考勤维度偏离度 (Z-Score)")
    score_deviation = Column(Float, default=0.0, comment="评价维度偏离度 (Z-Score)")
    psych_deviation = Column(
        Float, default=0.0, comment="心理维度偏离度 (Z-Score, 极端维度驱动模型)"
    )

    # 一票否决铁闸 (v3.1: psych_veto + discipline_veto 并列互锁)
    psych_veto_triggered = Column(
        Boolean, default=False, comment="心理一票否决触发标记 (1=单项超过3σ强制红灯)"
    )
    veto_dimension = Column(
        String(40), nullable=True, comment="触发一票否决的具体维度名 (如 depression_score)"
    )

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
    handling_note = Column(
        Text, nullable=True, comment="处置备注 (谈心/家访/ Behavior Intervention Plan)"
    )

    # 触发事件
    trigger_event_type = Column(
        String(40), nullable=True, comment="触发事件类型 (fighting/lateness/...)"
    )
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
    action_taken = Column(
        String(40),
        nullable=False,
        comment="heart_to_heart/talk_to_parent/intervention_plan/dismiss",
    )
    action_detail = Column(Text, nullable=True, comment="处置详细说明")

    # 效果评估
    effectiveness = Column(
        String(20), nullable=True, comment="effective/partially/pending/ineffective"
    )
    follow_up_needed = Column(Boolean, default=False)

    # 时间戳
    created_at = Column(DateTime, default=get_local_now)

    # 关系
    warning = relationship("RiskWarning", backref="feedback_records")
    teacher = relationship("core.models.User", lazy="selectin")

    __table_args__ = (Index("idx_wf_warning", "warning_id"),)


class RiskBaseline(Base, SchoolMixin):
    """风险基线 — 学生行为基线动态更新 (滑动窗口均值/标准差)

    v3.1: baseline_type 扩展支持 'psych' (398行 psych baseline 已由 ETL 初始化)
    """

    __tablename__ = "risk_baselines"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True)
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=False)

    # 基线类型: behavior / attendance / score / psych
    baseline_type = Column(String(20), nullable=False, comment="behavior/attendance/score/psych")
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

    __table_args__ = (Index("idx_rb_student_type", "student_id", "baseline_type", "window_days"),)


# =============================================================================
# v3.1 四维桥接: 心理筛查三表 ORM 落地
# =============================================================================


class PsychSurvey(Base, SchoolMixin):
    """心理筛查问卷原始数据表 — 10维标准分数 JSON Key 严格标准化 (v3.1)

    ETL 血缘: 640条 (319 MSSMHS-55 + 321 PCE-55), source_id 100% 可追溯 grade7_new
    """

    __tablename__ = "psych_surveys"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    school_id = Column(
        BigInteger, ForeignKey("schools.id"), nullable=False, comment="所属学校 (多租户隔离红线)"
    )
    branch_id = Column(BigInteger, nullable=True, comment="所属片区 (级联配置查找链)")
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, comment="学生ID")
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=False, comment="班级ID")
    grade_id = Column(BigInteger, ForeignKey("grades.id"), nullable=False, comment="年级ID")

    survey_type = Column(
        String(40), nullable=False, comment="量表类型: MSSMHS-55 / SCL-90 / PHQ-9 / 自定义"
    )
    total_score = Column(Float, nullable=True, comment="量表总分 (原始分)")

    # JSON 字段: 逐题答案 + 10维标准分数
    answers_json = Column(JSON, nullable=True, comment="逐题答案 (题号->原始分值)")
    dimension_scores = Column(JSON, nullable=True, comment="10维标准分数 JSON (严格Key命名)")

    # 有效性 & 审核状态
    is_valid = Column(Boolean, default=True, comment="问卷有效性标记")
    verify_status = Column(
        String(20), default="PENDING", comment="审核状态: PENDING/VERIFIED/REJECTED"
    )
    verified_by = Column(BigInteger, ForeignKey("users.id"), nullable=True, comment="审核人ID")
    verified_at = Column(DateTime, nullable=True, comment="审核时间")
    completed_at = Column(DateTime, nullable=True, comment="问卷完成时间")

    # ETL 追溯
    source_id = Column(Integer, nullable=True, comment="旧库 grade7_new ETL溯源标记")

    # 时间戳 & 操作者
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)
    created_by = Column(BigInteger, nullable=True, comment="创建操作者ID")
    updated_by = Column(BigInteger, nullable=True, comment="最后更新操作者ID")

    # 关系
    student = relationship("core.models.Student", lazy="selectin")
    cls = relationship("core.models.Class", lazy="selectin")

    __table_args__ = (
        Index("idx_ps_school_student", "school_id", "student_id"),
        Index("idx_ps_school_class", "school_id", "class_id"),
        Index("idx_ps_survey_type", "school_id", "survey_type"),
        Index("idx_ps_completed_at", "school_id", "completed_at"),
        Index("idx_ps_verify_status", "school_id", "verify_status"),
        Index("idx_ps_source_id", "source_id"),
    )


class MentalHealthAssessment(Base, SchoolMixin):
    """心理健康评估结论表 — 承载 risk_level 判定与干预方案 (v3.1)

    ETL 血缘: 316条 (8 high / 42 medium / 266 low), source_id + source_survey_id 100% 关联
    """

    __tablename__ = "mental_health_assessments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    school_id = Column(
        BigInteger, ForeignKey("schools.id"), nullable=False, comment="所属学校 (多租户隔离红线)"
    )
    branch_id = Column(BigInteger, nullable=True, comment="所属片区")
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, comment="学生ID")
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=False, comment="班级ID")
    grade_id = Column(BigInteger, ForeignKey("grades.id"), nullable=False, comment="年级ID")

    # 评估元信息
    assessment_type = Column(
        String(30),
        nullable=False,
        comment="评估类型: screening/diagnostic/follow_up/cross_analysis",
    )
    assessment_date = Column(Date, nullable=True, comment="评估日期")
    scale_name = Column(
        String(100), nullable=True, comment="量表名称: MSSMHS-55 / SCL-90 / PHQ-9 / GAD-7"
    )

    # 评估结果
    total_score = Column(Integer, nullable=True, comment="量表总分 (原始分)")
    risk_level = Column(String(20), nullable=True, comment="风险等级: high/medium/low")
    dimension_scores = Column(
        JSON, nullable=True, comment="10维标准分数 (同 psych_surveys.dimension_scores Key 规范)"
    )

    # 结论 & 干预
    conclusion = Column(Text, nullable=True, comment="评估结论文本")
    recommendations = Column(Text, nullable=True, comment="建议干预措施文本")
    need_intervention = Column(Boolean, default=False, comment="是否需要干预 (0=否, 1=是)")
    intervention_plan = Column(Text, nullable=True, comment="干预方案文本")

    # 评估人 & 审核
    assessed_by = Column(BigInteger, ForeignKey("users.id"), nullable=False, comment="评估人ID")
    status = Column(
        String(20), default="DRAFT", comment="状态: DRAFT/PENDING_REVIEW/APPROVED/REVISED/ARCHIVED"
    )
    reviewed_by = Column(BigInteger, ForeignKey("users.id"), nullable=True, comment="审核人ID")
    reviewed_at = Column(DateTime, nullable=True, comment="审核时间")
    review_comment = Column(Text, nullable=True, comment="审核意见")

    # ETL 追溯
    source_id = Column(Integer, nullable=True, comment="旧库 grade7_new ETL溯源")
    source_survey_id = Column(
        BigInteger,
        ForeignKey("psych_surveys.id"),
        nullable=True,
        comment="关联 psych_surveys.id (评估从哪份问卷生成)",
    )

    # 时间戳 & 操作者
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)
    created_by = Column(BigInteger, nullable=True, comment="创建操作者ID")
    updated_by = Column(BigInteger, nullable=True, comment="最后更新操作者ID")

    # 关系
    student = relationship("core.models.Student", lazy="selectin")
    source_survey = relationship("PsychSurvey", lazy="selectin")

    __table_args__ = (
        Index("idx_mha_school_student", "school_id", "student_id"),
        Index("idx_mha_school_class", "school_id", "class_id"),
        Index("idx_mha_risk_level", "school_id", "risk_level"),
        Index("idx_mha_assessment_date", "school_id", "assessment_date"),
        Index("idx_mha_status", "school_id", "status"),
        Index("idx_mha_source_survey_id", "source_survey_id"),
        Index("idx_mha_source_id", "source_id"),
    )


class PsychCrossAnalysis(Base, SchoolMixin):
    """跨维度交叉分析表 — 心理x行为x成绩x考勤关联分析 (v3.1)

    ETL 血缘: 35条, source_id 100% 可追溯
    """

    __tablename__ = "psych_cross_analyses"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    school_id = Column(
        BigInteger, ForeignKey("schools.id"), nullable=False, comment="多租户隔离红线"
    )
    branch_id = Column(BigInteger, nullable=True, comment="所属片区")
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, comment="学生ID")
    class_id = Column(BigInteger, ForeignKey("classes.id"), nullable=False, comment="班级ID")
    grade_id = Column(BigInteger, ForeignKey("grades.id"), nullable=False, comment="年级ID")

    # 分析结果
    analysis_type = Column(
        String(30),
        nullable=False,
        comment="分析类型: psych_behavior_correlation/psych_score_correlation/psych_attendance_correlation/multi_dimension",
    )
    details_json = Column(JSON, nullable=True, comment="分析结果详情")

    # ETL 追溯
    source_id = Column(Integer, nullable=True, comment="旧库 ETL 溯源标记")

    # 时间戳
    created_at = Column(DateTime, default=get_local_now)

    # 关系
    student = relationship("core.models.Student", lazy="selectin")

    __table_args__ = (
        Index("idx_pca_school_student", "school_id", "student_id"),
        Index("idx_pca_analysis_type", "school_id", "analysis_type"),
    )
