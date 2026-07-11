"""
modules/growth/pipeline.py — 成长档案核心聚合管道

BOSS 设计图纸落地：GrowthAggregationPipeline 类。
  - run_semester_snapshot(): 学期快照归一化引擎，五维雷达画像
  - inject_timeline_event(): 时光轴事件注入器，多态JSON流式写入

学业归一化数学模型（BOSS钦定公式）:
    Score_academic = α · Avg(exam) + β · (1 - Gap_critical_ratio) · 100

    α = 0.6  — 显性考试权重
    β = 0.4  — 隐性错题断层收敛率权重
    Gap_critical_ratio = critical_gaps / total_gaps

考勤扣分模型:
    Score_attendance = 100 - N_critical × 15 - N_warning × 5

行为/心理/活动 维度沿用 services.py 成熟逻辑，保持向后兼容。
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Student
from modules.growth.models import (
    GrowthDimension,
    GrowthPeriodicalSnapshot,
    GrowthTimelineEvent,
    EventSeverity,
)

logger = logging.getLogger(__name__)


class GrowthAggregationPipeline:
    """
    成长聚合管道 — 将跨模块异构数据归一化为五维雷达快照。

    数据源 (7路融合):
      1. grades.GradeRecord        → 学业: 考试均分
      2. error_funnel.KnowledgeGap → 学业: 错题断层收敛率
      3. attendance.AttendanceRecord → 考勤: CRITICAL/WARNING 事件计数
      4. behavior.DisciplineRecord → 行为: 违纪次数扣分
      5. habit_cards.HonorCard     → 行为: 表彰次数加分
      6. psych_profiles.PsychProfile → 心理: 风险等级映射
      7. research_activities.ActivityParticipant → 活动: 参与次数
    """

    # ═══════════════════════════════════════════════════════════════
    #  构造 & 配置
    # ═══════════════════════════════════════════════════════════════

    def __init__(
        self,
        db: AsyncSession,
        alpha: float = 0.6,
        beta: float = 0.4,
    ):
        """
        Args:
            db: 异步数据库会话
            alpha: 考试均分权重 (默认0.6)
            beta:  错题断层收敛率权重 (默认0.4)
        """
        self.db = db
        self.alpha = alpha
        self.beta = beta

    # ═══════════════════════════════════════════════════════════════
    #  公开 API — 学期快照归一化引擎
    # ═══════════════════════════════════════════════════════════════

    async def run_semester_snapshot(
        self,
        student_id: int,
        semester_label: str,
        school_id: Optional[int] = None,
        snapshot_type: str = "semester",
    ) -> GrowthPeriodicalSnapshot:
        """
        执行学期/月度快照归一化 — 五维雷达画像生成/更新。

        流程:
          1. 解析 school_id (显式传入 or 从 Student ORM 查询)
          2. 并行采集7路数据源
          3. 应用归一化公式计算5个维度得分
          4. 落库 (upsert: 存在则更新, 不存在则新建)
          5. 返回 GrowthPeriodicalSnapshot ORM 对象

        Args:
            student_id: 学生ID
            semester_label: 学期/月度标签, 如 "2025-2026-2" 或 "2026-07"
            school_id: 学校ID (不传则自动查询)
            snapshot_type: 快照类型 "semester" / "monthly"

        Returns:
            GrowthPeriodicalSnapshot ORM 对象
        """
        # ── Step 0: 解析 school_id ──
        if school_id is None:
            school_id = await self._resolve_school_id(student_id)
            if school_id is None:
                logger.error(f"[pipeline] 无法解析 student_id={student_id} 的 school_id, 跳过快照")
                raise ValueError(f"Student {student_id} not found or missing school_id")

        # ── Step 1: 采集7路数据 ──
        exam_avg, gap_critical_ratio, gap_metrics = await self._fetch_academic_data(
            student_id, school_id
        )
        attendance_critical, attendance_warning, att_metrics = await self._fetch_attendance_data(
            student_id, school_id
        )
        violation_count, honor_count, beh_metrics = await self._fetch_behavior_data(
            student_id, school_id
        )
        psych_score, psych_risk_level = await self._fetch_psychology_data(
            student_id, school_id
        )
        activity_count = await self._fetch_activity_data(student_id)

        # ── Step 2: 归一化五维得分 ──
        academic_score = self._compute_academic_score(exam_avg, gap_critical_ratio)
        attendance_score = self._compute_attendance_score(attendance_critical, attendance_warning)
        behavior_score = self._compute_behavior_score(violation_count, honor_count)
        psych_final = psych_score  # 心理维度已在上一步映射
        activity_score = self._compute_activity_score(activity_count)

        # clamp [0, 100]
        academic_score = round(min(100.0, max(0.0, academic_score)), 1)
        attendance_score = round(min(100.0, max(0.0, attendance_score)), 1)
        behavior_score = round(min(100.0, max(0.0, behavior_score)), 1)
        psych_final = round(min(100.0, max(0.0, psych_final)), 1)
        activity_score = round(min(100.0, max(0.0, activity_score)), 1)

        # ── Step 3: 汇总元数据 ──
        summary_metrics: Dict[str, Any] = {
            "exam_avg": round(exam_avg, 2) if exam_avg else None,
            "gap_critical_ratio": round(gap_critical_ratio, 4),
            "gap_total": gap_metrics.get("total_gaps", 0),
            "gap_critical": gap_metrics.get("critical_gaps", 0),
            "attendance_critical": attendance_critical,
            "attendance_warning": attendance_warning,
            "behavior_violations": violation_count,
            "honor_count": honor_count,
            "psych_risk_level": psych_risk_level,
            "activity_participations": activity_count,
            "formula": {
                "alpha": self.alpha,
                "beta": self.beta,
                "academic": f"{self.alpha}*{round(exam_avg,2) if exam_avg else 0}+{self.beta}*(1-{round(gap_critical_ratio,4)})*100={academic_score}",
            },
        }

        logger.info(
            f"[pipeline] 快照计算完成 student={student_id} semester={semester_label} "
            f"academic={academic_score} attendance={attendance_score} "
            f"behavior={behavior_score} psych={psych_final} activity={activity_score}"
        )

        # ── Step 4: 落库 (upsert) ──
        snapshot = await self._upsert_snapshot(
            school_id=school_id,
            student_id=student_id,
            snapshot_type=snapshot_type,
            period_label=semester_label,
            academic_score=academic_score,
            attendance_score=attendance_score,
            behavior_score=behavior_score,
            psych_score=psych_final,
            activity_score=activity_score,
            summary_metrics=summary_metrics,
        )

        return snapshot

    # ═══════════════════════════════════════════════════════════════
    #  公开 API — 时光轴事件注入
    # ═══════════════════════════════════════════════════════════════

    async def inject_timeline_event(
        self,
        event_data: Dict[str, Any],
    ) -> GrowthTimelineEvent:
        """
        注入一条成长时光轴事件 — 多态JSON流式写入。

        event_data 必填字段:
            school_id: int
            student_id: int
            dimension: str (GrowthDimension 枚举值)
            event_type: str (如 "hw_missing", "gap_critical", "discipline_punish")
            title: str (显示标题)
            occurred_at: datetime

        event_data 可选字段:
            severity: str (EventSeverity 枚举值, 默认 "info")
            payload: dict (多态结构化载荷)
            reporter_id: int (记录人ID, 系统触发为None)
        """
        # 校验必填字段
        required = ["school_id", "student_id", "dimension", "event_type", "title", "occurred_at"]
        for field in required:
            if field not in event_data:
                raise ValueError(f"inject_timeline_event 缺少必填字段: {field}")

        # 校验 dimension 枚举
        dimension = event_data["dimension"]
        valid_dims = {d.value for d in GrowthDimension}
        if dimension not in valid_dims:
            raise ValueError(
                f"无效 dimension='{dimension}', 必须为 {valid_dims}"
            )

        # 校验 severity 枚举
        severity = event_data.get("severity", EventSeverity.INFO.value)
        valid_severities = {s.value for s in EventSeverity}
        if severity not in valid_severities:
            raise ValueError(
                f"无效 severity='{severity}', 必须为 {valid_severities}"
            )

        event = GrowthTimelineEvent(
            school_id=event_data["school_id"],
            student_id=event_data["student_id"],
            dimension=dimension,
            severity=severity,
            event_type=event_data["event_type"],
            title=event_data["title"],
            occurred_at=event_data["occurred_at"],
            payload=event_data.get("payload"),
            reporter_id=event_data.get("reporter_id"),
        )
        self.db.add(event)
        await self.db.flush()

        logger.info(
            f"[pipeline] 时光轴事件注入 student={event.student_id} "
            f"dim={dimension} severity={severity} type={event.event_type}"
        )

        return event

    # ═══════════════════════════════════════════════════════════════
    #  归一化公式 — BOSS 钦定
    # ═══════════════════════════════════════════════════════════════

    def _compute_academic_score(
        self,
        exam_avg: float,
        gap_critical_ratio: float,
    ) -> float:
        """
        学业归一化 — BOSS 钦定公式:

            Score = α · Avg(exam) + β · (1 - Gap_critical_ratio) · 100

        当考试数据为空时，使用断层健康度作为 fallback。
        当两者都为空时，返回默认值 60.0 (中性偏保守)。
        """
        has_exam = exam_avg is not None and exam_avg > 0
        has_gap = gap_critical_ratio is not None and gap_critical_ratio >= 0

        if has_exam and has_gap:
            # 完整公式
            score = (self.alpha * exam_avg) + (self.beta * (1.0 - gap_critical_ratio) * 100)
        elif has_exam:
            # 只有考试均分，断层数据缺失 → 仅用考试分
            score = exam_avg
        elif has_gap:
            # 只有断层数据，考试缺失 → 用断层健康度
            score = (1.0 - gap_critical_ratio) * 100
        else:
            # 两者都缺失 → 保守中性值
            score = 60.0

        return score

    def _compute_attendance_score(
        self,
        critical_count: int,
        warning_count: int,
    ) -> float:
        """
        考勤归一化 — 100基准分扣分制:

            Score = 100 - N_critical × 15 - N_warning × 5

        CRITICAL 事件 (如旷课/严重迟到) 扣15分
        WARNING 事件 (如轻度迟到/请假未批) 扣5分
        下限为 0 分
        """
        score = 100.0 - (critical_count * 15) - (warning_count * 5)
        return max(0.0, score)

    def _compute_behavior_score(
        self,
        violation_count: int,
        honor_count: int,
    ) -> float:
        """
        行为归一化 — 100基准分扣分+加分:

            Score = 100 - violations × 5 + honors × 3

        违纪每次扣5分，表彰每次加3分，clamp [0, 100]
        """
        score = 100.0 - (violation_count * 5) + (honor_count * 3)
        return score

    def _compute_activity_score(self, activity_count: int) -> float:
        """
        活动归一化 — 参与度递增:

            Score = min(participations × 10, 100)

        每次活动参与加10分，上限100
        """
        return min(100.0, float(activity_count * 10))

    # ═══════════════════════════════════════════════════════════════
    #  数据采集层 — 7路跨模块查询 (异常兜底，单路失败不影响全局)
    # ═══════════════════════════════════════════════════════════════

    async def _resolve_school_id(self, student_id: int) -> Optional[int]:
        """从 Student ORM 查询 school_id"""
        try:
            result = await self.db.execute(
                select(Student.school_id).where(Student.id == student_id)
            )
            return result.scalar()
        except Exception as e:
            logger.error(f"[pipeline] 查询学生 school_id 失败: {e}")
            return None

    async def _fetch_academic_data(
        self, student_id: int, school_id: int
    ) -> Tuple[float, float, Dict[str, Any]]:
        """
        学业数据采集 — 考试均分 + 错题断层收敛率

        Returns:
            (exam_avg, gap_critical_ratio, metrics_dict)
        """
        exam_avg: float = 0.0
        gap_critical_ratio: float = 0.0
        metrics: Dict[str, Any] = {"total_gaps": 0, "critical_gaps": 0}

        # ── 1a. 考试均分 ──
        try:
            from modules.grades.models import GradeRecord

            result = await self.db.execute(
                select(func.avg(GradeRecord.score)).where(
                    GradeRecord.student_id == student_id,
                    GradeRecord.school_id == school_id,
                )
            )
            val = result.scalar()
            if val:
                exam_avg = float(val)
        except Exception as e:
            logger.warning(f"[pipeline] 学业-考试均分采集失败 student={student_id}: {e}")

        # ── 1b. 错题断层 ──
        try:
            from modules.error_funnel.models import KnowledgeGap

            # critical 断层数
            crit_result = await self.db.execute(
                select(func.count(KnowledgeGap.id)).where(
                    KnowledgeGap.student_id == student_id,
                    KnowledgeGap.gap_level == "critical",
                )
            )
            critical_gaps = crit_result.scalar() or 0

            # 总斷层数
            total_result = await self.db.execute(
                select(func.count(KnowledgeGap.id)).where(
                    KnowledgeGap.student_id == student_id
                )
            )
            total_gaps = total_result.scalar() or 0

            metrics["total_gaps"] = total_gaps
            metrics["critical_gaps"] = critical_gaps

            if total_gaps > 0:
                gap_critical_ratio = critical_gaps / total_gaps
            else:
                # 无错题数据 → 收敛率=0 (满分健康度)
                gap_critical_ratio = 0.0

        except Exception as e:
            logger.warning(f"[pipeline] 学业-错题断层采集失败 student={student_id}: {e}")
            # fallback: 不影响考试均分，断层比率设为0
            gap_critical_ratio = 0.0

        return exam_avg, gap_critical_ratio, metrics

    async def _fetch_attendance_data(
        self, student_id: int, school_id: int
    ) -> Tuple[int, int, Dict[str, Any]]:
        """
        考勤数据采集 — CRITICAL/WARNING 事件计数

        考勤记录中 status 字段:
          - "absent" (旷课) → CRITICAL
          - "late" (迟到) / "early_leave" (早退) → WARNING
          - "present" (正常) → 不计

        Returns:
            (critical_count, warning_count, metrics_dict)
        """
        critical_count = 0
        warning_count = 0

        try:
            from modules.attendance.models import AttendanceRecord

            # CRITICAL: 旷课
            crit_result = await self.db.execute(
                select(func.count(AttendanceRecord.id)).where(
                    AttendanceRecord.student_id == student_id,
                    AttendanceRecord.school_id == school_id,
                    AttendanceRecord.status == "absent",
                )
            )
            critical_count = crit_result.scalar() or 0

            # WARNING: 迟到 + 早退
            warn_result = await self.db.execute(
                select(func.count(AttendanceRecord.id)).where(
                    AttendanceRecord.student_id == student_id,
                    AttendanceRecord.school_id == school_id,
                    AttendanceRecord.status.in_(["late", "early"]),
                )
            )
            warning_count = warn_result.scalar() or 0

        except Exception as e:
            logger.warning(f"[pipeline] 考勤数据采集失败 student={student_id}: {e}")

        metrics = {
            "attendance_critical": critical_count,
            "attendance_warning": warning_count,
            "total_absent": critical_count + warning_count,
        }
        return critical_count, warning_count, metrics

    async def _fetch_behavior_data(
        self, student_id: int, school_id: int
    ) -> Tuple[int, int, Dict[str, Any]]:
        """
        行为数据采集 — 违纪次数 + 表彰次数

        Returns:
            (violation_count, honor_count, metrics_dict)
        """
        violation_count = 0
        honor_count = 0

        # ── 违纪 ──
        try:
            from modules.behavior.models import DisciplineRecord

            result = await self.db.execute(
                select(func.count(DisciplineRecord.id)).where(
                    DisciplineRecord.student_id == student_id,
                    DisciplineRecord.school_id == school_id,
                )
            )
            violation_count = result.scalar() or 0
        except Exception as e:
            logger.warning(f"[pipeline] 行为-违纪采集失败 student={student_id}: {e}")

        # ── 表彰 ──
        try:
            from modules.habit_cards.models import HonorCard

            result = await self.db.execute(
                select(func.count(HonorCard.id)).where(
                    HonorCard.student_id == student_id,
                    HonorCard.school_id == school_id,
                )
            )
            honor_count = result.scalar() or 0
        except Exception as e:
            logger.warning(f"[pipeline] 行为-表彰采集失败 student={student_id}: {e}")

        metrics = {
            "violations": violation_count,
            "honors": honor_count,
        }
        return violation_count, honor_count, metrics

    async def _fetch_psychology_data(
        self, student_id: int, school_id: int
    ) -> Tuple[float, Optional[str]]:
        """
        心理数据采集 — psych_profiles 风险等级映射

        Returns:
            (psych_score, risk_level_str)
        """
        # 默认值: 无心理数据时给 90.0 (略低于满分, 表示"未评估")
        psych_score = 90.0
        risk_level_str: Optional[str] = None

        try:
            from modules.psych_profiles.models import PsychProfile

            result = await self.db.execute(
                select(PsychProfile.risk_level)
                .where(
                    PsychProfile.student_id == student_id,
                    PsychProfile.school_id == school_id,
                )
                .order_by(desc(PsychProfile.updated_at))
                .limit(1)
            )
            risk_level = result.scalar()

            if risk_level:
                risk_level_str = risk_level.lower() if isinstance(risk_level, str) else str(risk_level).lower()
                # 双轨风险等级映射 (兼容 green/yellow/orange/red 和 low/medium/high)
                risk_map = {
                    "green": 100.0,
                    "yellow": 80.0,
                    "orange": 60.0,
                    "red": 40.0,
                    "low": 100.0,
                    "medium": 80.0,
                    "high": 60.0,
                }
                psych_score = risk_map.get(risk_level_str, 90.0)

        except Exception as e:
            logger.warning(f"[pipeline] 心理数据采集失败 student={student_id}: {e}")

        return psych_score, risk_level_str

    async def _fetch_activity_data(self, student_id: int) -> int:
        """
        活动数据采集 — 教研/课外活动参与次数

        Returns:
            activity_count
        """
        try:
            from modules.research_activities.models import ActivityParticipant

            result = await self.db.execute(
                select(func.count(ActivityParticipant.id)).where(
                    ActivityParticipant.student_id == student_id
                )
            )
            return result.scalar() or 0
        except Exception as e:
            logger.warning(f"[pipeline] 活动数据采集失败 student={student_id}: {e}")
            return 0

    # ═══════════════════════════════════════════════════════════════
    #  落库层 — Upsert 快照
    # ═══════════════════════════════════════════════════════════════

    async def _upsert_snapshot(
        self,
        school_id: int,
        student_id: int,
        snapshot_type: str,
        period_label: str,
        academic_score: float,
        attendance_score: float,
        behavior_score: float,
        psych_score: float,
        activity_score: float,
        summary_metrics: Dict[str, Any],
    ) -> GrowthPeriodicalSnapshot:
        """
        Upsert 快照 — 存在则更新, 不存在则新建。

        匹配键: (student_id, snapshot_type, period_label)
        """
        existing_result = await self.db.execute(
            select(GrowthPeriodicalSnapshot).where(
                GrowthPeriodicalSnapshot.student_id == student_id,
                GrowthPeriodicalSnapshot.snapshot_type == snapshot_type,
                GrowthPeriodicalSnapshot.period_label == period_label,
            )
        )
        snap = existing_result.scalar_one_or_none()

        if snap:
            # 更新已有快照
            snap.academic_score = academic_score
            snap.attendance_score = attendance_score
            snap.behavior_score = behavior_score
            snap.psych_score = psych_score
            snap.activity_score = activity_score
            snap.summary_metrics = summary_metrics
        else:
            # 新建快照
            snap = GrowthPeriodicalSnapshot(
                school_id=school_id,
                student_id=student_id,
                snapshot_type=snapshot_type,
                period_label=period_label,
                academic_score=academic_score,
                attendance_score=attendance_score,
                behavior_score=behavior_score,
                psych_score=psych_score,
                activity_score=activity_score,
                summary_metrics=summary_metrics,
            )
            self.db.add(snap)

        await self.db.flush()
        await self.db.refresh(snap)
        return snap
