"""
Data Adapter 数据模型

7 张核心表:
- ImportTask:                   数据导入任务记录
- ExamGradesDetail:             新高考成绩血缘明细(学生×学科×考试, 含赋分)
- StudentRiskAlert:             RDI 风险红灯预警流水
- StudentWeaknessPrescription:  AI 弱科诊断处方
- StudentSubjectSelection:      高中选科登记(3+1+2组合)
- StudentTeachingClassEnrollment: 走班多对多中间表
- ScalingRuleSet:               新高考等级赋分规则(A-E五级)
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
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)


class ImportTask(Base, SchoolMixin):
    """数据导入任务记录"""

    __tablename__ = "data_adapter_tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False, comment="上传文件名")
    status = Column(
        String(30),
        nullable=False,
        default="completed",
        comment="pending/processing/completed/completed_with_errors/failed",
    )
    phase = Column(
        String(20),
        nullable=False,
        comment="学段: primary/junior/senior/integrated",
    )
    template_code = Column(String(50), nullable=True, comment="使用的模板代号")
    total_rows = Column(Integer, default=0, comment="总行数")
    success_rows = Column(Integer, default=0, comment="成功行数")
    failed_rows = Column(Integer, default=0, comment="失败行数")
    skipped_rows = Column(Integer, default=0, comment="跳过行数(缺考等)")
    errors_summary = Column(JSON, nullable=True, comment="错误摘要(前20条)")
    sync_status = Column(
        String(20),
        nullable=False,
        default="native",
        comment="数据来源标记: native(原生)/legacy(旧系统迁移)/imported(批量导入)",
    )
    created_by = Column(BigInteger, nullable=True, comment="创建人 user_id")
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)


class ExamGradesDetail(Base, SchoolMixin):
    """
    新高考成绩血缘明细表

    每一行 = 一个学生 × 一个学科 × 一场考试
    再选科目 (化学/生物/政治/地理) 有 scaled_score;
    必考/首选科目 (语数英/物理/历史) scaled_score = NULL, 仅记录排名.
    """

    __tablename__ = "exam_grades_detail"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exam_id = Column(BigInteger, nullable=False, index=True, comment="大考ID")
    student_id = Column(BigInteger, nullable=False, index=True, comment="学生ID")
    admin_class_id = Column(BigInteger, nullable=False, index=True, comment="行政班ID")
    teaching_class_id = Column(BigInteger, nullable=True, comment="教学班ID(选科班, 高中走班启用)")
    subject_code = Column(
        String(20),
        nullable=False,
        index=True,
        comment="学科代码: chinese/math/english/physics/history/chemistry/biology/politics/geography",
    )
    raw_score = Column(Float, nullable=False, default=0.0, comment="原始分")
    scaled_score = Column(Float, nullable=True, comment="赋分(仅再选科目: 化学/生物/政治/地理)")
    is_absent = Column(Boolean, default=False, comment="是否缺考")
    cohort_rank = Column(Integer, nullable=True, comment="集团/全校排名")
    cohort_total = Column(Integer, nullable=True, comment="集团/全校有效参考人数")
    percentile = Column(Float, nullable=True, comment="百分比排位 0~1")
    grade_level = Column(String(2), nullable=True, comment="等级 A/B/C/D/E (仅再选科目)")
    created_at = Column(DateTime, default=get_local_now)


class StudentRiskAlert(Base, SchoolMixin):
    """
    学生风险红灯预警流水表

    当 RDI 引擎检测到学生学业/行为/考勤触发预警时,
    在此表落盘一条记录, lineage_graph 字段保存 3 层血缘有向无环图快照:
      - Layer 1 (Risk):        风险洞察层 — 预警类型/等级/触发条件
      - Layer 2 (Aggregation): 多维聚合层 — Z-Score / 排名 / 赋分等中间体
      - Layer 3 (Source):      异构数据源层 — 原始上传 task_id / 班级 / Excel 快照
    """

    __tablename__ = "student_risk_alerts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(Integer, nullable=False, index=True, comment="学生ID")
    exam_id = Column(Integer, nullable=False, index=True, comment="引发预警的目标大考ID")
    risk_type = Column(String(32), nullable=False, comment="风险分类: academic/behavior/attendance")
    risk_level = Column(String(16), nullable=False, comment="风险等级: red(红灯)/yellow(黄灯)")
    trigger_reason = Column(String(512), nullable=False, comment="核心触发原因摘要")
    lineage_graph = Column(JSON, nullable=False, comment="RDI 跨周期血缘有向图 JSON 结构")
    status = Column(
        String(16), nullable=False, default="active", comment="处理状态: active/resolved/ignored"
    )
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)


class StudentWeaknessPrescription(Base, SchoolMixin):
    """
    AI 智能定向弱科诊断与学业处方表

    关联 StudentRiskAlert (alert_id 可空, 支持主动诊断).
    保存大模型生成的根源薄弱点诊断报告 + 针对性提升行动处方,
    同时镜像核心指标 (raw_score / scaled_score / z_score) 防止源数据变动后处方失去锚点.
    """

    __tablename__ = "student_weakness_prescriptions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    alert_id = Column(BigInteger, nullable=True, index=True, comment="关联的风险预警ID(可为空)")
    student_id = Column(Integer, nullable=False, index=True, comment="学生ID")
    subject_code = Column(String(32), nullable=False, comment="诊断的目标学科")
    raw_score = Column(Numeric(5, 2), nullable=True, comment="原始分镜像")
    scaled_score = Column(Numeric(5, 2), nullable=True, comment="赋分镜像")
    z_score = Column(Numeric(4, 2), nullable=False, comment="确诊时的核心标尺 Z-Score")
    weakness_analysis = Column(Text, nullable=False, comment="AI 生成的根源薄弱点诊断报告")
    action_prescription = Column(Text, nullable=False, comment="AI 针对性开具的提升行动处方")
    model_metadata = Column(
        JSON, nullable=True, comment='大模型版本与代币元数据 {"model":"deepseek-v4","tokens":1240}'
    )
    created_at = Column(DateTime, default=get_local_now)


# ═══════════════════════════════════════════════════════════════════════
# 高中新高考 3+1+2 走班制 + 选科赋分 血缘扩展模型
# ═══════════════════════════════════════════════════════════════════════


class StudentSubjectSelection(Base, SchoolMixin):
    """
    高中生选科登记表 — 3+1+2 新高考组合

    每个学生在特定学期登记:
      首选1科 (physics 或 history)
      再选2科 (chemistry/biology/politics/geography 中选2)

    is_active=True 标记当前生效选科组合，
    每学期每学生仅允许1条 active 记录。
    """

    __tablename__ = "student_subject_selections"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(
        BigInteger, nullable=False, index=True, comment="学生ID(逻辑FK→students.id)"
    )
    preferred_subject = Column(String(20), nullable=False, comment="首选科目代码: physics/history")
    elective_subjects = Column(
        JSON, nullable=False, comment='再选2科代码数组 ["chemistry","biology"]'
    )
    semester = Column(String(20), nullable=False, comment="生效学期(如 2025-1)")
    is_active = Column(
        Boolean, nullable=False, default=True, comment="是否当前生效(每学期每学生仅1条active)"
    )
    confirmed_at = Column(DateTime, nullable=True, comment="选科确认时间")
    confirmed_by = Column(BigInteger, nullable=True, comment="确认人 user_id")
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        UniqueConstraint(
            "school_id", "student_id", "semester", name="uk_student_selection_semester"
        ),
        Index("idx_selection_school", "school_id"),
        Index("idx_selection_student", "student_id"),
        Index("idx_selection_active", "school_id", "is_active", "semester"),
    )


class StudentTeachingClassEnrollment(Base, SchoolMixin):
    """
    走班多对多中间表 — 学生 × 教学班 × 学科 × 学期

    高中走班制下一个学生可同时属于多个教学班:
      学生A → 教学班"物化生组合"(物理) + 教学班"物化生组合"(化学) + ...

    teaching_class_id 关联到 classes 表中 class_type='teaching' 的记录。
    Student.class_id 仍指向行政班(class_type='administrative')，本表实现学科维度的走班关联。
    """

    __tablename__ = "student_teaching_class_enrollments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, nullable=False, comment="学生ID(逻辑FK→students.id)")
    teaching_class_id = Column(
        BigInteger, nullable=False, comment="教学班ID(逻辑FK→classes.id, class_type=teaching)"
    )
    subject_code = Column(String(20), nullable=False, comment="该教学班对应的学科代码")
    semester = Column(String(20), nullable=False, comment="学期标识(如 2025-1)")
    is_active = Column(Boolean, nullable=False, default=True, comment="是否当前生效")
    created_at = Column(DateTime, default=get_local_now)

    __table_args__ = (
        UniqueConstraint(
            "school_id",
            "student_id",
            "teaching_class_id",
            "semester",
            name="uk_enrollment_student_class_semester",
        ),
        Index("idx_enrollment_school", "school_id"),
        Index("idx_enrollment_student", "student_id", "is_active"),
        Index("idx_enrollment_class", "teaching_class_id", "semester"),
        Index("idx_enrollment_subject", "school_id", "subject_code", "semester"),
    )


class ScalingRuleSet(Base, SchoolMixin):
    """
    新高考等级赋分规则配置表

    按 rank percentile → A-E 五级线性映射:
      A: 前15%   → 100-86
      B: 16%-50% → 85-71
      C: 51%-84% → 70-56
      D: 85%-97% → 55-41
      E: 98%-100% → 40-30

    允许不同省份/年份使用不同规则集，is_active+effective_from 管理生效时间。
    rule_entries 为 JSON 数组，每项含: level/pct_start/pct_end/score_start/score_end
    """

    __tablename__ = "scaling_rule_sets"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="规则集名称(如 '湖南省2025新高考赋分')")
    province_code = Column(String(10), nullable=True, comment="省份代码(如 '43' 湖南)")
    grade_levels = Column(
        JSON, nullable=True, comment='适用年级层级数组 ["senior_1","senior_2","senior_3"]'
    )
    rule_entries = Column(
        JSON,
        nullable=False,
        comment='赋分等级规则数组 [{"level":"A","pct_start":0,"pct_end":15,"score_start":100,"score_end":86},...]',
    )
    is_active = Column(Boolean, nullable=False, default=True, comment="是否当前生效")
    effective_from = Column(Date, nullable=False, comment="生效起始日期")
    effective_until = Column(Date, nullable=True, comment="生效截止日期(NULL=永久)")
    created_by = Column(BigInteger, nullable=True, comment="创建人 user_id")
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        Index("idx_scaling_school", "school_id"),
        Index("idx_scaling_active", "school_id", "is_active", "effective_from"),
    )
