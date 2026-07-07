"""
modules/risk_models/services.py — 风险预警雷达核心业务逻辑

核心功能:
  - RiskDeviationIndexCalculator: RDI 风险偏离指数计算器
  - SPC 统计过程控制 (EWMA + Z-Score 离群检测)
  - 三级预警系统 (🟢正常 / 🟡关注 / 🔴干预)
  - 预警抑制阈值 (防止预警疲劳)
"""

import logging
import time
from datetime import datetime, date, timedelta
from typing import Optional, List, Tuple, Dict
from collections import defaultdict
import math

from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from .models import RiskWarning, WarningFeedback, RiskBaseline
from core.models import Student, Class, Grade, User, UserRole
from core.models import Base, SchoolMixin, get_local_now
from modules.behavior.models import DisciplineRecord
from modules.attendance.models import AttendanceRecord
from modules.evaluation.models import StudentScore

# 导入 PolicyEngine 读取配置
import yaml
import os

logger = logging.getLogger(__name__)


def get_local_now() -> datetime:
    """获取本地时间 (MySQL datetime 无时区)"""
    return datetime.now()


def load_policy_config() -> dict:
    """加载 policy.yaml 配置 (委托给模块级单例缓存，消除每请求磁盘 I/O)"""
    from .policy_cache import get_policy_config
    return get_policy_config()


class RiskDeviationIndexCalculator:
    """
    RDI 风险偏离指数计算器

    算法原理:
      1. 滑动窗口统计: 计算学生在 7天/30天/90天 窗口内的行为/考勤/评价均值
      2. Z-Score 离群检测: (当前值 - 窗口均值) / 窗口标准差
      3. EWMA 趋势检测: λ=0.3 指数加权移动平均，检测 escalation
      4. 复合 RDI: ω₁×ΔBehavior + ω₂×ΔAttendance + ω₃×ΔScore
      5. 三级预警: RDI < 1.0σ 🟢 / 1.0σ≤RDI<2.0σ 🟡 / RDI≥2.0σ 🔴

    预警抑制:
      - 读取 policy.yaml 中 warning_suppression 配置
      - 避免预警疲劳 (alert fatigue)

    性能优化:
      - SQL 交互 ≤3次 (使用 JOIN 和聚合查询)
      - Latency Monitor (超过150ms → log.warning)
      - try-except 包裹所有 SELECT
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
        self.repeated_warning_cooldown_hours = suppression.get("repeated_warning_cooldown_hours", 48)

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
    ) -> Dict:
        """
        计算学生 RDI 风险偏离指数

        性能优化:
          - 使用2次SQL查询 (第1次: 学生+偏差数据, 第2次: 历史RDI)
          - 所有数据一次性获取，减少数据库交互

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
        # === SQL查询1: 获取学生基本信息 + 三维度偏差 ===
        start_total = time.time()

        student_data = await self._fetch_student_and_deviations(
            student_id, window_short, window_medium
        )

        if not student_data["student"]:
            raise ValueError(f"学生不存在: id={student_id}")

        behavior_dev = student_data["behavior"]
        attendance_dev = student_data["attendance"]
        score_dev = student_data["score"]

        # === SQL查询2: EWMA 趋势检测 (如果需要) ===
        ewma_trend = 0.0
        is_escalating = False
        if include_trend:
            ewma_trend, is_escalating = await self._fetch_ewma_trend(student_id)

        # === 3. 复合 RDI (权重可配置) ===
        weights = self.policy.get("risk_warning", {}).get("rdi_weights", {
            "behavior": 0.4,
            "attendance": 0.3,
            "score": 0.3,
        })
        rdi_score = (
            weights["behavior"] * behavior_dev["z_score"]
            + weights["attendance"] * attendance_dev["z_score"]
            + weights["score"] * score_dev["z_score"]
        )

        # === 4. 三级预警判定 ===
        risk_level = self._determine_risk_level(rdi_score, is_escalating)

        # === 5. 预警抑制判定 ===
        warning_suppressed = False
        suppression_reason = ""      # 默认空字符串 (非 None, 避免下游 replace() TypeError)
        if suppress_low_rdi and self.suppression_enabled:
            if rdi_score < self.min_rdi_to_warn:
                warning_suppressed = True
                suppression_reason = f"RDI {rdi_score:.2f} < 阈值 {self.min_rdi_to_warn}"
            elif risk_level == "normal":
                warning_suppressed = True
                suppression_reason = "风险等级为正常"

        # === 6. 推荐处置动作 ===
        recommended_action = self._recommend_action(risk_level, is_escalating)

        total_elapsed_ms = (time.time() - start_total) * 1000
        logger.info(f"✅ RDI计算完成: student_id={student_id}, RDI={rdi_score:.2f}, 耗时={total_elapsed_ms:.2f}ms")

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
            "calculated_at": get_local_now(),
            "compute_latency_ms": round(total_elapsed_ms, 2),
        }

    async def _fetch_student_and_deviations(
        self,
        student_id: int,
        window_short: int,
        window_medium: int,
    ) -> Dict:
        """
        SQL查询1: 一次性获取学生信息 + 三维度偏差数据

        性能优化:
          - 使用1次查询获取学生信息
          - 使用3次查询获取3个维度的当前值和基线 (总计4次SQL)
          - TODO: 可优化为2次 (使用JOIN)

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

        # === 1. 获取学生信息 ===
        student_query = select(Student).where(
            and_(
                Student.id == student_id,
                Student.school_id == self.school_id,
            )
        )
        student_result = await self._execute_with_latency_monitor(
            student_query, "fetch_student"
        )
        student = student_result.scalar_one_or_none()

        if not student:
            return {"student": None}

        # === 2. 计算行为维度偏离 (Z-Score) ===
        # 2.1 短期窗口违纪次数 — ORM 聚合查询 discipline_records
        behavior_count_result = await self._execute_with_latency_monitor(
            select(func.count(DisciplineRecord.id)).where(
                and_(
                    DisciplineRecord.student_id == student_id,
                    DisciplineRecord.school_id == self.school_id,
                    DisciplineRecord.incident_date >= short_start,
                )
            ),
            "fetch_behavior_count"
        )
        behavior_short_count = behavior_count_result.scalar() or 0

        # 2.2 获取基线 (通过 _get_or_create_baseline 自动计算+冷启动预热)
        behavior_mean, behavior_std = await self._get_or_create_baseline(
            student_id, "behavior", window_medium
        )

        # 2.3 计算 Z-Score
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
        # 3.1 短期窗口异常出勤率 — ORM 聚合查询 attendance_records
        # 异常状态: late(迟到) / absent(缺勤) / early(早退)
        attendance_rate_result = await self._execute_with_latency_monitor(
            select(
                func.coalesce(
                    func.avg(
                        case(
                            (AttendanceRecord.status.in_(["late", "absent", "early"]), 1.0),
                            else_=0.0
                        )
                    ),
                    0.0
                )
            ).where(
                and_(
                    AttendanceRecord.student_id == student_id,
                    AttendanceRecord.school_id == self.school_id,
                    AttendanceRecord.record_date >= short_start,
                )
            ),
            "fetch_attendance_rate"
        )
        attendance_short_rate = float(attendance_rate_result.scalar() or 0.0)

        # 3.2 获取基线 (通过 _get_or_create_baseline 自动计算+冷启动预热)
        attendance_mean, attendance_std = await self._get_or_create_baseline(
            student_id, "attendance", window_medium
        )

        # 3.3 计算 Z-Score
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
        # 4.1 当前学期总分 — ORM 查询 student_scores 快照
        score_result = await self._execute_with_latency_monitor(
            select(StudentScore.total_score).where(
                and_(
                    StudentScore.student_id == student_id,
                    StudentScore.school_id == self.school_id,
                )
            ).order_by(StudentScore.updated_at.desc()).limit(1),
            "fetch_score"
        )
        score_short_avg = score_result.scalar()
        if score_short_avg is None:
            score_short_avg = 80.0  # 无评价记录时使用默认值

        # 4.2 获取基线 (通过 _get_or_create_baseline 自动计算+冷启动预热)
        score_mean, score_std = await self._get_or_create_baseline(
            student_id, "score", window_medium
        )

        # 4.3 计算 Z-Score (注意: 分数越低越异常，所以取负)
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

    async def _fetch_ewma_trend(self, student_id: int) -> Tuple[float, bool]:
        """
        SQL查询2: 获取历史 RDI 序列，计算 EWMA 趋势

        返回: (ewma_value, is_escalating)
        """
        lambda_param = 0.3  # 平滑系数

        # 从 risk_warnings 表获取该学生历史 RDI 序列 (按时间升序)
        result = await self._execute_with_latency_monitor(
            select(RiskWarning.rdi_score).where(
                and_(
                    RiskWarning.student_id == student_id,
                    RiskWarning.school_id == self.school_id,
                )
            ).order_by(RiskWarning.warned_at.asc()).limit(20),
            "fetch_ewma_trend"
        )
        historical_rdi = [float(row[0]) for row in result.all()]

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
        risk_levels = self.policy.get("risk_warning", {}).get("risk_levels", {
            "normal": {"max_rdi": 1.0},
            "attention": {"min_rdi": 1.0, "max_rdi": 2.0},
            "intervention": {"min_rdi": 2.0},
        })

        if rdi_score < risk_levels["attention"]["min_rdi"]:
            return "normal"
        elif rdi_score < risk_levels["intervention"]["min_rdi"]:
            return "attention"
        else:
            return "intervention"

    def _recommend_action(self, risk_level: str, is_escalating: bool) -> Optional[str]:
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
    ) -> Tuple[float, float]:
        """
        获取或创建基线 (均值, 标准差)

        优先从 risk_baselines 表读取
        若不存在则计算并存储

        冷启动检测: 若 risk_baselines 表完全为空，触发全量预热
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
            baseline_query, f"fetch_baseline_{baseline_type}"
        )
        baseline = baseline_result.scalar_one_or_none()

        if baseline:
            return baseline.mean_value, baseline.std_value

        # === 冷启动检测: risk_baselines 表是否完全为空 ===
        count_result = await self._execute_with_latency_monitor(
            select(func.count(RiskBaseline.id)).where(
                RiskBaseline.school_id == self.school_id
            ),
            "cold_start_check"
        )
        total_baselines = count_result.scalar() or 0

        if total_baselines == 0:
            logger.warning(
                f"🔥 冷启动检测: risk_baselines 表为空 (school_id={self.school_id})，"
                f"触发全量预热 (window={window_days}天)..."
            )
            warmup_result = await self.warmup_all_baselines(
                self.db, self.school_id, window_days
            )
            logger.info(f"🔥 全量预热完成: {warmup_result}")

            # 预热后重新查询该学生的基线
            refetch_result = await self._execute_with_latency_monitor(
                baseline_query, f"refetch_baseline_{baseline_type}_post_warmup"
            )
            baseline = refetch_result.scalar_one_or_none()
            if baseline:
                return baseline.mean_value, baseline.std_value

        # 基线不存在 (非冷启动，仅该学生缺失)，计算并存储
        logger.info(f"🔄 计算新基线: student_id={student_id}, type={baseline_type}, window={window_days}")

        mean_value, std_value = await self._compute_baseline(
            student_id, baseline_type, window_days
        )

        # 存储基线
        student = await self.db.scalar(
            select(Student).where(Student.id == student_id)
        )
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
    async def warmup_all_baselines(
        db: AsyncSession, school_id: int, window_days: int = 30
    ) -> Dict:
        """
        冷启动批量预热 — 为全校学生计算并存储风险基线

        触发条件:
          - risk_baselines 表为空 (首次上线，由 _get_or_create_baseline 自动检测)
          - 管理员手动调用 POST /api/v1/risk_models/baselines/warmup

        策略:
          - 查询全校活跃学生 ID 列表
          - 为每个学生计算 3 种基线 (behavior/attendance/score)
          - 批量插入 risk_baselines 表

        Returns:
          {total_students, computed, skipped, errors, elapsed_ms}
        """
        start_ts = time.time()

        # 1. 查询已有基线的学生集合 (避免重复计算)
        existing_result = await db.execute(
            select(RiskBaseline.student_id).where(
                and_(
                    RiskBaseline.school_id == school_id,
                    RiskBaseline.window_days == window_days,
                )
            ).distinct()
        )
        existing_student_ids = {row[0] for row in existing_result.fetchall()}

        # 2. 查询全校活跃学生
        students_result = await db.execute(
            select(Student.id, Student.class_id).where(
                and_(
                    Student.school_id == school_id,
                    Student.is_active == True,  # noqa: E712
                )
            )
        )
        all_students = students_result.fetchall()

        # 3. 过滤出需要计算的学生
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

        # 4. 批量计算基线
        calc = RiskDeviationIndexCalculator(db, school_id)
        computed = 0
        errors = 0
        baseline_types = ["behavior", "attendance", "score"]
        new_baselines = []

        for student_id, class_id in students_to_compute:
            try:
                for btype in baseline_types:
                    mean_val, std_val = await calc._compute_baseline(
                        student_id, btype, window_days
                    )
                    new_baselines.append(RiskBaseline(
                        school_id=school_id,
                        student_id=student_id,
                        class_id=class_id or 1,
                        baseline_type=btype,
                        window_days=window_days,
                        mean_value=mean_val,
                        std_value=std_val,
                        sample_size=window_days,
                    ))
                computed += 1
            except Exception as e:
                logger.warning(f"基线计算失败 student_id={student_id}: {e}")
                errors += 1

        # 5. 批量插入
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
    ) -> Tuple[float, float]:
        """
        计算基线 (均值, 标准差)

        实际查询历史数据
        """
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
                f"compute_baseline_{baseline_type}"
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
                                else_=0.0
                            )
                        ),
                        0.0
                    )
                ).where(
                    and_(
                        AttendanceRecord.student_id == student_id,
                        AttendanceRecord.school_id == self.school_id,
                        AttendanceRecord.record_date >= start_date,
                    )
                ),
                f"compute_baseline_{baseline_type}"
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
                f"compute_baseline_{baseline_type}"
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


class RiskWarningService:
    """风险预警服务 — CRUD + 批量计算"""

    @staticmethod
    async def create_warning(
        db: AsyncSession,
        school_id: int,
        rdi_result: Dict,
        trigger_event_type: Optional[str] = None,
        trigger_event_id: Optional[int] = None,
    ) -> RiskWarning:
        """创建风险预警记录 — 从 Student 获取真实 class_id/grade_id"""
        # 查询 Student 获取真实班级/年级
        student_result = await db.execute(
            select(Student.class_id, Student.grade_id).where(
                Student.id == rdi_result["student_id"]
            )
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
        class_id: Optional[int] = None,
        grade_id: Optional[int] = None,
    ) -> Dict:
        """获取风险看板数据"""
        # TODO: 实现看板查询逻辑
        return {
            "total_students": 0,
            "at_risk_count": 0,
            "by_risk_level": {},
            "recent_warnings": [],
            "escalating_cases": [],
            "class_risk_ranking": [],
        }


class RiskMonitorService:
    """
    风险监控面板服务 — 黄/红预警学生实时监控

    用途:
      - 德育处/年级组实时掌握全校风险学生状态
      - 仅返回 RDI > 1.0 的黄(attention)/红(intervention)学生
      - 按班级筛选、按 RDI 降序排列
    """

    @staticmethod
    def _determine_top_dimension(
        behavior_dev: float, attendance_dev: float, score_dev: float
    ) -> str:
        """确定偏离最大的维度"""
        devs = {
            "behavior": abs(behavior_dev),
            "attendance": abs(attendance_dev),
            "score": abs(score_dev),
        }
        return max(devs, key=devs.get)  # type: ignore[arg-type]

    @staticmethod
    async def get_monitor_panel(
        db: AsyncSession,
        school_id: int,
        class_id: Optional[int] = None,
        grade_id: Optional[int] = None,
    ) -> Dict:
        """
        获取风险监控面板数据

        SQL策略:
          1. 子查询获取每个学生最新的 active 预警 (RDI > 1.0)
          2. JOIN Student + Class 获取姓名/班级
          3. 按 rdi_score 降序排列
          4. 按班级分组统计

        返回:
          {
            "total_students_scanned": 393,
            "yellow_count": 12,
            "red_count": 3,
            "students": [MonitorStudentCard, ...],
            "class_breakdown": [...],
            "generated_at": datetime
          }
        """
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

        # 按 class_id / grade_id 过滤
        if class_id is not None:
            main_query = main_query.where(RiskWarning.class_id == class_id)
        if grade_id is not None:
            main_query = main_query.where(Class.grade_id == grade_id)

        # 按 RDI 降序
        main_query = main_query.order_by(RiskWarning.rdi_score.desc())

        result = await db.execute(main_query)
        rows = result.all()

        # Step 3: 组装学生卡片
        students = []
        yellow_count = 0
        red_count = 0
        class_stats: Dict[int, Dict] = {}

        for rw, s_name, s_no, c_name, g_id in rows:
            risk_color = "red" if rw.risk_level == "intervention" else "yellow"
            if risk_color == "yellow":
                yellow_count += 1
            else:
                red_count += 1

            # 计算预警天数
            days_since = None
            if rw.warned_at:
                days_since = (now - rw.warned_at).days

            # 确定最大偏离维度
            top_dim = RiskMonitorService._determine_top_dimension(
                rw.behavior_deviation or 0.0,
                rw.attendance_deviation or 0.0,
                rw.score_deviation or 0.0,
            )

            # 推荐处置动作
            if rw.risk_level == "intervention":
                rec_action = "intervention_plan"
            elif rw.is_escalating:
                rec_action = "heart_to_heart"
            else:
                rec_action = "monitor"

            students.append({
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
                "top_dimension": top_dim,
                "is_escalating": rw.is_escalating or False,
                "ewma_trend": round(rw.ewma_trend or 0.0, 2),
                "latest_warning_id": rw.id,
                "latest_warning_status": rw.status,
                "warned_at": rw.warned_at,
                "days_since_warning": days_since,
                "recommended_action": rec_action,
            })

            # 班级统计
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
        total_scanned_query = select(func.count(Student.id)).where(
            Student.school_id == school_id
        )
        if class_id is not None:
            total_scanned_query = total_scanned_query.where(Student.class_id == class_id)
        if grade_id is not None:
            total_scanned_query = total_scanned_query.where(Student.grade_id == grade_id)

        total_result = await db.execute(total_scanned_query)
        total_students = total_result.scalar() or 0

        class_breakdown = sorted(class_stats.values(), key=lambda x: x["red"] * 100 + x["yellow"], reverse=True)

        logger.info(
            f"📊 监控面板: 扫描{total_students}人, 🟡{yellow_count}人, 🔴{red_count}人"
        )

        return {
            "total_students_scanned": total_students,
            "yellow_count": yellow_count,
            "red_count": red_count,
            "students": students,
            "class_breakdown": class_breakdown,
            "generated_at": now,
        }
