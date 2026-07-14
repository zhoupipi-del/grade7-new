"""
PolicyEngine Models — 运行时数据载体
YAML 配置是"宪法"，这些是"运行时状态"。
PolicyEngine 本身无状态，所有中间态由调用方传入。
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel

# ──────────────────────────────────────────────────────────────
# 1. 归一化管道 — 输入/输出
# ──────────────────────────────────────────────────────────────


class RawScoreVector(BaseModel):
    """原始特征向量 — 归一化管道的输入"""

    student_id: int
    dimension_code: str
    sub_scores: dict[str, float]  # {sub_dim_code: raw_value}
    snapshot_date: date


class CohortStatistics(BaseModel):
    """群组统计量 — 双模态基准的数据载体"""

    dimension_code: str
    sub_dimension_code: str
    # 短周期（近30天）
    short_mu: float
    short_sigma: float
    short_n: int
    # 长周期（学期至今）
    long_mu: float
    long_sigma: float
    long_n: int
    # Winsorized 裁剪边界（派生字段，加载后计算）
    clip_lower: float | None = None  # μ_long − clip_sigma × σ_long
    clip_upper: float | None = None  # μ_long + clip_sigma × σ_long


class DimensionResult(BaseModel):
    """单维度评价结果"""

    dimension_code: str
    dimension_label: str
    raw_weighted: float  # 原始加权分
    z_score: float  # Z-Score（经 Winsorized 裁剪）
    softmax_score: float  # Softmax 归一化分
    weighted_score: float  # w_d × softmax_score
    growth_vector: float | None = None  # Δz 增长向量
    percentile: float  # 百分位排名 [0, 1]


class GrowthSummary(BaseModel):
    overall_delta_z: float
    dimension_deltas: dict[str, float]
    trend: Literal["improving", "stable", "declining"]


class DESResult(BaseModel):
    """无因次评价总分 (Dimensionless Evaluation Score)"""

    student_id: int
    des: float  # Σ w_d × softmax_score
    dimensions: dict[str, DimensionResult]
    growth_summary: GrowthSummary | None = None
    computed_at: datetime


# ──────────────────────────────────────────────────────────────
# 2. 审批路由 — 输入/输出
# ──────────────────────────────────────────────────────────────


class ApprovalNode(BaseModel):
    role: str
    label: str
    timeout_hours: int
    status: Literal["pending", "approved", "rejected"] = "pending"


class ApprovalChain(BaseModel):
    """审批链 — ApprovalRouter 的输出"""

    event_type: str
    mode: str  # "parallel_or" | "serial_and"
    nodes: list[ApprovalNode]
    escalation_strategy: str | None = None
    total_timeout_hours: int | None = None


class ApprovalAction(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    TIMEOUT = "timeout"


# ──────────────────────────────────────────────────────────────
# 3. 回血计算器 — 输入/输出
# ──────────────────────────────────────────────────────────────


class RecoveryBreakdown(BaseModel):
    revocation: float = 0.0
    behavioral: float = 0.0
    temporal: float = 0.0


class RecoveryResult(BaseModel):
    """回血计算结果"""

    original_penalty: float
    recovered_amount: float
    remaining_penalty: float
    recovery_ratio: float  # 0.0 ~ max_recovery_ratio
    breakdown: RecoveryBreakdown
    new_policy_tag: str


# ──────────────────────────────────────────────────────────────
# 4. 事件分类 — 输出
# ──────────────────────────────────────────────────────────────


class ClassificationResult(BaseModel):
    """事件分类结果"""

    event_type: str
    severity: str
    dimension_code: str
    sub_dimension_code: str
    base_penalty: float
    weight_multiplier: float
    approval_rule_index: int  # 匹配到的审批规则索引


# ──────────────────────────────────────────────────────────────
# 5. 快照模型（用于 score_snapshots 表）
# ──────────────────────────────────────────────────────────────


class ScoreSnapshot(BaseModel):
    """DES 每日快照 — 用于增长向量计算"""

    id: int | None = None
    student_id: int
    snapshot_date: date
    des: float
    dimension_z_scores: dict[str, float]  # {dim_code: z_score}
    raw_features: dict[str, float]  # {dim_code: raw_weighted}
    population_stats: dict[str, dict[str, float]]  # {dim_code: {mu, sigma, n}}
    created_at: datetime | None = None

    class Config:
        from_attributes = True
