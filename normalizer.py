"""
PolicyEngine NormalizationPipeline — 5 步无因次评价

管道：
  Raw Features → Z-Score(μ_short/σ_short) → Winsorized(μ_long±2σ_long)
  → Softmax → DES(Σ w_d × a_i) → Growth Δz

双模态基准（总指挥决策1）：
  短周期（30天）作为 z-score 分母，捕捉阶段性冲刺
  长周期（学期初）作为 Winsorized 裁剪边界参考，拉平极端个体影响
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Optional

import logging

from .config import NormalizationConfig, PolicyConfig
from .models import (
    CohortStatistics,
    DESResult,
    DimensionResult,
    GrowthSummary,
    RawScoreVector,
    ScoreSnapshot,
)

logger = logging.getLogger("policy_engine.normalizer")


class NormalizationPipeline:
    """5 步归一化管道 — 纯函数式，无状态"""

    def __init__(self, config: NormalizationConfig) -> None:
        self.config = config

    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──
    # 公开入口
    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──

    def compute_des(
        self,
        student_id: int,
        raw_vectors: list[RawScoreVector],
        cohort_stats: dict[str, dict[str, CohortStatistics]],
        previous_snapshot: Optional[ScoreSnapshot] = None,
    ) -> DESResult:
        """
        计算单学生的 DES（无因次评价总分）。

        参数：
          raw_vectors:      该学生的各维度原始特征向量
          cohort_stats:      {dim_code: {sub_dim_code: CohortStatistics}}
          previous_snapshot: 上一次快照（用于计算 Δz 增长向量）

        返回：
          DESResult（含各维度结果 + 增长摘要）
        """
        dim_results: dict[str, DimensionResult] = {}
        prev_z_scores: Optional[dict[str, float]] = (
            previous_snapshot.dimension_z_scores if previous_snapshot else None
        )

        for raw in raw_vectors:
            dim_code = raw.dimension_code
            dim_cfg = self.config.dimensions[dim_code]

            # Step 1: 原始特征聚合
            raw_weighted = self._step1_aggregate_raw(raw, dim_cfg)

            # 获取该维度的群组统计量
            dim_cohort = cohort_stats.get(dim_code, {})

            # Step 2-4: Z-Score → Winsorized → Softmax
            z_score = self._step2_dual_modal_zscore(
                raw_weighted, dim_cohort
            )
            z_prime = self._step3_winsorize(z_score, dim_cohort)
            # Softmax 需要整个群组都计算完才能做，先存 z_prime
            dim_results[dim_code] = DimensionResult(
                dimension_code=dim_code,
                dimension_label=dim_cfg.label,
                raw_weighted=raw_weighted,
                z_score=z_prime,          # 暂存 z_prime，后面转 softmax
                softmax_score=0.0,         # placeholder
                weighted_score=0.0,
                percentile=0.0,
            )

        # ── Softmax 归一化（需全群组 z_prime 才能算）──
        # 注意：此处为单学生演示，批量计算时需在外层聚合全群组 z_prime
        # 这里先做单学生线性归一化作为降级方案
        z_primes = [r.z_score for r in dim_results.values()]
        if len(z_primes) >= 2:
            # 多维度时做 Softmax
            softmax_scores = self._step4_softmax(z_primes)
            for i, (dim_code, r) in enumerate(dim_results.items()):
                r.softmax_score = softmax_scores[i]
                r.weighted_score = self.config.dimensions[dim_code].weight * r.softmax_score
        else:
            # 单维度时跳过 Softmax
            for dim_code, r in dim_results.items():
                r.softmax_score = 0.5
                r.weighted_score = self.config.dimensions[dim_code].weight * 0.5

        # Step 5: 综合 DES + 增长向量
        des, growth = self._step5_final_des(dim_results, prev_z_scores)

        return DESResult(
            student_id=student_id,
            des=des,
            dimensions=dim_results,
            growth_summary=growth,
            computed_at=datetime.utcnow(),
        )

    def compute_des_batch(
        self,
        raw_vectors_by_student: dict[int, list[RawScoreVector]],
        cohort_stats: dict[str, dict[str, CohortStatistics]],
        previous_snapshots: Optional[dict[int, ScoreSnapshot]] = None,
    ) -> dict[int, DESResult]:
        """
        批量计算 — 支持 Softmax 跨学生归一化。

        这是生产环境推荐使用的入口（单学生接口无法正确计算 Softmax）。
        """
        previous_snapshots = previous_snapshots or {}
        results: dict[int, DESResult] = {}

        # 第一遍：收集所有学生的 z_prime
        all_z_primes: dict[str, list[tuple[int, float]]] = {}  # {dim_code: [(student_id, z_prime)]}
        all_dim_results: dict[int, dict[str, DimensionResult]] = {}

        for student_id, vectors in raw_vectors_by_student.items():
            all_dim_results[student_id] = {}
            for raw in vectors:
                dim_code = raw.dimension_code
                dim_cfg = self.config.dimensions[dim_code]
                raw_weighted = self._step1_aggregate_raw(raw, dim_cfg)
                dim_cohort = cohort_stats.get(dim_code, {})
                z_score = self._step2_dual_modal_zscore(raw_weighted, dim_cohort)
                z_prime = self._step3_winsorize(z_score, dim_cohort)

                r = DimensionResult(
                    dimension_code=dim_code,
                    dimension_label=dim_cfg.label,
                    raw_weighted=raw_weighted,
                    z_score=z_prime,
                    softmax_score=0.0,
                    weighted_score=0.0,
                    percentile=0.0,
                )
                all_dim_results[student_id][dim_code] = r
                all_z_primes.setdefault(dim_code, []).append((student_id, z_prime))

        # 第二遍：跨学生 Softmax
        for dim_code, entries in all_z_primes.items():
            z_primes = [z for _, z in entries]
            sids = [s for s, _ in entries]

            if len(z_primes) >= self.config.softmax.min_samples_for_normalization:
                softmax_scores = self._step4_softmax(z_primes)
            else:
                # 样本不足，退化为线性归一化
                z_min, z_max = min(z_primes), max(z_primes)
                span = z_max - z_min if z_max != z_min else 1.0
                softmax_scores = [(z - z_min) / span for z in z_primes]

            for sid, score in zip(sids, softmax_scores):
                r = all_dim_results[sid][dim_code]
                r.softmax_score = score
                r.weighted_score = self.config.dimensions[dim_code].weight * score

        # 第三遍：综合 DES + 增长向量
        for student_id, dim_results in all_dim_results.items():
            prev = previous_snapshots.get(student_id)
            prev_z = prev.dimension_z_scores if prev else None
            des, growth = self._step5_final_des(dim_results, prev_z)
            results[student_id] = DESResult(
                student_id=student_id,
                des=des,
                dimensions=dim_results,
                growth_summary=growth,
                computed_at=datetime.utcnow(),
            )

        return results

    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──
    # Step 1: 原始特征聚合
    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──

    def _step1_aggregate_raw(
        self,
        raw: RawScoreVector,
        dim_cfg: DimensionConfig,      # type: ignore[name-defined]
    ) -> float:
        """
        π_raw(d, s) = Σ_j w_sub(j) × r(s, j)

        其中：
          d     = 维度代码（如 discipline）
          s     = 学生 ID
          w_sub = 子维度权重（来自 YAML）
          r     = 该子维度的原始累计值
        """
        total = 0.0
        for sub in dim_cfg.sub_dimensions:
            raw_val = raw.sub_scores.get(sub.code, 0.0)
            total += sub.weight * raw_val
        return total

    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──
    # Step 2: 双模态 Z-Score
    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──

    def _step2_dual_modal_zscore(
        self,
        raw_score: float,
        cohort: dict[str, CohortStatistics],
    ) -> float:
        """
        z = (x − μ_short) / σ_short

        关键：使用短周期的 μ 和 σ 计算 z-score，
        使 z 值对近期行为变化高度敏感。
        """
        # 取该维度第一个子维度的统计量（代表维度级统计量）
        first_sub = next(iter(cohort.values()), None)
        if first_sub is None:
            return 0.0
        if first_sub.short_sigma < 0.001:
            return 0.0  # 群组内无方差时退化为零
        return (raw_score - first_sub.short_mu) / first_sub.short_sigma

    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──
    # Step 3: Winsorized 裁剪
    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──

    def _step3_winsorize(
        self,
        z_score: float,
        cohort: dict[str, CohortStatistics],
    ) -> float:
        """
        使用长周期基准的 σ 做裁剪。

        clip_upper = μ_long + clip_sigma × σ_long
        clip_lower = μ_long − clip_sigma × σ_long

        裁剪后的 z' 映射到 [−2, +2] 附近，
        防止一个打架事件把整个班级的分布打散。
        """
        if not self.config.winsorizing.enabled:
            return z_score

        sigma = self.config.winsorizing.clip_sigma  # 2.0

        # 取该维度第一个子维度做裁剪参考
        first_sub = next(iter(cohort.values()), None)
        if first_sub is None or first_sub.long_sigma < 0.001:
            return z_score

        # z_score 本身是 (x - mu_short) / sigma_short 的结果
        # 要映射到长周期的裁剪边界，需要反向映射：
        #   x = z_score * sigma_short + mu_short
        #   z_long = (x - mu_long) / sigma_long
        #   z_clipped = clip(z_long, -sigma, +sigma)
        #   z_prime = z_clipped  （作为最终 z' 输出）
        mu_s = first_sub.short_mu
        sig_s = first_sub.short_sigma
        mu_l = first_sub.long_mu
        sig_l = first_sub.long_sigma

        x = z_score * sig_s + mu_s
        z_long = (x - mu_l) / sig_l if sig_l >= 0.001 else z_score
        z_prime = max(-sigma, min(sigma, z_long))
        return z_prime

    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──
    # Step 4: Softmax 归一化
    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──

    def _step4_softmax(self, z_primes: list[float]) -> list[float]:
        """
        a_i = e^(z'_i / T) / Σ e^(z'_j / T)

        T = temperature（默认 1.0）。
        当样本数 < min_samples 时退回到线性归一化。
        """
        if len(z_primes) < self.config.softmax.min_samples_for_normalization:
            z_min = min(z_primes)
            z_max = max(z_primes)
            span = z_max - z_min if z_max != z_min else 1.0
            return [(z - z_min) / span for z in z_primes]

        T = self.config.softmax.temperature
        exp_vals = [math.exp(z / T) for z in z_primes]
        exp_sum = sum(exp_vals)
        return [ev / exp_sum for ev in exp_vals]

    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──
    # Step 5: 综合 DES + 增长向量
    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──

    def _step5_final_des(
        self,
        dim_results: dict[str, DimensionResult],
        previous_z_scores: Optional[dict[str, float]],
    ) -> tuple[float, Optional[GrowthSummary]]:
        """加权求和 + 增长向量分析"""
        des = 0.0
        for dim_code, r in dim_results.items():
            w = self.config.dimensions[dim_code].weight
            des += w * r.softmax_score

        growth = None
        if previous_z_scores and self.config.growth_vector.enabled:
            deltas: dict[str, float] = {}
            overall_delta = 0.0
            for dim_code, r in dim_results.items():
                z_prev = previous_z_scores.get(dim_code)
                if z_prev is not None:
                    delta = r.z_score - z_prev
                    deltas[dim_code] = delta
                    w = self.config.dimensions[dim_code].weight
                    overall_delta += w * delta

            trend: Literal["improving", "stable", "declining"] = (
                "improving" if overall_delta > 0.1
                else "declining" if overall_delta < -0.1
                else "stable"
            )
            growth = GrowthSummary(
                overall_delta_z=overall_delta,
                dimension_deltas=deltas,
                trend=trend,
            )

        return des, growth
