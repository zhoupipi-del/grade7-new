"""
PolicyEngine — 德育"数字宪法"核心解释器

Policy as Code: 改 YAML 即改政策，零代码变更。
启动注入：app.state.policy_engine = PolicyEngine.from_yaml("policy.yaml")
"""
from __future__ import annotations

import logging
from typing import Optional

from .config import PolicyConfig
from .models import (
    ApprovalChain,
    ClassificationResult,
    CohortStatistics,
    DESResult,
    RawScoreVector,
    RecoveryResult,
)
from .normalizer import NormalizationPipeline
from .recovery import RecoveryCalculator
from .router import ApprovalRouter

logger = logging.getLogger("policy_engine")


class PolicyEngine:
    """
    PolicyEngine 门面类 — 绑定三个子引擎。

    使用方式：
        engine = PolicyEngine.from_yaml("/path/to/policy.yaml")
        result = engine.normalizer.compute_des(...)
    """

    def __init__(
        self,
        config: PolicyConfig,
    ) -> None:
        self.config = config
        self.normalizer = NormalizationPipeline(config.normalization)
        self.router = ApprovalRouter(config.approval_routing)
        self.recovery = RecoveryCalculator(config.recovery_model)
        logger.info(
            "policy_engine.init",
            version=config.version,
            dimensions=list(config.normalization.dimensions.keys()),
        )

    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── /
    # 公开 API
    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── /

    def classify(self, behavior_type: str) -> ClassificationResult:
        """
        事件分类 — 将行为类型映射到维度/严重度/审批规则。

        参数：
          behavior_type: 行为类型代码（如 "fighting", "lateness"）

        返回：
          ClassificationResult（含 severity、dimension_code、approval_rule_index）
        """
        ec = self.config.event_classification
        bt_cfg = ec.behavior_types.get(behavior_type)

        if bt_cfg is None:
            logger.warning(
                "classify.unknown_behavior",
                behavior_type=behavior_type,
                fallback=True,
            )
            dm = ec.default_mapping
            return ClassificationResult(
                event_type=behavior_type,
                severity=dm.severity.value,
                dimension_code=dm.dimension,
                sub_dimension_code=dm.sub_dimension,
                base_penalty=dm.base_penalty,
                weight_multiplier=dm.weight_multiplier,
                approval_rule_index=-1,  # -1 表示使用默认规则
            )

        # 查找匹配的审批规则索引
        rule_idx = -1
        for i, rule in enumerate(self.config.approval_routing.rules):
            if behavior_type in rule.event_types:
                rule_idx = i
                break

        return ClassificationResult(
            event_type=behavior_type,
            severity=bt_cfg.severity.value,
            dimension_code=bt_cfg.dimension,
            sub_dimension_code=bt_cfg.sub_dimension,
            base_penalty=bt_cfg.base_penalty,
            weight_multiplier=bt_cfg.weight_multiplier,
            approval_rule_index=rule_idx,
        )

    def route(
        self,
        event_type: str,
        creator_role: str,
    ) -> ApprovalChain:
        """审批路由（委托给 self.router）"""
        return self.router.route(event_type, creator_role)

    def compute_des(
        self,
        student_id: int,
        raw_vectors: list[RawScoreVector],
        cohort_stats: dict[str, dict[str, CohortStatistics]],
        previous_snapshot: Optional[object] = None,
    ) -> DESResult:
        """计算 DES（委托给 self.normalizer）"""
        return self.normalizer.compute_des(
            student_id=student_id,
            raw_vectors=raw_vectors,
            cohort_stats=cohort_stats,
            previous_snapshot=previous_snapshot,
        )

    def compute_des_batch(
        self,
        raw_vectors_by_student: dict[int, list[RawScoreVector]],
        cohort_stats: dict[str, dict[str, CohortStatistics]],
        previous_snapshots: Optional[dict[int, object]] = None,
    ) -> dict[int, DESResult]:
        """批量计算 DES（委托给 self.normalizer）"""
        return self.normalizer.compute_des_batch(
            raw_vectors_by_student=raw_vectors_by_student,
            cohort_stats=cohort_stats,
            previous_snapshots=previous_snapshots,
        )

    def compute_recovery(
        self,
        penalty_amount: float,
        severity: str,
        days_elapsed: int,
        positive_streak_days: int = 0,
        is_revoked: bool = False,
    ) -> RecoveryResult:
        """计算回血（委托给 self.recovery）"""
        return self.recovery.compute_recovery(
            penalty_amount=penalty_amount,
            severity=severity,
            days_elapsed=days_elapsed,
            positive_streak_days=positive_streak_days,
            is_revoked=is_revoked,
        )

    def preview_recovery(
        self,
        penalty_amount: float,
        severity: str,
        max_days: int = 90,
    ) -> list[tuple[int, float, float]]:
        """预览回血曲线（委托给 self.recovery）"""
        return self.recovery.compute_recovery_preview(
            penalty_amount=penalty_amount,
            severity=severity,
            max_days=max_days,
        )

    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── /
    # 类方法：从 YAML 加载
    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── /

    @classmethod
    def from_yaml(cls, path: str) -> "PolicyEngine":
        """从 YAML 文件加载配置并创建 PolicyEngine"""
        config = PolicyConfig.from_yaml(path)
        logger.info("policy_engine.loaded", path=path, version=config.version)
        return cls(config)

    def reload_config(self, path: Optional[str] = None) -> None:
        """
        热重载配置（生产环境用）。
        注意：此方法会创建新的子引擎实例，正在进行的计算可能用旧配置。
        """
        path = path or getattr(self, "_config_path", None)
        if path is None:
            raise ValueError("No config path available for reload")
        new_config = PolicyConfig.from_yaml(path)
        self.__init__(new_config)
        self._config_path = path
        logger.info("policy_engine.reloaded", version=new_config.version)


# ── / ── / ── / ── / ── / ── / ── / ── / ── / ── /
# 便捷导出
# ── / ── / ── / ── / ── / ── / ── / ── / ── / ── /

__all__ = [
    "PolicyEngine",
    "PolicyConfig",
    "NormalizationPipeline",
    "ApprovalRouter",
    "RecoveryCalculator",
    "ClassificationResult",
    "DESResult",
    "RecoveryResult",
    "ApprovalChain",
    "RawScoreVector",
    "CohortStatistics",
]
