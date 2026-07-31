"""
modules/evaluation/models.py — 素质评价引擎数据模型

事件驱动 CQRS 架构：
  - EvaluationIndicator: 指标树（一级维度 + 二级评分项）
  - EvaluationScore:   单次评分记录（写模型 — 事件源）
  - StudentScore:       学生当前总分快照（读模型 — 预计算）
  - ScoreLog:           评分流水审计（事件溯源）
  - EvaluationRule:     评分规则配置（多租户隔离）

写入路径: 违纪扣分/手动评分 → EvaluationScore + ScoreLog → 重算 StudentScore
读取路径: 查询排名/仪表盘 → 直接读 StudentScore（0.1ms，无需实时聚合）
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, Float, DateTime, Date,
    ForeignKey, JSON, Text, Index,
)
from sqlalchemy.orm import relationship
from core.models import Base, SchoolMixin, get_local_now


# ═══════════════════════════════════════════════════════════════
# 1. 评分规则配置（每学校独立）
# ═══════════════════════════════════════════════════════════════

class EvaluationRule(Base, SchoolMixin):
    """多租户评分规则 — 每学校可定制五育权重、平衡惩罚、违纪扣分映射"""
    __tablename__ = "evaluation_rules"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # 五育维度权重 — JSON: {"moral": 0.25, "academic": 0.25, "health": 0.20, "art": 0.15, "social": 0.15}
    dimension_weights = Column(JSON, nullable=False, default=lambda: {
        "moral": 0.25, "academic": 0.25, "health": 0.20, "art": 0.15, "social": 0.15,
    })

    # 平衡补偿参数 — 防止"一维独大"
    balance_threshold = Column(Float, default=1.5)   # 某维度分 > 其他均值 × 1.5 → 触发惩罚
    balance_penalty = Column(Float, default=0.85)     # 惩罚系数（乘以此值）

    # 违纪扣分映射 — JSON: {"warning": 1, "minor": 3, "major": 5, "serious": 10}
    deduction_map = Column(JSON, nullable=False, default=lambda: {
        "warning": 1, "minor": 3, "major": 5, "serious": 10,
    })

    # 基础分（每人起始分）
    base_score = Column(Float, default=100.0)

    max_score = Column(Float, default=100.0)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)


# ═══════════════════════════════════════════════════════════════
# 2. 评价指标树（五维 + 二级评分项）
# ═══════════════════════════════════════════════════════════════

class EvaluationIndicator(Base, SchoolMixin):
    """评价指标 — 一级维度（parent_id=0） + 二级评分项（parent_id>0）"""
    __tablename__ = "evaluation_indicators"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    parent_id = Column(BigInteger, default=0, index=True)          # 0=一级维度, >0=二级指标
    dimension = Column(String(30), nullable=True, index=True)      # 维度标识: moral/academic/health/art/social
    weight = Column(Float, default=0.0)                            # 权重（二级指标在其一级维度的权重）
    max_score = Column(Float, default=100.0)                       # 满分值
    sort_order = Column(Integer, default=0)                        # 排序
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=get_local_now)

    __table_args__ = (
        Index("idx_ei_dim_active", "school_id", "dimension", "is_active"),
    )


# ═══════════════════════════════════════════════════════════════
# 3. 单次评分记录（事件源 — 不可变）
# ═══════════════════════════════════════════════════════════════

class EvaluationScore(Base, SchoolMixin):
    """单次评分记录 — 事件源，写入后不可更改（如需修正通过 ScoreLog 反查）"""
    __tablename__ = "evaluation_scores"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True)
    class_id = Column(BigInteger, nullable=False)
    grade_id = Column(BigInteger, nullable=False)
    indicator_id = Column(BigInteger, ForeignKey("evaluation_indicators.id"), nullable=False)
    score = Column(Float, default=0.0)
    scorer_type = Column(String(20), nullable=False)               # teacher/self/peer/parent/system
    scorer_id = Column(BigInteger, nullable=False)
    semester = Column(String(20), nullable=False)
    comment = Column(Text, default="")
    created_at = Column(DateTime, default=get_local_now)

    # 关系
    indicator = relationship("EvaluationIndicator", lazy="selectin")
    student = relationship("core.models.Student", lazy="selectin")

    __table_args__ = (
        Index("idx_es_stu_sem", "student_id", "semester"),
        Index("idx_es_ind_sem", "indicator_id", "semester"),
    )


# ═══════════════════════════════════════════════════════════════
# 4. 学生当前总分快照（读模型 — CQRS 查询侧）
# ═══════════════════════════════════════════════════════════════

class StudentScore(Base, SchoolMixin):
    """
    学生当前总分快照 — 事件驱动预计算，查询端直接读取。

    写入触发时机：
      - 新增 EvaluationScore → 异步/同步重算本学生维度分和总分
      - 违纪扣分 → 从 moral 维度减去对应值

    五维分 + 加权总分，一条 SELECT 出结果，0.1ms 级别。
    """
    __tablename__ = "student_scores"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True)
    class_id = Column(BigInteger, nullable=False)
    grade_id = Column(BigInteger, nullable=False)
    semester = Column(String(20), nullable=False)

    # 五育维度分（已平衡补偿）
    moral_score = Column(Float, default=0.0)
    academic_score = Column(Float, default=0.0)
    health_score = Column(Float, default=0.0)
    art_score = Column(Float, default=0.0)
    social_score = Column(Float, default=0.0)

    # 加权总分
    total_score = Column(Float, default=0.0, index=True)

    # 基础分（通常从 EvaluationRule.base_score 取值）
    base_score = Column(Float, default=100.0)

    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    # 关系
    student = relationship("core.models.Student", lazy="selectin")

    __table_args__ = (
        Index("idx_ss_stu_sem", "student_id", "semester", unique=True),
        Index("idx_ss_class_sem", "class_id", "semester"),
        Index("idx_ss_grade_sem", "grade_id", "semester"),
    )


# ═══════════════════════════════════════════════════════════════
# 5. 评分流水审计（事件溯源）
# ═══════════════════════════════════════════════════════════════

class ScoreLog(Base, SchoolMixin):
    """
    评分流水 — 每次分数变更的完整溯源（#1193 数据血缘增强版）。

    家长质疑"为什么扣了 3 分" → 一条 ScoreLog 精确回溯：
      谁扣的、为什么扣、扣之前多少分、扣之后多少分、关联的违纪记录 ID

    #1193 新增字段:
      - actor_id: 实际操作者（与 created_by 区分，created_by 可能是委托者）
      - source_ip: 操作来源 IP（支持 IPv6，用于审计合规）
      - trace_context_id: 血缘追踪上下文 ID（关联 LineageEvent.trace_id）
      - diff_snapshot: 变更前后 JSON 对比快照（家长可精确看到"扣了哪项"）
    """
    __tablename__ = "score_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True)
    dimension = Column(String(30), nullable=True)                   # 影响维度: moral/academic/...
    change_amount = Column(Float, nullable=False)                   # 变化量（正=加分，负=扣分）
    before_score = Column(Float, nullable=False)                    # 变动前总分
    after_score = Column(Float, nullable=False)                     # 变动后总分
    reason = Column(String(200), nullable=False)                    # 原因简述
    source_type = Column(String(20), nullable=False)                # behavior/manual/appeal/auto
    source_id = Column(BigInteger, nullable=True)                   # 关联源 ID（违纪记录 ID / 申诉 ID）
    policy_tag = Column(String(20), default="repairable")           # PolicyEngine 标签: repairable/non_repairable/recovered/permanent
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=get_local_now)

    # ── #1193 血缘增强字段 ──
    actor_id = Column(BigInteger, nullable=True, comment="实际操作者（与 created_by 区分，支持委托场景）")
    source_ip = Column(String(45), nullable=True, comment="操作来源 IP（IPv4/IPv6，审计合规）")
    trace_context_id = Column(String(36), nullable=True, index=True, comment="血缘追踪上下文 ID（关联 LineageEvent.trace_id）")
    diff_snapshot = Column(JSON, nullable=True, comment="变更前后 JSON 对比快照 {before:{...}, after:{...}}")

    # 关系
    student = relationship("core.models.Student", lazy="selectin")

    __table_args__ = (
        Index("idx_sl_stu_time", "student_id", "created_at"),
        Index("idx_sl_source", "source_type", "source_id"),
        Index("idx_sl_policy_tag", "student_id", "policy_tag"),
        Index("idx_sl_trace_context", "trace_context_id"),
    )


# ═══════════════════════════════════════════════════════════════
# 6. 审批工单（PolicyEngine 路由产物 — 分层审批状态机）
# ═══════════════════════════════════════════════════════════════

class ApprovalRequest(Base, SchoolMixin):
    """
    审批工单 — PolicyEngine.router 产出的审批链实例。

    每当 BehaviorService.create_record() 或 DisciplineService 触发事件，
    PolicyEngine.route() 返回 ApprovalChain，系统据此创建工单：

      parallel_or  (日常违纪): 班主任 + 年级组长 并行审批，48h 超时
      serial_and   (严重违纪): 班主任 → 年级组长 → 德育处 串行审批，144h 超时
      serial_and_escalate (临界处分): 4 级串行 + 教务升级，156h 超时
    """
    __tablename__ = "approval_requests"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True)

    # 事件来源
    event_type = Column(String(50), nullable=False)                 # 行为类型: fighting/smoking/lateness/...
    source_type = Column(String(20), nullable=False)                # behavior/attendance/discipline
    source_id = Column(BigInteger, nullable=False)                  # 源记录 ID

    # PolicyEngine 分类结果
    severity = Column(String(20), nullable=False)                   # minor/major/critical
    approval_mode = Column(String(20), nullable=False)              # parallel_or/serial_and/serial_and_escalate

    # 审批链快照（JSON: [{role, status, approver_id, approved_at, comment}, ...]）
    chain_config = Column(JSON, nullable=False)
    current_status = Column(String(20), default="pending")          # pending/approved/rejected/timeout/cancelled
    current_step = Column(Integer, default=0)                       # 当前审批步骤索引

    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_ar_school_status", "school_id", "current_status"),
        Index("idx_ar_student", "student_id"),
        Index("idx_ar_source", "source_type", "source_id"),
    )


# ═══════════════════════════════════════════════════════════════
# 7. 回血状态追踪（PolicyEngine.recovery 运行态）
# ═══════════════════════════════════════════════════════════════

class RecoveryState(Base, SchoolMixin):
    """
    回血状态追踪 — PolicyEngine.recovery 的持久化运行态。

    幂律衰减模型: R(t) = 1 / (1 + t)^k
      k=0.5 → warning  (7天观察期, 最高回血 85%)
      k=0.7 → serious  (14天观察期, 最高回血 85%)
      k=1.0 → demerit  (28天观察期, 最高回血 85%)
      non_repairable → PROBATION/EXPULSION (不回血)

    三通道回血:
      A-撤销回血: 处分撤销 → recovered_amount = 100%
      B-行为回血: 连续无违纪 14 天 → +5% 增量
      C-时间回血: 幂律衰减自动计算
    """
    __tablename__ = "recovery_state"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True)

    # 来源
    source_type = Column(String(20), nullable=False)                # behavior/discipline
    source_id = Column(BigInteger, nullable=False)                  # 违纪 ID / 处分 ID

    # 回血参数
    severity = Column(String(20), nullable=False)                   # minor/major/critical
    original_penalty = Column(Float, nullable=False)                # 原始扣分量
    recovered_amount = Column(Float, default=0.0)                   # 已回血量
    remaining_penalty = Column(Float, nullable=False)               # 剩余扣分量
    recovery_ratio = Column(Float, default=0.0)                     # 回血比例 = recovered / original

    # PolicyEngine 标签
    policy_tag = Column(String(20), default="repairable")           # repairable/non_repairable/recovered/permanent

    # 观察期
    observation_start = Column(Date, nullable=False)                # 观察期开始日期
    observation_end = Column(Date, nullable=False)                  # 观察期结束日期
    last_computed_at = Column(DateTime, nullable=True)              # 最后计算时间

    is_active = Column(Boolean, default=True)                       # 是否仍在追踪中
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        Index("idx_rs_student_active", "student_id", "is_active"),
        Index("idx_rs_source", "source_type", "source_id"),
    )
