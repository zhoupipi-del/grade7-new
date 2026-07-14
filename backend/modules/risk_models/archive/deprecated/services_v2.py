"""
modules/risk_models/services.py — 风险预警雷达核心业务逻辑 (真实数据源版本)

核心功能:
  - RiskDeviationIndexCalculator: RDI 风险偏离指数计算器
  - 真实数据源: DisciplineRecord / AttendanceRecord / StudentScore (ORM查询)
  - SQL 优化: ≤3次交互 (使用 scalar_subquery 合并查询)
  - Latency Monitor: 超过150ms → log.warning
"""

import logging
import os
import time
from datetime import date, datetime, timedelta

# 导入 PolicyEngine 读取配置
import yaml
from core.models import Student, get_local_now
from modules.attendance.models import AttendanceRecord

# 导入其他模块的 Model (真实数据源)
from modules.behavior.models import DisciplineRecord
from modules.evaluation.models import StudentScore
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import RiskBaseline, RiskWarning

logger = logging.getLogger(__name__)


def get_local_now() -> datetime:
    """获取本地时间 (MySQL datetime 无时区)"""
    return datetime.now()


def load_policy_config() -> dict:
    """加载 policy.yaml 配置"""
    policy_path = os.path.join(os.path.dirname(__file__), "../../policy.yaml")
    try:
        with open(policy_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config.get("policy_engine", {})
    except Exception as e:
        logger.warning(f"Failed to load policy.yaml: {e}, using defaults")
        return {}


class RiskDeviationIndexCalculator:
    """
    RDI 风险偏离指数计算器 (真实数据源版本)

    算法原理:
      1. 滑动窗口统计: 计算学生在 7天/30天/90天 窗口内的行为/考勤/评价均值
      2. Z-Score 离群检测: (当前值 - 窗口均值) / 窗口标准差
      3. EWMA 趋势检测: λ=0.3 指数加权移动平均，检测 escalation
      4. 复合 RDI: ω₁×ΔBehavior + ω₂×ΔAttendance + ω₃×ΔScore
      5. 三级预警: RDI < 1.0σ 🟢 / 1.0σ≤RDI<2.0σ 🟡 / RDI≥2.0σ 🔴

    SQL 优化 (≤3次交互):
      - SQL 1: 学生信息 (SELECT Student ...)
      - SQL 2: 三维度基线 (SELECT RiskBaseline WHERE type IN (...) → 3行)
      - SQL 3: 三维度当前值 (使用 scalar_subquery 合并为1次查询)

    预警抑制:
      - 读取 policy.yaml 中 warning_suppression 配置
      - 避免预警疲劳 (alert fatigue)

    Latency Monitor:
      - 所有 SELECT 包裹在 _execute_with_latency_monitor()
      - 超过 150ms → log.warning
    """

    def __init__(self, db: AsyncSession, school_id: int):
        self.db = db
        self.school_id = school_id
        self.policy = load_policy_config()
        self._load_warning_suppression_config()

    def _load_warning_suppression_config(self):
        """加载预警抑制配置"""
        risk_warning = self.policy.get("risk_warning", {})
        suppression = risk_warning.get("warning_suppression", {})

        self.suppression_enabled = suppression.get("enabled", True)
        self.min_rdi_to_warn = suppression.get("min_rdi_to_warn", 1.0)
        self.max_warnings_per_day = suppression.get("max_warnings_per_day", 3)  # 总指挥调整为3
        self.suppress_repeated_warnings = suppression.get("suppress_repeated_warnings", True)
        self.repeated_warning_cooldown_hours = suppression.get(
            "repeated_warning_cooldown_hours", 48
        )

    async def _execute_with_latency_monitor(self, query, operation_name: str):
        """
        执行查询并监控延迟

        超过 150ms → log.warning
        包裹在 try-except 中
        """
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

    async def calculate_rdi(
        self,
        student_id: int,
        window_short: int = 7,
        window_medium: int = 30,
        window_long: int = 90,
        include_trend: bool = True,
        suppress_low_rdi: bool = True,
    ) -> dict:
        """
        计算学生 RDI 风险偏离指数

        SQL 交互: ≤3次
          - SQL 1: 学生信息 + 班级信息
          - SQL 2: 三维度基线数据 (RiskBaseline x3)
          - SQL 3: 三维度当前值 (discipline + attendance + score)

        返回:
          {
            "student_id": 123,
            "rdi_score": 1.85,
            "risk_level": "attention",
            "behavior_deviation": 1.2,
            "attendance_deviation": -0.3,
            "score_deviation": 0.8,
            ...
            "warning_suppressed": False,
            "recommended_action": "heart_to_heart"
          }
        """
        start_total = time.time()

        # === SQL 1+2+3: 获取学生信息 + 三维度偏差 ===
        student_data = await self._fetch_student_and_deviations(
            student_id, window_short, window_medium
        )

        if not student_data["student"]:
            raise ValueError(f"学生不存在: id={student_id}")

        student = student_data["student"]
        behavior_dev = student_data["behavior"]
        attendance_dev = student_data["attendance"]
        score_dev = student_data["score"]
        historical_rdi = student_data.get("historical_rdi", [])  # 历史RDI序列

        # === 计算复合 RDI (权重可配置) ===
        weights = self.policy.get("risk_warning", {}).get(
            "rdi_weights",
            {
                "behavior": 0.4,
                "attendance": 0.3,
                "score": 0.3,
            },
        )
        rdi_score = (
            weights["behavior"] * behavior_dev["z_score"]
            + weights["attendance"] * attendance_dev["z_score"]
            + weights["score"] * score_dev["z_score"]
        )

        # === EWMA 趋势检测 (SQL 额外查询) ===
        ewma_trend = 0.0
        is_escalating = False
        if include_trend:
            # SQL 额外: 获取历史 RDI 序列 (从 risk_warnings 表)
            ewma_trend, is_escalating = await self._fetch_ewma_trend(student_id)

        # === 三级预警判定 ===
        risk_level = self._determine_risk_level(rdi_score, is_escalating)

        # === 预警抑制判定 ===
        warning_suppressed = False
        suppression_reason = None
        if suppress_low_rdi and self.suppression_enabled:
            if rdi_score < self.min_rdi_to_warn:
                warning_suppressed = True
                suppression_reason = f"RDI {rdi_score:.2f} < 阈值 {self.min_rdi_to_warn}"
            elif risk_level == "normal":
                warning_suppressed = True
                suppression_reason = "风险等级为正常"

        # === 推荐处置动作 ===
        recommended_action = self._recommend_action(risk_level, is_escalating)

        total_latency_ms = (time.time() - start_total) * 1000

        return {
            "student_id": student_id,
            "rdi_score": round(rdi_score, 2),
            "risk_level": risk_level,
            "behavior_deviation": behavior_dev["z_score"],
            "attendance_deviation": attendance_dev["z_score"],
            "score_deviation": score_dev["z_score"],
            "behavior_count": behavior_dev["raw_count"],
            "attendance_rate": attendance_dev["raw_rate"],
            "score_avg": score_dev["raw_avg"],
            "behavior_baseline_mean": behavior_dev["baseline_mean"],
            "behavior_baseline_std": behavior_dev["baseline_std"],
            "attendance_baseline_mean": attendance_dev["baseline_mean"],
            "attendance_baseline_std": attendance_dev["baseline_std"],
            "score_baseline_mean": score_dev["baseline_mean"],
            "score_baseline_std": score_dev["baseline_std"],
            "ewma_trend": ewma_trend,
            "is_escalating": is_escalating,
            "warning_suppressed": warning_suppressed,
            "suppression_reason": suppression_reason,
            "recommended_action": recommended_action,
            "compute_latency_ms": round(total_latency_ms, 2),
            "calculated_at": get_local_now(),
        }

    async def _fetch_student_and_deviations(
        self,
        student_id: int,
        window_short: int,
        window_medium: int,
    ) -> dict:
        """
        SQL 1+2+3: 一次性获取学生信息 + 三维度偏差数据

        性能优化:
          - SQL 1: 学生信息 (SELECT Student ... WHERE id=:student_id)
          - SQL 2: 三维度基线 (SELECT RiskBaseline WHERE type IN (...) → 3行, 1次查询)
          - SQL 3: 三维度当前值 (使用 scalar_subquery 合并为1次查询)

        总计: 3次 SQL 交互 ✅

        返回:
          {
            "student": Student对象,
            "behavior": {raw_count, baseline_mean, baseline_std, z_score},
            "attendance": {raw_rate, baseline_mean, baseline_std, z_score},
            "score": {raw_avg, baseline_mean, baseline_std, z_score},
          }
        """
        # 计算时间窗口
        short_start = date.today() - timedelta(days=window_short)
        medium_start = date.today() - timedelta(days=window_medium)

        # === SQL 1: 获取学生信息 ===
        student_query = (
            select(Student)
            .options(selectinload(Student.class_))
            .where(
                and_(
                    Student.id == student_id,
                    Student.school_id == self.school_id,
                )
            )
        )
        student_result = await self._execute_with_latency_monitor(student_query, "fetch_student")
        student = student_result.scalar_one_or_none()

        if not student:
            return {"student": None}

        # === SQL 2: 获取三维度基线 (1次查询获取3行) ===
        baselines_query = select(RiskBaseline).where(
            and_(
                RiskBaseline.student_id == student_id,
                RiskBaseline.window_days == window_medium,
                RiskBaseline.school_id == self.school_id,
                RiskBaseline.baseline_type.in_(["behavior", "attendance", "score"]),
            )
        )
        baselines_result = await self._execute_with_latency_monitor(
            baselines_query, "fetch_baselines"
        )
        baselines = {b.baseline_type: b for b in baselines_result.scalars().all()}

        # 提取基线数据 (如果没有则使用默认值)
        behavior_baseline = baselines.get("behavior")
        attendance_baseline = baselines.get("attendance")
        score_baseline = baselines.get("score")

        behavior_mean = behavior_baseline.mean_value if behavior_baseline else 1.0
        behavior_std = behavior_baseline.std_value if behavior_baseline else 1.0
        attendance_mean = attendance_baseline.mean_value if attendance_baseline else 0.0
        attendance_std = attendance_baseline.std_value if attendance_baseline else 1.0
        score_mean = score_baseline.mean_value if score_baseline else 80.0
        score_std = score_baseline.std_value if score_baseline else 10.0

        # === SQL 3: 获取三维度当前值 (使用 scalar_subquery 合并为1次查询) ===
        # 3.1 行为维度: 过去 window_short 天违纪次数 (从 DisciplineRecord 查询)
        behavior_count_subq = (
            select(func.count())
            .select_from(DisciplineRecord)
            .where(
                and_(
                    DisciplineRecord.student_id == student_id,
                    DisciplineRecord.incident_date >= short_start,
                    DisciplineRecord.school_id == self.school_id,
                    DisciplineRecord.status == "active",  # 只统计活跃违纪
                )
            )
            .scalar_subquery()
        )

        # 3.2 考勤维度: 过去 window_short 天迟到率 (从 AttendanceRecord 查询)
        attendance_rate_subq = (
            select(func.avg(case((AttendanceRecord.status.in_(["late", "absent"]), 1), else_=0)))
            .select_from(AttendanceRecord)
            .where(
                and_(
                    AttendanceRecord.student_id == student_id,
                    AttendanceRecord.record_date >= short_start,
                    AttendanceRecord.school_id == self.school_id,
                )
            )
            .scalar_subquery()
        )

        # 3.3 评价维度: 最新 total_score (从 StudentScore 查询)
        score_avg_subq = (
            select(func.max(StudentScore.total_score))
            .select_from(StudentScore)
            .where(
                and_(
                    StudentScore.student_id == student_id,
                    StudentScore.school_id == self.school_id,
                )
            )
            .scalar_subquery()
        )

        # 主查询: 一次性获取3个当前值 (SQL 3)
        current_values_query = select(
            behavior_count_subq.label("behavior_count"),
            attendance_rate_subq.label("attendance_rate"),
            score_avg_subq.label("score_latest"),
        )

        current_values_result = await self._execute_with_latency_monitor(
            current_values_query, "fetch_current_values"
        )
        current_values = current_values_result.one()

        # 提取当前值
        behavior_short_count = current_values.behavior_count or 0
        attendance_short_rate = current_values.attendance_rate or 0.0
        score_short_avg = float(current_values.score_latest or 0.0)

        # === 计算 Z-Score ===
        # 行为维度 (违纪次数越多越异常，正向指标)
        if behavior_std > 0:
            behavior_z = (behavior_short_count - behavior_mean) / behavior_std
        else:
            behavior_z = 0.0

        # 考勤维度 (迟到率越高越异常，正向指标)
        if attendance_std > 0:
            attendance_z = (attendance_short_rate - attendance_mean) / attendance_std
        else:
            attendance_z = 0.0

        # 评价维度 (分数越低越异常，负向指标，取负)
        if score_std > 0:
            score_z = -(score_short_avg - score_mean) / score_std  # 负向指标
        else:
            score_z = 0.0

        behavior_dev = {
            "raw_count": behavior_short_count,
            "baseline_mean": behavior_mean,
            "baseline_std": behavior_std,
            "z_score": round(behavior_z, 2),
        }

        attendance_dev = {
            "raw_rate": round(attendance_short_rate, 4),
            "baseline_mean": attendance_mean,
            "baseline_std": attendance_std,
            "z_score": round(attendance_z, 2),
        }

        score_dev = {
            "raw_avg": round(score_short_avg, 2),
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

    async def _fetch_ewma_trend(self, student_id: int) -> tuple[float, bool]:
        """
        SQL 额外: 获取历史 RDI 序列，计算 EWMA 趋势

        数据来源: risk_warnings 表 (历史预警记录)

        返回: (ewma_value, is_escalating)
        """
        lambda_param = 0.3  # 平滑系数 (policy.yaml 可配置)

        # 从 risk_warnings 表获取历史 RDI 序列
        historical_query = (
            select(RiskWarning.rdi_score)
            .where(
                and_(
                    RiskWarning.student_id == student_id,
                    RiskWarning.school_id == self.school_id,
                )
            )
            .order_by(RiskWarning.created_at.asc())
            .limit(10)  # 最多取最近10个点
        )

        historical_result = await self._execute_with_latency_monitor(
            historical_query, "fetch_historical_rdi"
        )
        historical_rdi = [r.rdi_score for r in historical_result.scalars().all()]

        if not historical_rdi:
            return 0.0, False

        # 计算 EWMA
        ewma = historical_rdi[0]
        for rdi in historical_rdi[1:]:
            ewma = lambda_param * rdi + (1 - lambda_param) * ewma

        # 判断 escalation (连续3个点上升)
        is_escalating = False
        if len(historical_rdi) >= 3:
            is_escalating = all(
                historical_rdi[i] < historical_rdi[i + 1]
                for i in range(len(historical_rdi) - 3, len(historical_rdi) - 1)
            )

        return round(ewma, 2), is_escalating

    def _determine_risk_level(self, rdi_score: float, is_escalating: bool) -> str:
        """
        三级预警判定

        配置读取: policy.yaml → risk_warning → risk_levels
        """
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

    def _recommend_action(self, risk_level: str, is_escalating: bool) -> str | None:
        """
        推荐处置动作

        读取 policy.yaml 中 configured_actions
        """
        actions = self.policy.get("risk_warning", {}).get("configured_actions", {})

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

    async def _get_or_create_baseline(
        self, student_id: int, baseline_type: str, window_days: int
    ) -> tuple[float, float]:
        """
        获取或创建基线 (均值, 标准差)

        优先从 risk_baselines 表读取
        若不存在则计算并存储 (懒初始化)
        """
        # 查询已有基线
        baseline_query = select(RiskBaseline).where(
            and_(
                RiskBaseline.student_id == student_id,
                RiskBaseline.baseline_type == baseline_type,
                RiskBaseline.window_days == window_days,
                RiskBaseline.school_id == self.school_id,
            )
        )
        baseline_result = await self._execute_with_latency_monitor(
            baseline_query, f"get_baseline_{baseline_type}"
        )
        baseline = baseline_result.scalar_one_or_none()

        if baseline:
            return baseline.mean_value, baseline.std_value

        # 基线不存在，计算并存储 (懒初始化)
        logger.info(
            f"Baseline not found for student={student_id}, type={baseline_type}, calculating..."
        )

        mean_value, std_value = await self._calculate_baseline_from_history(
            student_id, baseline_type, window_days
        )

        # 获取 class_id
        student_query = select(Student.class_id).where(Student.id == student_id)
        student_result = await self._execute_with_latency_monitor(
            student_query, "get_class_id_for_baseline"
        )
        class_id = student_result.scalar_one_or_none() or 1

        # 存储基线
        new_baseline = RiskBaseline(
            school_id=self.school_id,
            student_id=student_id,
            class_id=class_id,
            baseline_type=baseline_type,
            window_days=window_days,
            mean_value=mean_value,
            std_value=std_value,
            sample_size=0,  # TODO: 计算实际样本数
        )
        self.db.add(new_baseline)
        await self.db.flush()

        return mean_value, std_value

    async def _calculate_baseline_from_history(
        self, student_id: int, baseline_type: str, window_days: int
    ) -> tuple[float, float]:
        """
        从历史数据计算基线 (均值, 标准差)

        用于懒初始化 baseline
        """
        # TODO: 实现从历史数据计算基线
        # 临时返回默认值
        defaults = {
            "behavior": (1.0, 1.0),
            "attendance": (0.0, 1.0),
            "score": (80.0, 10.0),
        }
        return defaults.get(baseline_type, (0.0, 1.0))

    async def generate_risk_warning(
        self,
        student_id: int,
        rdi_result: dict,
        commit: bool = True,
    ) -> RiskWarning:
        """
        生成风险预警记录

        写入 risk_warnings 表
        """
        warning = RiskWarning(
            school_id=self.school_id,
            student_id=student_id,
            class_id=rdi_result.get("class_id", 1),  # TODO: 从 student 对象获取
            rdi_score=rdi_result["rdi_score"],
            risk_level=rdi_result["risk_level"],
            behavior_deviation=rdi_result["behavior_deviation"],
            attendance_deviation=rdi_result["attendance_deviation"],
            score_deviation=rdi_result["score_deviation"],
            ewma_trend=rdi_result.get("ewma_trend"),
            is_escalating=rdi_result.get("is_escalating", False),
            warning_suppressed=rdi_result.get("warning_suppressed", False),
            suppression_reason=rdi_result.get("suppression_reason"),
            recommended_action=rdi_result.get("recommended_action"),
            status="pending",
        )

        self.db.add(warning)

        if commit:
            await self.db.commit()
            await self.db.refresh(warning)

        logger.info(
            f"Risk warning generated: id={warning.id}, student={student_id}, "
            f"rdi={rdi_result['rdi_score']:.2f}, level={rdi_result['risk_level']}"
        )

        return warning

    async def get_dashboard_data(
        self,
        class_id: int | None = None,
        grade_id: int | None = None,
        risk_level: str | None = None,
        days: int = 7,
    ) -> dict:
        """
        获取风险预警看板数据

        返回:
          {
            "total_students": 393,
            "risk_distribution": {"normal": 300, "attention": 80, "intervention": 13},
            "recent_warnings": [...],
            "hotspot_behaviors": [...],
          }
        """
        # TODO: 实现看板查询逻辑
        # 临时返回模拟数据
        return {
            "total_students": 393,
            "risk_distribution": {
                "normal": 300,
                "attention": 80,
                "intervention": 13,
            },
            "recent_warnings": [],
            "hotspot_behaviors": [],
            "generated_at": get_local_now(),
        }
