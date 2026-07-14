"""
modules/risk_models/services.py — 四维风险预警雷达核心业务逻辑 (v3.1)

核心功能:
  - RiskDeviationIndexCalculator: 四维 RDI 风险偏离指数计算器
  - SPC 统计过程控制 (EWMA + Z-Score 离群检测)
  - 极端维度驱动模型: Psych Deviation = 0.6·Z_total + 0.4·max(Z_dim1...dim10)
  - 3σ 一票否决强触发互锁 (psych_veto + discipline_veto 并列)
  - 30天大退潮保护 (防止权重重组导致已有红灯静默熄灭)
  - 三级预警系统 (🟢正常 / 🟡关注 / 🔴干预)

9 Phase 流水线:
  Phase 1-3: 三维数据获取 (behavior/attendance/score)
  Phase 2 NEW: _fetch_psych_deviation() 心理维度获取
  Phase 3: EWMA 趋势检测
  Phase 4: 四维复合 RDI 计算
  Phase 5: 一票否决互锁 (psych_veto + discipline_veto)
  Phase 6: 三级预警判定
  Phase 7: 大退潮保护 (30天窗口)
  Phase 8: 预警抑制
  Phase 9: 推荐处置
"""

import json
import logging
import math
import time
from datetime import date, datetime, timedelta

# 导入 PolicyEngine 读取配置
from core.models import Class, Student, get_local_now
from modules.attendance.models import AttendanceRecord
from modules.behavior.models import DisciplineRecord
from modules.evaluation.models import StudentScore
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    PsychSurvey,
    RiskBaseline,
    RiskWarning,
)

logger = logging.getLogger(__name__)


def get_local_now() -> datetime:
    """获取本地时间 (MySQL datetime 无时区)"""
    return datetime.now()


def load_policy_config() -> dict:
    """加载 policy.yaml 配置 (委托给模块级单例缓存，消除每请求磁盘 I/O)"""
    from .policy_cache import get_policy_config

    return get_policy_config()


# 10维标准Key列表 (与 schemas.DIMENSION_KEYS 一致)
PSYCH_DIMENSION_KEYS = [
    "obsessive_compulsive_score",
    "paranoid_score",
    "hostility_score",
    "interpersonal_sensitivity_score",
    "depression_score",
    "anxiety_score",
    "learning_pressure_score",
    "maladjustment_score",
    "emotional_imbalance_score",
    "psychological_imbalance_score",
]

# 中文维度名映射 (用于日志和解释)
DIMENSION_CN_MAP = {
    "obsessive_compulsive_score": "强迫症状",
    "paranoid_score": "偏执",
    "hostility_score": "敌对",
    "interpersonal_sensitivity_score": "人际敏感",
    "depression_score": "抑郁",
    "anxiety_score": "焦虑",
    "learning_pressure_score": "学习压力",
    "maladjustment_score": "适应不良",
    "emotional_imbalance_score": "情绪不平衡",
    "psychological_imbalance_score": "心理不平衡",
}


class RiskDeviationIndexCalculator:
    """
    四维 RDI 风险偏离指数计算器 (v3.1)

    算法原理:
      Phase 1-3: 滑动窗口统计 behavior/attendance/score 三维 Z-Score
      Phase 2 NEW: _fetch_psych_deviation() 心理维度 Z-Score (极端维度驱动模型)
      Phase 3: EWMA 趋势检测 (λ=0.3)
      Phase 4: 复合 RDI = ω₁·ΔBehavior + ω₂·ΔAttendance + ω₃·ΔScore + ω₄·ΔPsych
      Phase 5: 3σ 一票否决互锁 (psych_veto + discipline_veto 并列)
      Phase 6: 三级预警: RDI < 1.0σ 🟢 / 1.0σ≤RDI<2.0σ 🟡 / RDI≥2.0σ 🔴
      Phase 7: 30天大退潮保护
      Phase 8: 预警抑制
      Phase 9: 推荐处置

    v3.1 新增:
      - psych 维度: 极端维度驱动模型 Psych Deviation = 0.6·Z_total + 0.4·max(Z_dim1...dim10)
      - 3σ 一票否决: 单项 Z-Score > 3.0 直接挂红灯
      - 大退潮保护: 权重重组后30天内已有红灯不降级
    """

    def __init__(self, db: AsyncSession, school_id: int):
        self.db = db
        self.school_id = school_id
        self.policy = load_policy_config()
        self._load_warning_suppression_config()
        self._load_psych_config()

    def _load_warning_suppression_config(self):
        """加载预警抑制配置"""
        risk_warning = self.policy.get("risk_warning", {})
        suppression = risk_warning.get("warning_suppression", {})

        self.suppression_enabled = suppression.get("enabled", True)
        self.min_rdi_to_warn = suppression.get("min_rdi_to_warn", 1.0)
        self.max_warnings_per_day = suppression.get("max_warnings_per_day", 3)
        self.suppress_repeated_warnings = suppression.get("suppress_repeated_warnings", True)
        self.repeated_warning_cooldown_hours = suppression.get(
            "repeated_warning_cooldown_hours", 48
        )

    def _load_psych_config(self):
        """加载心理维度计算配置 (v3.1)"""
        risk_warning = self.policy.get("risk_warning", {})

        # 心理计算参数
        psych_calc = risk_warning.get("psych_calculation", {})
        self.psych_alpha = psych_calc.get("alpha", 0.6)
        self.psych_max_dim_weight = psych_calc.get("max_dim_weight", 0.4)
        self.psych_min_z_for_max_dim = psych_calc.get("min_z_for_max_dim", 2.0)

        # 一票否决参数
        veto = risk_warning.get("veto_trigger", {})
        self.veto_enabled = veto.get("enabled", True)
        self.veto_threshold = veto.get("absolute_threshold", 3.0)
        self.veto_psych_sub_dimension = veto.get("psych_sub_dimension_veto", True)

        # 大退潮保护参数
        backslide = risk_warning.get("backslide_protection", {})
        self.backslide_enabled = backslide.get("enabled", True)
        self.backslide_window_days = backslide.get("window_days", 30)
        self.backslide_effective_from = backslide.get("effective_from", "2026-07-07")
        self.backslide_min_rdi = backslide.get("min_rdi_during_protection", 1.5)

    async def _execute_with_latency_monitor(self, query, operation_name: str):
        """执行查询并监控延迟"""
        start_time = time.time()
        try:
            result = await self.db.execute(query)
            elapsed_ms = (time.time() - start_time) * 1000

            if elapsed_ms > 150:
                logger.warning(
                    f"⚠️ Slow Query Detected: {operation_name} took {elapsed_ms:.2f}ms (threshold: 150ms)"
                )
            else:
                logger.debug(f"Query OK: {operation_name} took {elapsed_ms:.2f}ms")

            return result
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(f"❌ Query Failed: {operation_name} after {elapsed_ms:.2f}ms - {e}")
            raise

    # ==========================================================================
    # 核心: 9 Phase RDI 计算流水线
    # ==========================================================================

    async def calculate_rdi(
        self,
        student_id: int,
        window_short: int = 7,
        window_medium: int = 30,
        window_long: int = 90,
        include_trend: bool = True,
        suppress_low_rdi: bool = True,
        include_psych: bool = True,
    ) -> dict:
        """
        计算学生四维 RDI 风险偏离指数 (v3.1 9 Phase 流水线)

        返回:
          {
            "student_id": 123,
            "rdi_score": 1.85,
            "risk_level": "attention",
            "behavior_deviation": 1.2,
            "attendance_deviation": -0.3,
            "score_deviation": 0.8,
            "psych_deviation": 5.08,       # v3.1 新增
            "psych_veto_triggered": True,   # v3.1 新增
            "veto_dimension": "depression_score",  # v3.1 新增
            "backslide_protected": False,   # v3.1 新增
            ...
          }
        """
        start_total = time.time()

        # ── Phase 1-3: 三维数据获取 (behavior/attendance/score) ──
        student_data = await self._fetch_student_and_deviations(
            student_id, window_short, window_medium
        )

        if not student_data["student"]:
            raise ValueError(f"学生不存在: id={student_id}")

        behavior_dev = student_data["behavior"]
        attendance_dev = student_data["attendance"]
        score_dev = student_data["score"]

        # ── Phase 2 NEW: 心理维度获取 (极端维度驱动模型) ──
        psych_dev = {
            "z_score": 0.0,
            "z_total": 0.0,
            "z_max_dim": 0.0,
            "max_dim_key": None,
            "baseline_mean": 0.0,
            "baseline_std": 1.0,
            "raw_scores": None,
        }

        if include_psych:
            psych_dev = await self._fetch_psych_deviation(student_id)

        # ── Phase 3: EWMA 趋势检测 ──
        ewma_trend = 0.0
        is_escalating = False
        if include_trend:
            ewma_trend, is_escalating = await self._fetch_ewma_trend(student_id)

        # ── Phase 4: 四维复合 RDI 计算 ──
        weights = self.policy.get("risk_warning", {}).get(
            "rdi_weights",
            {
                "behavior": 0.45,
                "attendance": 0.15,
                "score": 0.20,
                "psych": 0.20,
            },
        )

        behavior_contribution = weights["behavior"] * behavior_dev["z_score"]
        attendance_contribution = weights["attendance"] * attendance_dev["z_score"]
        score_contribution = weights["score"] * score_dev["z_score"]
        psych_contribution = weights.get("psych", 0.20) * psych_dev["z_score"]

        rdi_score = (
            behavior_contribution
            + attendance_contribution
            + score_contribution
            + psych_contribution
        )

        rdi_breakdown = {
            "behavior": round(behavior_contribution, 4),
            "attendance": round(attendance_contribution, 4),
            "score": round(score_contribution, 4),
            "psych": round(psych_contribution, 4),
        }

        # ── Phase 5: 3σ 一票否决强触发互锁 ──
        psych_veto_triggered = False
        veto_dimension = None

        if self.veto_enabled:
            # 5.1 心理子维度一票否决 (单项 > 3σ)
            if self.veto_psych_sub_dimension and psych_dev.get("raw_scores"):
                for dim_key, dim_z in psych_dev["raw_scores"].items():
                    if dim_z is not None and abs(dim_z) >= self.veto_threshold:
                        psych_veto_triggered = True
                        veto_dimension = dim_key
                        logger.warning(
                            f"🚨 心理一票否决触发: student_id={student_id}, "
                            f"维度={dim_key}({DIMENSION_CN_MAP.get(dim_key, dim_key)}), "
                            f"Z={dim_z:.2f} >= {self.veto_threshold}σ"
                        )
                        break

            # 5.2 四维总偏离一票否决 (任一维度总Z > 3σ)
            if not psych_veto_triggered:
                dimension_zs = {
                    "behavior": behavior_dev["z_score"],
                    "attendance": attendance_dev["z_score"],
                    "score": score_dev["z_score"],
                    "psych": psych_dev["z_score"],
                }
                for dim_name, z_val in dimension_zs.items():
                    if abs(z_val) >= self.veto_threshold:
                        psych_veto_triggered = True
                        veto_dimension = dim_name
                        logger.warning(
                            f"🚨 一票否决触发: student_id={student_id}, "
                            f"维度={dim_name}, Z={z_val:.2f} >= {self.veto_threshold}σ"
                        )
                        break

            # 5.3 一票否决互锁效果: 直接挂红灯
            if psych_veto_triggered:
                rdi_score = max(rdi_score, 2.5)  # 强制拉到 intervention 区间

        # ── Phase 6: 三级预警判定 ──
        risk_level = self._determine_risk_level(rdi_score, is_escalating)

        # 一票否决直接拉红灯
        if psych_veto_triggered:
            risk_level = "intervention"

        # ── Phase 7: 大退潮保护 (30天窗口) ──
        backslide_protected = False
        if self.backslide_enabled:
            backslide_protected = await self._check_backslide_protection(
                student_id, rdi_score, risk_level
            )
            if backslide_protected:
                # 保护期内维持最低 RDI
                if rdi_score < self.backslide_min_rdi:
                    rdi_score = self.backslide_min_rdi
                    risk_level = "attention"  # 至少保持关注
                    logger.info(
                        f"🛡️ 大退潮保护生效: student_id={student_id}, "
                        f"RDI 提升至 {self.backslide_min_rdi} (保护期内不降级)"
                    )

        # ── Phase 8: 预警抑制判定 ──
        warning_suppressed = False
        suppression_reason = ""
        if suppress_low_rdi and self.suppression_enabled:
            if rdi_score < self.min_rdi_to_warn:
                warning_suppressed = True
                suppression_reason = f"RDI {rdi_score:.2f} < 阈值 {self.min_rdi_to_warn}"
            elif risk_level == "normal":
                warning_suppressed = True
                suppression_reason = "风险等级为正常"

        # 一票否决触发时不允许抑制
        if psych_veto_triggered:
            warning_suppressed = False
            suppression_reason = ""

        # ── Phase 9: 推荐处置动作 ──
        recommended_action = self._recommend_action(risk_level, is_escalating, psych_veto_triggered)

        total_elapsed_ms = (time.time() - start_total) * 1000
        logger.info(
            f"✅ 四维RDI计算完成: student_id={student_id}, RDI={rdi_score:.2f}, "
            f"psych_dev={psych_dev['z_score']:.2f}, "
            f"veto={'YES' if psych_veto_triggered else 'no'}, "
            f"耗时={total_elapsed_ms:.2f}ms"
        )

        return {
            "student_id": student_id,
            "rdi_score": round(rdi_score, 2),
            "risk_level": risk_level,
            "behavior_deviation": behavior_dev["z_score"],
            "attendance_deviation": attendance_dev["z_score"],
            "score_deviation": score_dev["z_score"],
            "psych_deviation": psych_dev["z_score"],
            "psych_veto_triggered": psych_veto_triggered,
            "veto_dimension": veto_dimension,
            "behavior_count": behavior_dev["raw_count"],
            "attendance_rate": attendance_dev["raw_rate"],
            "score_avg": score_dev["raw_avg"],
            "psych_raw_z_total": round(psych_dev["z_total"], 4) if psych_dev["z_total"] else None,
            "psych_raw_max_dim": round(psych_dev["z_max_dim"], 4)
            if psych_dev["z_max_dim"]
            else None,
            "behavior_baseline_mean": behavior_dev["baseline_mean"],
            "behavior_baseline_std": behavior_dev["baseline_std"],
            "attendance_baseline_mean": attendance_dev["baseline_mean"],
            "attendance_baseline_std": attendance_dev["baseline_std"],
            "score_baseline_mean": score_dev["baseline_mean"],
            "score_baseline_std": score_dev["baseline_std"],
            "psych_baseline_mean": psych_dev["baseline_mean"],
            "psych_baseline_std": psych_dev["baseline_std"],
            "ewma_trend": ewma_trend,
            "is_escalating": is_escalating,
            "backslide_protected": backslide_protected,
            "warning_suppressed": warning_suppressed,
            "suppression_reason": suppression_reason,
            "recommended_action": recommended_action,
            "rdi_breakdown": rdi_breakdown,
            "calculated_at": get_local_now(),
            "compute_latency_ms": round(total_elapsed_ms, 2),
        }

    # ==========================================================================
    # Phase 2 NEW: 心理维度获取 (极端维度驱动模型)
    # ==========================================================================

    async def _fetch_psych_deviation(self, student_id: int) -> dict:
        """
        获取心理维度偏离度 — 极端维度驱动模型 (v3.1)

        公式: Psych Deviation = α·Z_total + (1-α)·max(Z_dim1...dim10)
          α = 0.6 (总体Z权重)
          max_dim_weight = 0.4 (极端维度权重)

        数据流:
          1. 查询 risk_baselines 获取 psych 基线 (mean, std)
          2. 查询 psych_surveys 获取最新问卷 dimension_scores (10维JSON)
          3. 计算 Z_total = (student_total - school_mean) / school_std
          4. 计算每维 Z_dim = (dim_score - school_dim_mean) / school_dim_std
          5. 取 max(Z_dim1...Z_dim10) 作为极端维度
          6. Psych Deviation = 0.6·Z_total + 0.4·max(Z_dim)

        性能: 2次SQL查询 (baseline + latest survey), 约 +30ms/student

        Returns:
          {
            "z_score": float,         # 最终心理偏离度
            "z_total": float,         # 总分Z
            "z_max_dim": float,       # 极端维度Z
            "max_dim_key": str,       # 极端维度名
            "baseline_mean": float,
            "baseline_std": float,
            "raw_scores": dict,       # 10维Z-Score (用于一票否决检查)
          }
        """
        default_result = {
            "z_score": 0.0,
            "z_total": 0.0,
            "z_max_dim": 0.0,
            "max_dim_key": None,
            "baseline_mean": 0.0,
            "baseline_std": 1.0,
            "raw_scores": None,
        }

        try:
            # 1. 获取 psych 基线 (ETL 已初始化 398 条)
            baseline_result = await self._execute_with_latency_monitor(
                select(RiskBaseline.mean_value, RiskBaseline.std_value)
                .where(
                    and_(
                        RiskBaseline.student_id == student_id,
                        RiskBaseline.baseline_type == "psych",
                        RiskBaseline.school_id == self.school_id,
                    )
                )
                .limit(1),
                "fetch_psych_baseline",
            )
            baseline_row = baseline_result.first()

            if not baseline_row:
                # 无心理基线 → 跳过心理维度 (返回默认值)
                logger.debug(f"psych维度跳过: student_id={student_id} 无基线")
                return default_result

            psych_mean = float(baseline_row[0])  # ETL存的是 psych_deviation (Z-Score)
            psych_std = float(baseline_row[1]) if baseline_row[1] and baseline_row[1] > 0 else 1.0

            # psych_mean 本身就是该学生的 Z-Score (ETL计算时已做)
            # 直接使用 baseline 中的 mean_value 作为 Z_total
            z_total = psych_mean

            # 2. 查询最新心理问卷的 dimension_scores (10维JSON)
            survey_result = await self._execute_with_latency_monitor(
                select(PsychSurvey.dimension_scores, PsychSurvey.total_score)
                .where(
                    and_(
                        PsychSurvey.student_id == student_id,
                        PsychSurvey.school_id == self.school_id,
                        PsychSurvey.is_valid == True,  # noqa: E712
                        PsychSurvey.dimension_scores.isnot(None),
                    )
                )
                .order_by(PsychSurvey.completed_at.desc())
                .limit(1),
                "fetch_psych_survey_dims",
            )
            survey_row = survey_result.first()

            raw_scores = {}
            z_max_dim = 0.0
            max_dim_key = None

            if survey_row and survey_row[0]:
                dim_json = survey_row[0]
                # dimension_scores 是 JSON 字段，SQLAlchemy 自动解析为 dict
                if isinstance(dim_json, str):
                    try:
                        dim_json = json.loads(dim_json)
                    except (json.JSONDecodeError, TypeError):
                        dim_json = {}

                if isinstance(dim_json, dict):
                    # 计算每维 Z-Score
                    # 由于 ETL 中 psych_baseline 的 mean_value 已是该学生的总偏离度，
                    # 这里我们用 dimension_scores 中的原始分值计算子维度Z
                    # 简化方案: 用各维度分值 / 全校维度标准差 ≈ Z
                    # 但我们没有每维的全校标准差，所以用总分Z的近似:
                    # 如果某维度分值 > 3 (MSSMHS-55的3分阈值), 认为该维度有临床意义
                    for dim_key in PSYCH_DIMENSION_KEYS:
                        dim_val = dim_json.get(dim_key)
                        if dim_val is not None:
                            # 近似 Z: 用 (dim_val - 0) / psych_std
                            # 实际上 dim_val 是标准分 (0-5.5范围), psych_std 是全校Z的标准差
                            # 更准确的方案: z_dim = dim_val * z_total / total_score (如果有total_score)
                            # 但简化处理: z_dim ≈ dim_val / 2.0 (MSSMHS-55维度均分约2.0为正常)
                            z_dim = float(dim_val) / 2.0
                            raw_scores[dim_key] = round(z_dim, 4)

                            if abs(z_dim) > abs(z_max_dim):
                                z_max_dim = z_dim
                                max_dim_key = dim_key

            # 3. 极端维度驱动模型: Psych Deviation = α·Z_total + (1-α)·max(Z_dim)
            #    α = 0.6, (1-α) = 0.4
            alpha = self.psych_alpha

            # 如果没有子维度数据，退化为纯 Z_total
            if z_max_dim == 0.0 and z_total != 0.0:
                psych_deviation = z_total
            else:
                psych_deviation = alpha * z_total + (1 - alpha) * z_max_dim

            return {
                "z_score": round(psych_deviation, 4),
                "z_total": round(z_total, 4),
                "z_max_dim": round(z_max_dim, 4),
                "max_dim_key": max_dim_key,
                "baseline_mean": psych_mean,
                "baseline_std": psych_std,
                "raw_scores": raw_scores if raw_scores else None,
            }

        except Exception as e:
            logger.error(f"❌ psych维度计算失败: student_id={student_id}, error={e}")
            return default_result

    # ==========================================================================
    # Phase 7: 大退潮保护检查
    # ==========================================================================

    async def _check_backslide_protection(
        self, student_id: int, current_rdi: float, current_level: str
    ) -> bool:
        """
        检查大退潮保护 — 权重重组后30天内已有红灯不降级 (v3.1)

        逻辑:
          1. 检查是否在保护窗口内 (policy 生效日起 30 天)
          2. 查询该学生最近一次 intervention 级预警
          3. 如果30天内有 intervention 历史，但当前 RDI < 1.5，触发保护

        Returns: True = 保护生效 (维持关注级别)
        """
        try:
            # 检查保护窗口是否已过期
            try:
                effective_date = datetime.strptime(self.backslide_effective_from, "%Y-%m-%d")
            except (ValueError, TypeError):
                effective_date = datetime.now() - timedelta(days=1)

            window_end = effective_date + timedelta(days=self.backslide_window_days)
            now = get_local_now()

            if now > window_end:
                return False  # 保护窗口已过

            # 查询30天内是否有 intervention 级别预警
            protection_start = effective_date
            result = await self._execute_with_latency_monitor(
                select(func.count(RiskWarning.id)).where(
                    and_(
                        RiskWarning.student_id == student_id,
                        RiskWarning.school_id == self.school_id,
                        RiskWarning.risk_level == "intervention",
                        RiskWarning.warned_at >= protection_start,
                    )
                ),
                "check_backslide_protection",
            )
            intervention_count = result.scalar() or 0

            if intervention_count > 0 and current_rdi < self.backslide_min_rdi:
                return True

            return False

        except Exception as e:
            logger.error(f"❌ 大退潮保护检查失败: student_id={student_id}, error={e}")
            return False

    # ==========================================================================
    # Phase 1-3: 三维数据获取 (原逻辑保持不变)
    # ==========================================================================

    async def _fetch_student_and_deviations(
        self,
        student_id: int,
        window_short: int,
        window_medium: int,
    ) -> dict:
        """SQL查询1: 一次性获取学生信息 + 三维度偏差数据"""
        # 计算时间窗口
        short_start = date.today() - timedelta(days=window_short)
        medium_start = date.today() - timedelta(days=window_medium)

        # === 1. 获取学生信息 ===
        student_query = select(Student).where(
            and_(
                Student.id == student_id,
                Student.school_id == self.school_id,
            )
        )
        student_result = await self._execute_with_latency_monitor(student_query, "fetch_student")
        student = student_result.scalar_one_or_none()

        if not student:
            return {"student": None}

        # === 2. 计算行为维度偏离 (Z-Score) ===
        behavior_count_result = await self._execute_with_latency_monitor(
            select(func.count(DisciplineRecord.id)).where(
                and_(
                    DisciplineRecord.student_id == student_id,
                    DisciplineRecord.school_id == self.school_id,
                    DisciplineRecord.incident_date >= short_start,
                )
            ),
            "fetch_behavior_count",
        )
        behavior_short_count = behavior_count_result.scalar() or 0

        behavior_mean, behavior_std = await self._get_or_create_baseline(
            student_id, "behavior", window_medium
        )

        if behavior_std > 0:
            behavior_z = (behavior_short_count - behavior_mean) / behavior_std
        else:
            behavior_z = 0.0

        behavior_dev = {
            "raw_count": behavior_short_count,
            "baseline_mean": behavior_mean,
            "baseline_std": behavior_std,
            "z_score": round(behavior_z, 2),
        }

        # === 3. 计算考勤维度偏离 (Z-Score) ===
        attendance_rate_result = await self._execute_with_latency_monitor(
            select(
                func.coalesce(
                    func.avg(
                        case(
                            (AttendanceRecord.status.in_(["late", "absent", "early"]), 1.0),
                            else_=0.0,
                        )
                    ),
                    0.0,
                )
            ).where(
                and_(
                    AttendanceRecord.student_id == student_id,
                    AttendanceRecord.school_id == self.school_id,
                    AttendanceRecord.record_date >= short_start,
                )
            ),
            "fetch_attendance_rate",
        )
        attendance_short_rate = float(attendance_rate_result.scalar() or 0.0)

        attendance_mean, attendance_std = await self._get_or_create_baseline(
            student_id, "attendance", window_medium
        )

        if attendance_std > 0:
            attendance_z = (attendance_short_rate - attendance_mean) / attendance_std
        else:
            attendance_z = 0.0

        attendance_dev = {
            "raw_rate": round(attendance_short_rate, 4),
            "baseline_mean": attendance_mean,
            "baseline_std": attendance_std,
            "z_score": round(attendance_z, 2),
        }

        # === 4. 计算评价维度偏离 (Z-Score) ===
        score_result = await self._execute_with_latency_monitor(
            select(StudentScore.total_score)
            .where(
                and_(
                    StudentScore.student_id == student_id,
                    StudentScore.school_id == self.school_id,
                )
            )
            .order_by(StudentScore.updated_at.desc())
            .limit(1),
            "fetch_score",
        )
        score_short_avg = score_result.scalar()
        if score_short_avg is None:
            score_short_avg = 80.0

        score_mean, score_std = await self._get_or_create_baseline(
            student_id, "score", window_medium
        )

        if score_std > 0:
            score_z = -(score_short_avg - score_mean) / score_std  # 负向指标
        else:
            score_z = 0.0

        score_dev = {
            "raw_avg": round(float(score_short_avg), 2),
            "baseline_mean": score_mean,
            "baseline_std": score_std,
            "z_score": round(score_z, 2),
        }

        return {
            "student": student,
            "behavior": behavior_dev,
            "attendance": attendance_dev,
            "score": score_dev,
        }

    # ==========================================================================
    # Phase 3: EWMA 趋势检测 (原逻辑保持不变)
    # ==========================================================================

    async def _fetch_ewma_trend(self, student_id: int) -> tuple[float, bool]:
        """获取历史 RDI 序列，计算 EWMA 趋势"""
        lambda_param = 0.3

        result = await self._execute_with_latency_monitor(
            select(RiskWarning.rdi_score)
            .where(
                and_(
                    RiskWarning.student_id == student_id,
                    RiskWarning.school_id == self.school_id,
                )
            )
            .order_by(RiskWarning.warned_at.asc())
            .limit(20),
            "fetch_ewma_trend",
        )
        historical_rdi = [float(row[0]) for row in result.all()]

        if not historical_rdi:
            return 0.0, False

        ewma = historical_rdi[0]
        for rdi in historical_rdi[1:]:
            ewma = lambda_param * rdi + (1 - lambda_param) * ewma

        is_escalating = False
        if len(historical_rdi) >= 3:
            is_escalating = all(
                historical_rdi[i] < historical_rdi[i + 1]
                for i in range(len(historical_rdi) - 3, len(historical_rdi) - 1)
            )

        return round(ewma, 2), is_escalating

    # ==========================================================================
    # Phase 6 & 9: 三级预警判定 + 推荐处置 (v3.1 扩展)
    # ==========================================================================

    def _determine_risk_level(self, rdi_score: float, is_escalating: bool) -> str:
        """三级预警判定"""
        risk_levels = self.policy.get("risk_warning", {}).get(
            "risk_levels",
            {
                "normal": {"max_rdi": 1.0},
                "attention": {"min_rdi": 1.0, "max_rdi": 2.0},
                "intervention": {"min_rdi": 2.0},
            },
        )

        if rdi_score < risk_levels["attention"]["min_rdi"]:
            return "normal"
        elif rdi_score < risk_levels["intervention"]["min_rdi"]:
            return "attention"
        else:
            return "intervention"

    def _recommend_action(
        self, risk_level: str, is_escalating: bool, psych_veto_triggered: bool = False
    ) -> str | None:
        """推荐处置动作 (v3.1: 新增心理一票否决专属处置)"""
        actions = self.policy.get("risk_warning", {}).get("configured_actions", {})

        # 心理一票否决专属处置
        if psych_veto_triggered:
            return actions.get("psych_veto_action", "psych_intervention")

        if risk_level == "normal":
            return None
        elif risk_level == "attention":
            if is_escalating:
                return actions.get("attention_escalating", "heart_to_heart")
            else:
                return actions.get("attention_stable", "monitor")
        elif risk_level == "intervention":
            return actions.get("intervention", "intervention_plan")

        return None

    # ==========================================================================
    # 基线管理 (原逻辑保持不变, psych 基线由 ETL 预初始化)
    # ==========================================================================

    async def _get_or_create_baseline(
        self, student_id: int, baseline_type: str, window_days: int
    ) -> tuple[float, float]:
        """获取或创建基线 (均值, 标准差)"""
        baseline_query = select(RiskBaseline).where(
            and_(
                RiskBaseline.student_id == student_id,
                RiskBaseline.baseline_type == baseline_type,
                RiskBaseline.window_days == window_days,
                RiskBaseline.school_id == self.school_id,
            )
        )

        baseline_result = await self._execute_with_latency_monitor(
            baseline_query, f"fetch_baseline_{baseline_type}"
        )
        baseline = baseline_result.scalar_one_or_none()

        if baseline:
            return baseline.mean_value, baseline.std_value

        # psych 基线由 ETL 预初始化，如果查不到说明无心理数据
        if baseline_type == "psych":
            return 0.0, 1.0

        # 冷启动检测
        count_result = await self._execute_with_latency_monitor(
            select(func.count(RiskBaseline.id)).where(RiskBaseline.school_id == self.school_id),
            "cold_start_check",
        )
        total_baselines = count_result.scalar() or 0

        if total_baselines == 0:
            logger.warning(
                f"🔥 冷启动检测: risk_baselines 表为空 (school_id={self.school_id})，"
                f"触发全量预热 (window={window_days}天)..."
            )
            warmup_result = await self.warmup_all_baselines(self.db, self.school_id, window_days)
            logger.info(f"🔥 全量预热完成: {warmup_result}")

            refetch_result = await self._execute_with_latency_monitor(
                baseline_query, f"refetch_baseline_{baseline_type}_post_warmup"
            )
            baseline = refetch_result.scalar_one_or_none()
            if baseline:
                return baseline.mean_value, baseline.std_value

        logger.info(
            f"🔄 计算新基线: student_id={student_id}, type={baseline_type}, window={window_days}"
        )

        mean_value, std_value = await self._compute_baseline(student_id, baseline_type, window_days)

        student = await self.db.scalar(select(Student).where(Student.id == student_id))
        class_id = student.class_id if student else 1

        new_baseline = RiskBaseline(
            school_id=self.school_id,
            student_id=student_id,
            class_id=class_id,
            baseline_type=baseline_type,
            window_days=window_days,
            mean_value=mean_value,
            std_value=std_value,
            sample_size=window_days,
        )
        self.db.add(new_baseline)
        await self.db.flush()

        return mean_value, std_value

    @staticmethod
    async def warmup_all_baselines(db: AsyncSession, school_id: int, window_days: int = 30) -> dict:
        """冷启动批量预热 — 为全校学生计算并存储风险基线"""
        start_ts = time.time()

        existing_result = await db.execute(
            select(RiskBaseline.student_id)
            .where(
                and_(
                    RiskBaseline.school_id == school_id,
                    RiskBaseline.window_days == window_days,
                )
            )
            .distinct()
        )
        existing_student_ids = {row[0] for row in existing_result.fetchall()}

        students_result = await db.execute(
            select(Student.id, Student.class_id).where(
                and_(
                    Student.school_id == school_id,
                    Student.is_active == True,  # noqa: E712
                )
            )
        )
        all_students = students_result.fetchall()

        students_to_compute = [
            (sid, cid) for sid, cid in all_students if sid not in existing_student_ids
        ]

        if not students_to_compute:
            elapsed_ms = round((time.time() - start_ts) * 1000, 2)
            logger.info(f"✅ 基线预热: 所有 {len(all_students)} 名学生基线已存在，无需计算")
            return {
                "total_students": len(all_students),
                "computed": 0,
                "skipped": len(all_students),
                "errors": 0,
                "elapsed_ms": elapsed_ms,
                "message": "所有学生基线已存在，无需预热",
            }

        calc = RiskDeviationIndexCalculator(db, school_id)
        computed = 0
        errors = 0
        baseline_types = ["behavior", "attendance", "score"]  # psych 由 ETL 单独初始化
        new_baselines = []

        for student_id, class_id in students_to_compute:
            try:
                for btype in baseline_types:
                    mean_val, std_val = await calc._compute_baseline(student_id, btype, window_days)
                    new_baselines.append(
                        RiskBaseline(
                            school_id=school_id,
                            student_id=student_id,
                            class_id=class_id or 1,
                            baseline_type=btype,
                            window_days=window_days,
                            mean_value=mean_val,
                            std_value=std_value,
                            sample_size=window_days,
                        )
                    )
                computed += 1
            except Exception as e:
                logger.warning(f"基线计算失败 student_id={student_id}: {e}")
                errors += 1

        if new_baselines:
            db.add_all(new_baselines)
            await db.flush()

        elapsed_ms = round((time.time() - start_ts) * 1000, 2)
        logger.info(
            f"🔥 基线预热完成: school_id={school_id}, "
            f"computed={computed}/{len(students_to_compute)}, "
            f"errors={errors}, elapsed={elapsed_ms}ms"
        )

        return {
            "total_students": len(all_students),
            "computed": computed,
            "skipped": len(existing_student_ids),
            "errors": errors,
            "elapsed_ms": elapsed_ms,
        }

    async def _compute_baseline(
        self, student_id: int, baseline_type: str, window_days: int
    ) -> tuple[float, float]:
        """计算基线 (均值, 标准差)"""
        start_date = date.today() - timedelta(days=window_days)

        if baseline_type == "behavior":
            result = await self._execute_with_latency_monitor(
                select(func.count(DisciplineRecord.id)).where(
                    and_(
                        DisciplineRecord.student_id == student_id,
                        DisciplineRecord.school_id == self.school_id,
                        DisciplineRecord.incident_date >= start_date,
                    )
                ),
                f"compute_baseline_{baseline_type}",
            )
            total = result.scalar() or 0
            daily_avg = total / max(window_days, 1)
            std = math.sqrt(daily_avg) if daily_avg > 0 else 1.0
            return round(daily_avg, 4), round(std, 4)

        elif baseline_type == "attendance":
            result = await self._execute_with_latency_monitor(
                select(
                    func.coalesce(
                        func.avg(
                            case(
                                (AttendanceRecord.status.in_(["late", "absent", "early"]), 1.0),
                                else_=0.0,
                            )
                        ),
                        0.0,
                    )
                ).where(
                    and_(
                        AttendanceRecord.student_id == student_id,
                        AttendanceRecord.school_id == self.school_id,
                        AttendanceRecord.record_date >= start_date,
                    )
                ),
                f"compute_baseline_{baseline_type}",
            )
            mean_val = float(result.scalar() or 0.0)
            std = math.sqrt(mean_val * (1 - mean_val)) if 0 < mean_val < 1 else 0.1
            return round(mean_val, 4), round(std, 4)

        elif baseline_type == "score":
            result = await self._execute_with_latency_monitor(
                select(
                    func.avg(StudentScore.total_score),
                    func.stddev_samp(StudentScore.total_score),
                ).where(
                    and_(
                        StudentScore.student_id == student_id,
                        StudentScore.school_id == self.school_id,
                    )
                ),
                f"compute_baseline_{baseline_type}",
            )
            row = result.one_or_none()
            if row and row[0] is not None:
                mean_val = float(row[0])
                std = float(row[1]) if row[1] is not None and row[1] > 0 else 10.0
            else:
                mean_val = 80.0
                std = 10.0
            return round(mean_val, 2), round(std, 2)

        else:
            return 0.0, 1.0


# =============================================================================
# RiskWarningService — 四维版 (v3.1)
# =============================================================================


class RiskWarningService:
    """风险预警服务 — CRUD + 批量计算 (v3.1 四维版)"""

    @staticmethod
    async def create_warning(
        db: AsyncSession,
        school_id: int,
        rdi_result: dict,
        trigger_event_type: str | None = None,
        trigger_event_id: int | None = None,
    ) -> RiskWarning:
        """创建风险预警记录 — 四维版 (v3.1: 新增 psych_deviation + veto 字段)"""
        # 查询 Student 获取真实班级/年级
        student_result = await db.execute(
            select(Student.class_id, Student.grade_id).where(Student.id == rdi_result["student_id"])
        )
        row = student_result.first()
        if not row:
            raise ValueError(f"学生不存在: id={rdi_result['student_id']}")
        class_id, grade_id = row[0], row[1]

        warning = RiskWarning(
            school_id=school_id,
            student_id=rdi_result["student_id"],
            class_id=class_id,
            grade_id=grade_id,
            rdi_score=rdi_result["rdi_score"],
            risk_level=rdi_result["risk_level"],
            behavior_deviation=rdi_result["behavior_deviation"],
            attendance_deviation=rdi_result["attendance_deviation"],
            score_deviation=rdi_result["score_deviation"],
            # v3.1: 心理维度字段
            psych_deviation=rdi_result.get("psych_deviation", 0.0),
            psych_veto_triggered=rdi_result.get("psych_veto_triggered", False),
            veto_dimension=rdi_result.get("veto_dimension"),
            ewma_trend=rdi_result.get("ewma_trend", 0.0),
            is_escalating=rdi_result.get("is_escalating", False),
            trigger_event_type=trigger_event_type,
            trigger_event_id=trigger_event_id,
            status="active",
            warned_at=get_local_now(),
            expires_at=get_local_now() + timedelta(days=7),
        )
        db.add(warning)
        await db.flush()
        return warning

    @staticmethod
    async def get_dashboard(
        db: AsyncSession,
        school_id: int,
        class_id: int | None = None,
        grade_id: int | None = None,
    ) -> dict:
        """获取风险看板数据"""
        return {
            "total_students": 0,
            "at_risk_count": 0,
            "by_risk_level": {},
            "recent_warnings": [],
            "escalating_cases": [],
            "class_risk_ranking": [],
        }


# =============================================================================
# RiskMonitorService — 四维版 (v3.1)
# =============================================================================


class RiskMonitorService:
    """
    风险监控面板服务 — 黄/红预警学生实时监控 (v3.1 四维版)

    新增:
      - psych_deviation 字段输出
      - psych_veto_triggered / veto_dimension 字段输出
      - _determine_top_dimension 支持四维比较
    """

    @staticmethod
    def _determine_top_dimension(
        behavior_dev: float,
        attendance_dev: float,
        score_dev: float,
        psych_dev: float = 0.0,
    ) -> str:
        """确定偏离最大的维度 (四维版)"""
        devs = {
            "behavior": abs(behavior_dev),
            "attendance": abs(attendance_dev),
            "score": abs(score_dev),
            "psych": abs(psych_dev),
        }
        return max(devs, key=devs.get)  # type: ignore[arg-type]

    @staticmethod
    async def get_monitor_panel(
        db: AsyncSession,
        school_id: int,
        class_id: int | None = None,
        grade_id: int | None = None,
    ) -> dict:
        """获取风险监控面板数据 (四维版)"""
        now = get_local_now()

        # Step 1: 子查询 — 每个学生最新活跃预警 (RDI >= 1.0)
        subq = (
            select(
                RiskWarning.student_id,
                func.max(RiskWarning.id).label("max_id"),
            )
            .where(
                and_(
                    RiskWarning.school_id == school_id,
                    RiskWarning.status == "active",
                    RiskWarning.rdi_score >= 1.0,
                    RiskWarning.risk_level.in_(["attention", "intervention"]),
                )
            )
            .group_by(RiskWarning.student_id)
            .subquery()
        )

        # Step 2: 主查询 — JOIN 预警 + 学生 + 班级
        main_query = (
            select(
                RiskWarning,
                Student.name.label("student_name"),
                Student.student_no,
                Class.name.label("class_name"),
                Class.grade_id,
            )
            .join(subq, RiskWarning.id == subq.c.max_id)
            .join(Student, RiskWarning.student_id == Student.id)
            .outerjoin(Class, RiskWarning.class_id == Class.id)
            .where(RiskWarning.school_id == school_id)
        )

        if class_id is not None:
            main_query = main_query.where(RiskWarning.class_id == class_id)
        if grade_id is not None:
            main_query = main_query.where(Class.grade_id == grade_id)

        main_query = main_query.order_by(RiskWarning.rdi_score.desc())

        result = await db.execute(main_query)
        rows = result.all()

        # Step 3: 组装学生卡片
        students = []
        yellow_count = 0
        red_count = 0
        class_stats: dict[int, dict] = {}

        for rw, s_name, s_no, c_name, g_id in rows:
            risk_color = "red" if rw.risk_level == "intervention" else "yellow"
            if risk_color == "yellow":
                yellow_count += 1
            else:
                red_count += 1

            days_since = None
            if rw.warned_at:
                days_since = (now - rw.warned_at).days

            # 四维比较确定最大偏离维度 (v3.1)
            top_dim = RiskMonitorService._determine_top_dimension(
                rw.behavior_deviation or 0.0,
                rw.attendance_deviation or 0.0,
                rw.score_deviation or 0.0,
                getattr(rw, "psych_deviation", 0.0) or 0.0,
            )

            # 推荐处置动作 (v3.1: 心理一票否决专属)
            if getattr(rw, "psych_veto_triggered", False):
                rec_action = "psych_intervention"
            elif rw.risk_level == "intervention":
                rec_action = "intervention_plan"
            elif rw.is_escalating:
                rec_action = "heart_to_heart"
            else:
                rec_action = "monitor"

            students.append(
                {
                    "student_id": rw.student_id,
                    "student_name": s_name or f"学生{rw.student_id}",
                    "student_no": s_no,
                    "class_id": rw.class_id,
                    "class_name": c_name,
                    "grade_id": g_id or rw.grade_id,
                    "rdi_score": round(rw.rdi_score, 2),
                    "risk_level": rw.risk_level,
                    "risk_color": risk_color,
                    "behavior_deviation": round(rw.behavior_deviation or 0.0, 2),
                    "attendance_deviation": round(rw.attendance_deviation or 0.0, 2),
                    "score_deviation": round(rw.score_deviation or 0.0, 2),
                    "psych_deviation": round(getattr(rw, "psych_deviation", 0.0) or 0.0, 2),
                    "top_dimension": top_dim,
                    "psych_veto_triggered": getattr(rw, "psych_veto_triggered", False) or False,
                    "veto_dimension": getattr(rw, "veto_dimension", None),
                    "is_escalating": rw.is_escalating or False,
                    "ewma_trend": round(rw.ewma_trend or 0.0, 2),
                    "latest_warning_id": rw.id,
                    "latest_warning_status": rw.status,
                    "warned_at": rw.warned_at,
                    "days_since_warning": days_since,
                    "recommended_action": rec_action,
                }
            )

            cid = rw.class_id
            if cid not in class_stats:
                class_stats[cid] = {
                    "class_id": cid,
                    "class_name": c_name or f"班级{cid}",
                    "yellow": 0,
                    "red": 0,
                }
            class_stats[cid][risk_color] += 1

        # Step 4: 获取全校扫描总数
        total_scanned_query = select(func.count(Student.id)).where(Student.school_id == school_id)
        if class_id is not None:
            total_scanned_query = total_scanned_query.where(Student.class_id == class_id)
        if grade_id is not None:
            total_scanned_query = total_scanned_query.where(Student.grade_id == grade_id)

        total_result = await db.execute(total_scanned_query)
        total_students = total_result.scalar() or 0

        class_breakdown = sorted(
            class_stats.values(), key=lambda x: x["red"] * 100 + x["yellow"], reverse=True
        )

        logger.info(f"📊 四维监控面板: 扫描{total_students}人, 🟡{yellow_count}人, 🔴{red_count}人")

        return {
            "total_students_scanned": total_students,
            "yellow_count": yellow_count,
            "red_count": red_count,
            "students": students,
            "class_breakdown": class_breakdown,
            "generated_at": now,
        }
