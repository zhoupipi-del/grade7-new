"""
PolicyEngine Config — YAML 配置宪法加载器
policy.yaml 的完整 Pydantic 映射。启动时加载，类型错误立即暴露。
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

import yaml
from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────
# 枚举
# ─────────────────────────────────────────────────────────────


class Severity(str, Enum):
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class ApprovalMode(str, Enum):
    PARALLEL_OR = "parallel_or"
    SERIAL_AND = "serial_and"


class PolicyTag(str, Enum):
    REPAIRABLE = "repairable"
    NON_REPAIRABLE = "non_repairable"
    RECOVERED = "recovered"
    PERMANENT = "permanent"


class EscalationStrategy(str, Enum):
    AUTO_APPROVE = "auto_approve"
    ESCALATE = "escalate"


# ─────────────────────────────────────────────────────────────
# 1. 归一化配置
# ─────────────────────────────────────────────────────────────


class ShortWindowConfig(BaseModel):
    days: int = 30
    label: str = "短周期基准"
    purpose: str


class LongWindowConfig(BaseModel):
    start_anchor: Literal["semester_start", "school_year_start"]
    label: str = "长周期基准"
    purpose: str


class BaselineConfig(BaseModel):
    short_window: ShortWindowConfig
    long_window: LongWindowConfig


class WinsorizingConfig(BaseModel):
    enabled: bool = True
    clip_sigma: float = 2.0
    reference_window: Literal["short", "long"] = "long"


class SoftmaxConfig(BaseModel):
    temperature: float = 1.0
    min_samples_for_normalization: int = 10


class GrowthVectorConfig(BaseModel):
    enabled: bool = True
    comparison_window_days: int = 7


class SubDimensionConfig(BaseModel):
    code: str
    label: str
    weight: float = Field(ge=0, le=1)
    source_events: list[str]


class DimensionConfig(BaseModel):
    label: str
    weight: float = Field(ge=0, le=1)
    sub_dimensions: list[SubDimensionConfig]


class NormalizationConfig(BaseModel):
    dimensions: dict[str, DimensionConfig]
    baseline: BaselineConfig
    winsorizing: WinsorizingConfig
    softmax: SoftmaxConfig
    growth_vector: GrowthVectorConfig


# ─────────────────────────────────────────────────────────────
# 2. 审批路由配置
# ─────────────────────────────────────────────────────────────


class ApproverConfig(BaseModel):
    role: str
    label: str


class ChainNodeConfig(BaseModel):
    role: str
    label: str
    timeout_hours: int


class ApprovalRule(BaseModel):
    event_types: list[str]
    severity: Severity
    mode: ApprovalMode
    approvers: list[ApproverConfig] | None = None
    chain: list[ChainNodeConfig] | None = None
    auto_approve_if_creator: bool = False
    timeout_hours: int = 48
    escalation_on_timeout: EscalationStrategy | None = None


class DefaultRuleConfig(BaseModel):
    mode: ApprovalMode = ApprovalMode.PARALLEL_OR
    approvers: list[ApproverConfig]


class ApprovalRoutingConfig(BaseModel):
    rules: list[ApprovalRule]
    default_rule: DefaultRuleConfig


# ─────────────────────────────────────────────────────────────
# 3. 回血模型配置
# ─────────────────────────────────────────────────────────────


class PerSeverityConfig(BaseModel):
    recovery_enabled: bool
    tag_on_apply: PolicyTag
    tag_on_full_recovery: PolicyTag | None = None
    k_override: float | None = None
    min_observation_days_override: int | None = None


class RecoveryChannelConfig(BaseModel):
    code: str
    label: str
    trigger: str
    recovery_ratio: float | None = None
    streak_days: int | None = None
    min_streak: int | None = None


class RecoveryParameters(BaseModel):
    k: float = 0.5
    min_observation_days: int = 7
    max_recovery_ratio: float = 0.85
    half_life_indicator: int = 30


class RecoveryModelConfig(BaseModel):
    type: Literal["power_law", "exponential"] = "power_law"
    parameters: RecoveryParameters
    per_severity: dict[str, PerSeverityConfig]
    channels: list[RecoveryChannelConfig]


# ─────────────────────────────────────────────────────────────
# 4. 事件分类配置
# ─────────────────────────────────────────────────────────────


class BehaviorTypeConfig(BaseModel):
    severity: Severity
    dimension: str
    sub_dimension: str
    base_penalty: float
    weight_multiplier: float = 1.0


class EventClassificationConfig(BaseModel):
    behavior_types: dict[str, BehaviorTypeConfig]
    default_mapping: BehaviorTypeConfig


# ─────────────────────────────────────────────────────────────
# 根配置
# ─────────────────────────────────────────────────────────────


class PolicyConfig(BaseModel):
    version: str
    description: str
    normalization: NormalizationConfig
    approval_routing: ApprovalRoutingConfig
    recovery_model: RecoveryModelConfig
    event_classification: EventClassificationConfig

    @classmethod
    def from_yaml(cls, path: str) -> PolicyConfig:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data["policy_engine"])

    def to_yaml(self, path: str) -> None:
        import yaml

        out = {"policy_engine": self.model_dump(mode="json")}
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(out, f, allow_unicode=True, sort_keys=False)
