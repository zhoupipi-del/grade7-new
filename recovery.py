"""
PolicyEngine RecoveryCalculator — 幂律衰减回血计算器

三通道回血：
  通道 A（撤销）: 处分撤销 → 100% 回血
  通道 B（行为）: 连续正向行为 → 每 14 天 +5%
  通道 C（时间）: 幂律衰减 R(t) = 1/(1+t)^k

总指挥决策3：幂律衰减（非指数），k=0.5，长尾效应。
永不完全消除（max_recovery_ratio=0.85）。
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Optional

import logging

from .config import PolicyTag, RecoveryModelConfig, PerSeverityConfig
from .models import RecoveryResult, RecoveryBreakdown

logger = structlog.get_logger("policy_engine.recovery")


class RecoveryCalculator:
    """幂律衰减回血计算器 — 三通道综合"""

    def __init__(self, config: RecoveryModelConfig) -> None:
        self.config = config

    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──
    # 公开入口
    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──

    def compute_recovery(
        self,
        penalty_amount: float,
        severity: str,
        days_elapsed: int,
        positive_streak_days: int = 0,
        is_revoked: bool = False,
    ) -> RecoveryResult:
        """
        综合三通道计算回血。

        参数：
          penalty_amount:          原始扣分数
          severity:                处分等级（warning/serious_warn/demerit/probation/expulsion）
          days_elapsed:           距处分生效天数
          positive_streak_days:    连续正向行为天数
          is_revoked:             处分是否已撤销

        返回：
          RecoveryResult（含各通道回血明细）
        """
        sev_config = self._get_severity_config(severity)

        if not sev_config.recovery_enabled:
            logger.info(
                "recovery.disabled",
                severity=severity,
                tag=sev_config.tag_on_apply,
            )
            return RecoveryResult(
                original_penalty=penalty_amount,
                recovered_amount=0.0,
                remaining_penalty=penalty_amount,
                recovery_ratio=0.0,
                breakdown=RecoveryBreakdown(),
                new_policy_tag=sev_config.tag_on_apply,
            )

        # 通道 A: 撤销回血
        revocation = penalty_amount if is_revoked else 0.0

        # 通道 B: 行为回血
        behavioral = self._channel_behavioral(
            penalty_amount, positive_streak_days
        )

        # 通道 C: 时间回血（幂律衰减）
        temporal = self._channel_temporal(
            penalty_amount, days_elapsed, sev_config
        )

        total_recovered = revocation + behavioral + temporal
        max_recovery = penalty_amount * self.config.parameters.max_recovery_ratio
        total_recovered = min(total_recovered, max_recovery)

        remaining = penalty_amount - total_recovered
        new_tag = (
            sev_config.tag_on_full_recovery
            if total_recovered >= max_recovery - 0.01
            else sev_config.tag_on_apply
        )

        return RecoveryResult(
            original_penalty=penalty_amount,
            recovered_amount=total_recovered,
            remaining_penalty=remaining,
            recovery_ratio=total_recovered / penalty_amount if penalty_amount > 0 else 0.0,
            breakdown=RecoveryBreakdown(
                revocation=revocation,
                behavioral=behavioral,
                temporal=temporal,
            ),
            new_policy_tag=new_tag.value if isinstance(new_tag, PolicyTag) else new_tag,
        )

    def compute_recovery_preview(
        self,
        penalty_amount: float,
        severity: str,
        max_days: int = 90,
    ) -> list[tuple[int, float, float]]:
        """
        预览回血曲线（用于前端可视化）。

        返回：
          [(day, recovered_ratio, remaining_penalty), ...]
        """
        sev_config = self._get_severity_config(severity)
        if not sev_config.recovery_enabled:
            return [(d, 0.0, penalty_amount) for d in range(0, max_days + 1, 7)]

        k = sev_config.k_override or self.config.parameters.k
        min_days = sev_config.min_observation_days_override or self.config.parameters.min_observation_days

        curve = []
        for d in range(0, max_days + 1):
            if d < min_days:
                recovered = 0.0
            else:
                remaining_ratio = 1.0 / ((1.0 + d) ** k)
                recovered_ratio = 1.0 - remaining_ratio
                recovered = penalty_amount * min(recovered_ratio, self.config.parameters.max_recovery_ratio)
            remaining = penalty_amount - recovered
            curve.append((d, recovered / penalty_amount if penalty_amount > 0 else 0.0, remaining))
        return curve

    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──
    # 三通道计算
    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──

    def _channel_temporal(
        self,
        penalty: float,
        days: int,
        sev_config: PerSeverityConfig,
    ) -> float:
        """通道 C: 幂律时间衰减"""
        min_days = (
            sev_config.min_observation_days_override
            or self.config.parameters.min_observation_days
        )
        if days < min_days:
            return 0.0

        k = sev_config.k_override or self.config.parameters.k
        # R(t) = 1 / (1 + t)^k
        remaining_ratio = 1.0 / ((1.0 + days) ** k)
        recovered_ratio = 1.0 - remaining_ratio

        max_ratio = self.config.parameters.max_recovery_ratio
        return penalty * min(recovered_ratio, max_ratio)

    def _channel_behavioral(
        self,
        penalty: float,
        streak_days: int,
    ) -> float:
        """通道 B: 连续正向行为回血"""
        channel = next(
            (c for c in self.config.channels if c.code == "behavioral"),
            None,
        )
        if not channel or not channel.streak_days or channel.streak_days <= 0:
            return 0.0

        cycles = streak_days // channel.streak_days
        return penalty * cycles * (channel.recovery_ratio or 0.05)

    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──
    # 配置查询
    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──

    def _get_severity_config(self, severity: str) -> PerSeverityConfig:
        """获取处分等级的回血配置（含 fallback）"""
        cfg = self.config.per_severity.get(severity)
        if cfg is not None:
            return cfg

        # fallback: 尝试大小写兼容
        for key, val in self.config.per_severity.items():
            if key.lower() == severity.lower():
                return val

        # 最终 fallback: 不可回血
        logger.warning("recovery.severity_not_found", severity=severity, fallback="non_repairable")
        return PerSeverityConfig(
            recovery_enabled=False,
            tag_on_apply=PolicyTag.NON_REPAIR_ABLE,
        )
