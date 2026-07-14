"""
modules/growth/analytics.py — 动态五维降维引擎 + 德育量化闭环

═══════════════════════════════════════════════════════════════════════
  数学模型
═══════════════════════════════════════════════════════════════════════

1. 时间衰减 (Time-Decay):
   V_e(T) = Severity(e) × e^(-λ × Δt)
   λ = 0.05 → 14 天后事件影响力衰减 50%

2. 13路 → 5维 降维映射矩阵 M:
   每路信号的残存能量乘以映射权重，累加到对应维度的扣分累加器。

3. Sigmoid 归一化:
   S_d = 100 / (1 + e^(k × (penalty - threshold)))
   k = 0.1, threshold = 30
   → penalty=0 时 S≈95, penalty=30 时 S=50, penalty=60 时 S≈5

4. 德育闭环:
   分值跌破警戒线 → 自动写入 MoralEducationLedger → 班主任干预 → 解除挂牌

═══════════════════════════════════════════════════════════════════════
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Any

from core.models import Base
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    and_,
    desc,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  表3: 德育量化自动流水账 — 闭环工单
# ═══════════════════════════════════════════════════════════════


class MoralEducationLedger(Base):
    """
    德育量化工单 — 动态降维引擎自动挂牌/解除的持久化记录。

    生命周期: AUTO_WARN/RED_ZONE → RESOLVED (班主任干预后)
    防刷机制: 同一学生+维度 24h 内不重复挂牌
    """

    __tablename__ = "growth_moral_education_ledger"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, nullable=False, index=True)
    student_id = Column(Integer, nullable=False, index=True)

    # 哪个维度触发了告警: moral / academic / psych / habit / practice
    dimension_name = Column(String(50), nullable=False)
    # 触发时的实时得分
    trigger_score = Column(Float, nullable=False)
    # AUTO_WARN (跌破警戒线) / RED_ZONE (跌破红线)
    action_type = Column(String(50), nullable=False, default="AUTO_WARN")

    description = Column(String(500), nullable=True)
    # 五维全量快照（便于回溯触发时的完整状态）
    score_snapshot = Column(Text, nullable=True)

    # 闭环状态
    is_resolved = Column(Boolean, default=False, index=True)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, nullable=True)
    resolution_note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_moral_ledger_school_student", "school_id", "student_id"),
        Index("ix_moral_ledger_unresolved", "is_resolved", "created_at"),
    )


# ═══════════════════════════════════════════════════════════════
#  DynamicGrowthEngine — 动态五维降维引擎
# ═══════════════════════════════════════════════════════════════


class DynamicGrowthEngine:
    """
    将 13 路全息时序事件流降维为 5 维雷达得分。

    五维 (BOSS 钦定):
      moral     — 道德品行 (违纪/处分/行为基线)
      academic  — 学业发展 (考试/断层/作业)
      psych     — 身心健康 (心理风险/RDI偏差)
      habit     — 行为习惯 (考勤/迟到/作业习惯)
      practice  — 综合实践 (活动参与/表彰/快照基线)
    """

    # ── 数学参数 ──
    LAMBDA_DECAY = 0.05  # 14天半衰期
    SIGMOID_THRESHOLD = 30.0  # penalty=30时 Sigmoid=50
    SIGMOID_K = 0.1  # Sigmoid陡度
    LOOKBACK_DAYS = 90  # 数据回溯窗口

    # ── 13路 → 5维 映射权重矩阵 ──
    # key = 数据源标识, value = {维度: 权重}
    MAP_MATRIX = {
        "attendance": {"habit": 0.8},
        "discipline": {"moral": 0.7, "habit": 0.3},
        "punishment": {"moral": 0.9},
        "academic_trend": {"academic": 0.8},
        "rdi_warning": {"psych": 0.6, "habit": 0.4},
        "psych_factors": {"psych": 0.9},
        "growth_timeline": {"moral": 0.3, "habit": 0.4, "practice": 0.3},
        "periodical_snap": {"moral": 0.4, "academic": 0.4, "practice": 0.2},
        "homework": {"academic": 0.7, "habit": 0.3},
        "error_funnel": {"academic": 0.9},
        "psych_deep_risk": {"psych": 1.0},
    }

    # ── 事件烈度权重 ──
    SEVERITY = {
        "absent": 5.0,
        "late": 2.0,
        "early": 2.0,
        "discipline": 4.0,
        "punishment": 8.0,
        "gap_critical": 4.0,
        "gap_watch": 1.0,
        "psych_red": 10.0,
        "psych_yellow": 5.0,
        "hw_missing": 2.0,
        "timeline_critical": 5.0,
        "timeline_warning": 2.0,
        "timeline_bonus": -3.0,  # 负值 = 正向加分，抵扣 penalty
    }

    # ── 德育闭环警戒线 ──
    ALERT_THRESHOLDS = {
        "moral": {"warn": 60.0, "red": 50.0},
        "academic": {"warn": 55.0, "red": 40.0},
        "psych": {"warn": 60.0, "red": 45.0},
        "habit": {"warn": 65.0, "red": 50.0},
        "practice": {"warn": 50.0, "red": 35.0},
    }

    # ═══════════════════════════════════════════════════════════
    #  公开 API
    # ═══════════════════════════════════════════════════════════

    @classmethod
    async def compute_five_dimensions(
        cls,
        db: AsyncSession,
        student_id: int,
        school_id: int,
    ) -> dict[str, Any]:
        """
        全息五维雷达计算 — 13路数据采集 → 时间衰减 → 降维映射 → Sigmoid归一化

        Returns:
            {
                "scores": {"moral": 85.2, "academic": 72.1, ...},
                "penalties": {"moral": 12.3, ...},  # 原始扣分（调试用）
                "sources": {"attendance": {...}, ...},  # 各路数据摘要
                "alerts": [...],  # 触发的德育工单
            }
        """
        now = datetime.utcnow()
        lookback = now - timedelta(days=cls.LOOKBACK_DAYS)

        # 初始化五维扣分累加器
        penalties = {"moral": 0.0, "academic": 0.0, "psych": 0.0, "habit": 0.0, "practice": 0.0}
        sources: dict[str, Any] = {}

        # ── 路1: 考勤离子流 ──
        att_data = await cls._fetch_attendance(db, student_id, school_id, lookback)
        sources["attendance"] = att_data
        for rec in att_data["records"]:
            sev = cls.SEVERITY.get(rec["status"], 1.0)
            decayed = cls._time_decay(rec["occurred_at"], sev)
            for dim, weight in cls.MAP_MATRIX["attendance"].items():
                penalties[dim] += decayed * weight

        # ── 路2+3: 违纪 + 处分 ──
        beh_data = await cls._fetch_behavior(db, student_id, school_id, lookback)
        sources["behavior"] = beh_data
        for rec in beh_data["violations"]:
            sev = cls.SEVERITY["discipline"]
            decayed = cls._time_decay(rec["occurred_at"], sev)
            for dim, weight in cls.MAP_MATRIX["discipline"].items():
                penalties[dim] += decayed * weight
        for rec in beh_data["punishments"]:
            sev = cls.SEVERITY["punishment"]
            decayed = cls._time_decay(rec["occurred_at"], sev)
            for dim, weight in cls.MAP_MATRIX["punishment"].items():
                penalties[dim] += decayed * weight

        # ── 路5: 学业趋势 ──
        acad_data = await cls._fetch_academic(db, student_id, school_id)
        sources["academic"] = acad_data
        if acad_data["exam_avg"] is not None:
            avg = acad_data["exam_avg"]
            if avg < 60:
                # 低于及格线 → 学业 penalty
                decayed = cls._time_decay(now, (60 - avg) * 0.5)
                penalties["academic"] += decayed * cls.MAP_MATRIX["academic_trend"]["academic"]
            elif avg >= 85:
                # 优秀 → bonus (负 penalty)
                penalties["academic"] -= (avg - 85) * 0.3

        # ── 路12: 错题漏斗 ──
        gap_data = acad_data.get("gaps", {})
        for gap in gap_data.get("active_critical", []):
            sev = cls.SEVERITY["gap_critical"]
            decayed = cls._time_decay(gap.get("updated_at", now), sev)
            penalties["academic"] += decayed * cls.MAP_MATRIX["error_funnel"]["academic"]

        # ── 路11: 作业流 ──
        hw_data = await cls._fetch_homework(db, student_id, school_id, lookback)
        sources["homework"] = hw_data
        for rec in hw_data["missing"]:
            sev = cls.SEVERITY["hw_missing"]
            decayed = cls._time_decay(rec.get("due_date", now), sev)
            for dim, weight in cls.MAP_MATRIX["homework"].items():
                penalties[dim] += decayed * weight

        # ── 路7+13: 心理风险 ──
        psych_data = await cls._fetch_psych(db, student_id, school_id)
        sources["psych"] = psych_data
        risk = psych_data.get("risk_level", "").lower()
        if risk == "red":
            decayed = cls._time_decay(psych_data.get("updated_at", now), cls.SEVERITY["psych_red"])
            penalties["psych"] += decayed * cls.MAP_MATRIX["psych_deep_risk"]["psych"]
        elif risk == "yellow":
            decayed = cls._time_decay(
                psych_data.get("updated_at", now), cls.SEVERITY["psych_yellow"]
            )
            penalties["psych"] += decayed * cls.MAP_MATRIX["psych_factors"]["psych"]

        # ── 路8+9: 时光轴事件 (含 Redis 实时注入) ──
        tl_data = await cls._fetch_timeline_events(db, student_id, school_id, lookback)
        sources["timeline"] = tl_data
        for ev in tl_data["events"]:
            sev_key = f"timeline_{ev['severity']}"
            sev = cls.SEVERITY.get(sev_key, 0.0)
            decayed = cls._time_decay(ev["occurred_at"], sev)
            for dim, weight in cls.MAP_MATRIX["growth_timeline"].items():
                penalties[dim] += decayed * weight

        # ── 路10: 阶段性快照基线 ──
        snap_data = await cls._fetch_latest_snapshot(db, student_id, school_id)
        sources["snapshot"] = snap_data
        if snap_data:
            snap_map = {
                "behavior_score": "moral",
                "academic_score": "academic",
                "attendance_score": "habit",
                "psych_score": "psych",
                "activity_score": "practice",
            }
            for snap_field, dim in snap_map.items():
                snap_val = snap_data.get(snap_field)
                if snap_val is not None and snap_val < 60:
                    # 快照低于60 → 加 penalty
                    penalty_add = (60 - snap_val) * 0.5
                    weight = cls.MAP_MATRIX["periodical_snap"].get(dim, 0.4)
                    penalties[dim] += penalty_add * weight

        # ── 综合实践维度补全: 活动参与 ──
        act_count = await cls._fetch_activity_count(db, student_id)
        sources["activity_count"] = act_count
        if act_count == 0:
            penalties["practice"] += 10.0  # 无活动 → penalty
        else:
            penalties["practice"] -= min(act_count * 2.0, 15.0)  # 有活动 → bonus

        # ── Sigmoid 归一化 ──
        scores = {}
        for dim, penalty in penalties.items():
            # penalty 可能为负（大量 bonus） → clamp >= 0
            penalty = max(0.0, penalty)
            scores[dim] = cls._sigmoid_normalize(penalty)

        # ── 德育闭环检查 ──
        alerts = await cls._check_moral_ledger_loop(db, student_id, school_id, scores)

        return {
            "scores": scores,
            "penalties": {k: round(v, 2) for k, v in penalties.items()},
            "sources": sources,
            "alerts": alerts,
        }

    @classmethod
    async def get_ledger_entries(
        cls,
        db: AsyncSession,
        school_id: int,
        student_id: int | None = None,
        unresolved_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """查询德育工单列表"""
        conditions = [MoralEducationLedger.school_id == school_id]
        if student_id is not None:
            conditions.append(MoralEducationLedger.student_id == student_id)
        if unresolved_only:
            conditions.append(MoralEducationLedger.is_resolved == False)

        # 总数
        count_stmt = select(func.count(MoralEducationLedger.id)).where(and_(*conditions))
        total = (await db.execute(count_stmt)).scalar() or 0

        # 分页查询
        stmt = (
            select(MoralEducationLedger)
            .where(and_(*conditions))
            .order_by(desc(MoralEducationLedger.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        items = result.scalars().all()

        return {
            "items": [
                {
                    "id": e.id,
                    "student_id": e.student_id,
                    "dimension_name": e.dimension_name,
                    "trigger_score": e.trigger_score,
                    "action_type": e.action_type,
                    "description": e.description,
                    "score_snapshot": e.score_snapshot,
                    "is_resolved": e.is_resolved,
                    "resolved_at": e.resolved_at,
                    "resolved_by": e.resolved_by,
                    "resolution_note": e.resolution_note,
                    "created_at": e.created_at,
                }
                for e in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @classmethod
    async def resolve_ledger_entry(
        cls,
        db: AsyncSession,
        ledger_id: int,
        school_id: int,
        resolved_by: int,
        note: str = "",
    ) -> MoralEducationLedger | None:
        """解除德育工单挂牌"""
        stmt = select(MoralEducationLedger).where(
            and_(
                MoralEducationLedger.id == ledger_id,
                MoralEducationLedger.school_id == school_id,
            )
        )
        result = await db.execute(stmt)
        entry = result.scalar_one_or_none()
        if not entry:
            return None
        if entry.is_resolved:
            return entry  # 已解除，幂等

        entry.is_resolved = True
        entry.resolved_at = datetime.utcnow()
        entry.resolved_by = resolved_by
        entry.resolution_note = note
        await db.commit()
        await db.refresh(entry)
        return entry

    # ═══════════════════════════════════════════════════════════
    #  数学工具
    # ═══════════════════════════════════════════════════════════

    @classmethod
    def _time_decay(cls, occurred_at: datetime, severity: float) -> float:
        """V_e(T) = Severity × e^(-λ × Δt)"""
        if occurred_at is None:
            return severity
        if isinstance(occurred_at, str):
            try:
                occurred_at = datetime.fromisoformat(occurred_at.replace("Z", ""))
            except Exception:
                return severity
        days = max(0, (datetime.utcnow() - occurred_at).days)
        return severity * math.exp(-cls.LAMBDA_DECAY * days)

    @classmethod
    def _sigmoid_normalize(cls, penalty: float) -> float:
        """
        S_d = 100 / (1 + e^(k × (penalty - threshold)))

        penalty=0  → 95.3 (优秀)
        penalty=15 → 81.8 (良好)
        penalty=30 → 50.0 (中位)
        penalty=50 → 7.6  (危险)
        """
        score = 100.0 / (1.0 + math.exp(cls.SIGMOID_K * (penalty - cls.SIGMOID_THRESHOLD)))
        return round(max(10.0, min(100.0, score)), 1)

    # ═══════════════════════════════════════════════════════════
    #  德育闭环
    # ═══════════════════════════════════════════════════════════

    @classmethod
    async def _check_moral_ledger_loop(
        cls,
        db: AsyncSession,
        student_id: int,
        school_id: int,
        scores: dict[str, float],
    ) -> list[dict[str, Any]]:
        """
        闭环看守: 分值跌破警戒线 → 自动挂牌德育工单
        防刷: 同一学生+维度 24h 内不重复挂牌
        """
        alerts = []
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=24)

        for dim, thresholds in cls.ALERT_THRESHOLDS.items():
            score = scores.get(dim, 100.0)
            warn_line = thresholds["warn"]
            red_line = thresholds["red"]

            if score >= warn_line:
                continue  # 安全，不需要挂牌

            # 判定动作类型
            action_type = "RED_ZONE" if score < red_line else "AUTO_WARN"

            # 24h 防刷: 查询近期同类未解除工单
            dup_stmt = select(func.count(MoralEducationLedger.id)).where(
                and_(
                    MoralEducationLedger.school_id == school_id,
                    MoralEducationLedger.student_id == student_id,
                    MoralEducationLedger.dimension_name == dim,
                    MoralEducationLedger.created_at >= cutoff,
                )
            )
            dup_count = (await db.execute(dup_stmt)).scalar() or 0
            if dup_count > 0:
                continue  # 24h 内已有同类工单，跳过

            # 创建工单
            import json

            entry = MoralEducationLedger(
                school_id=school_id,
                student_id=student_id,
                dimension_name=dim,
                trigger_score=score,
                action_type=action_type,
                description=(
                    f"动态降维引擎检测到该生 [{dim}] 维度滑落至 {score} 分，"
                    f"{'触发红线告警' if action_type == 'RED_ZONE' else '触发警戒线告警'}，"
                    f"自动挂牌督导。"
                ),
                score_snapshot=json.dumps(scores, ensure_ascii=False),
            )
            db.add(entry)
            alerts.append(
                {
                    "dimension": dim,
                    "score": score,
                    "action_type": action_type,
                    "threshold_warn": warn_line,
                    "threshold_red": red_line,
                }
            )
            logger.info(
                f"[analytics] 德育工单挂牌 student={student_id} dim={dim} "
                f"score={score} action={action_type}"
            )

        if alerts:
            await db.commit()

        return alerts

    # ═══════════════════════════════════════════════════════════
    #  数据采集层 — 跨模块查询 (异常兜底，单路失败不影响全局)
    # ═══════════════════════════════════════════════════════════

    @classmethod
    async def _fetch_attendance(
        cls,
        db: AsyncSession,
        student_id: int,
        school_id: int,
        since: datetime,
    ) -> dict[str, Any]:
        """路1: 考勤记录 — absent / late / early"""
        records = []
        try:
            from modules.attendance.models import AttendanceRecord

            stmt = (
                select(
                    AttendanceRecord.status,
                    AttendanceRecord.record_date,
                )
                .where(
                    and_(
                        AttendanceRecord.student_id == student_id,
                        AttendanceRecord.school_id == school_id,
                        AttendanceRecord.record_date >= since.date(),
                        AttendanceRecord.status.in_(["absent", "late", "early"]),
                    )
                )
                .order_by(desc(AttendanceRecord.record_date))
            )
            result = await db.execute(stmt)
            for row in result:
                records.append(
                    {
                        "status": row[0],
                        "occurred_at": datetime.combine(row[1], datetime.min.time()),
                    }
                )
        except Exception as e:
            logger.warning(f"[analytics] 考勤数据采集失败 student={student_id}: {e}")

        return {
            "total": len(records),
            "absent_count": sum(1 for r in records if r["status"] == "absent"),
            "warning_count": sum(1 for r in records if r["status"] in ("late", "early")),
            "records": records,
        }

    @classmethod
    async def _fetch_behavior(
        cls,
        db: AsyncSession,
        student_id: int,
        school_id: int,
        since: datetime,
    ) -> dict[str, Any]:
        """路2+3: 违纪记录 + 处分记录"""
        violations = []
        punishments = []
        try:
            from modules.behavior.models import DisciplineRecord

            # 违纪记录 (verified)
            stmt = (
                select(DisciplineRecord)
                .where(
                    and_(
                        DisciplineRecord.student_id == student_id,
                        DisciplineRecord.school_id == school_id,
                        DisciplineRecord.created_at >= since,
                    )
                )
                .order_by(desc(DisciplineRecord.created_at))
            )
            result = await db.execute(stmt)
            for rec in result.scalars():
                occurred = rec.created_at or datetime.utcnow()
                level = getattr(rec, "level", "").lower()
                if level in ("serious", "severe") or getattr(rec, "punishment", None):
                    punishments.append({"occurred_at": occurred, "level": level})
                else:
                    violations.append({"occurred_at": occurred, "level": level})
        except Exception as e:
            logger.warning(f"[analytics] 行为数据采集失败 student={student_id}: {e}")

        return {
            "violation_count": len(violations),
            "punishment_count": len(punishments),
            "violations": violations,
            "punishments": punishments,
        }

    @classmethod
    async def _fetch_academic(
        cls,
        db: AsyncSession,
        student_id: int,
        school_id: int,
    ) -> dict[str, Any]:
        """路5+12: 考试均分 + 错题断层"""
        exam_avg = None
        gaps = {"active_critical": []}

        # 考试均分
        try:
            from modules.grades.models import GradeRecord

            result = await db.execute(
                select(func.avg(GradeRecord.score)).where(
                    GradeRecord.student_id == student_id,
                    GradeRecord.school_id == school_id,
                )
            )
            val = result.scalar()
            if val:
                exam_avg = round(float(val), 2)
        except Exception as e:
            logger.warning(f"[analytics] 学业-考试均分采集失败 student={student_id}: {e}")

        # 错题断层
        try:
            from modules.error_funnel.models import KnowledgeGap

            stmt = select(KnowledgeGap).where(
                and_(
                    KnowledgeGap.student_id == student_id,
                    KnowledgeGap.gap_level == "critical",
                    KnowledgeGap.gap_status == "active",
                )
            )
            result = await db.execute(stmt)
            for gap in result.scalars():
                gaps["active_critical"].append(
                    {
                        "id": gap.id,
                        "updated_at": getattr(gap, "last_error_date", None) or datetime.utcnow(),
                        "consecutive_errors": getattr(gap, "consecutive_errors", 1),
                    }
                )
        except Exception as e:
            logger.warning(f"[analytics] 学业-错题断层采集失败 student={student_id}: {e}")

        return {
            "exam_avg": exam_avg,
            "gap_critical_count": len(gaps["active_critical"]),
            "gaps": gaps,
        }

    @classmethod
    async def _fetch_homework(
        cls,
        db: AsyncSession,
        student_id: int,
        school_id: int,
        since: datetime,
    ) -> dict[str, Any]:
        """路11: 作业缺交流"""
        missing = []
        try:
            from modules.homework_mgmt.models import HwSubmission

            stmt = select(HwSubmission).where(
                and_(
                    HwSubmission.student_id == student_id,
                    HwSubmission.school_id == school_id,
                    HwSubmission.status.in_(["missing", "overdue", "late"]),
                    HwSubmission.created_at >= since,
                )
            )
            result = await db.execute(stmt)
            for sub in result.scalars():
                missing.append(
                    {
                        "due_date": getattr(sub, "due_date", None) or datetime.utcnow(),
                        "status": getattr(sub, "status", "missing"),
                    }
                )
        except Exception as e:
            logger.warning(f"[analytics] 作业数据采集失败 student={student_id}: {e}")

        return {"missing_count": len(missing), "missing": missing}

    @classmethod
    async def _fetch_psych(
        cls,
        db: AsyncSession,
        student_id: int,
        school_id: int,
    ) -> dict[str, Any]:
        """路7+13: 心理风险等级"""
        risk_level = "green"
        updated_at = None
        try:
            from modules.psych_profiles.models import PsychProfile

            stmt = select(PsychProfile).where(
                and_(
                    PsychProfile.student_id == student_id,
                    PsychProfile.school_id == school_id,
                )
            )
            result = await db.execute(stmt)
            profile = result.scalar_one_or_none()
            if profile:
                risk_level = getattr(profile, "risk_level", "green") or "green"
                updated_at = getattr(profile, "risk_level_updated_at", None) or datetime.utcnow()
        except Exception as e:
            logger.warning(f"[analytics] 心理数据采集失败 student={student_id}: {e}")

        return {"risk_level": risk_level, "updated_at": updated_at}

    @classmethod
    async def _fetch_timeline_events(
        cls,
        db: AsyncSession,
        student_id: int,
        school_id: int,
        since: datetime,
    ) -> dict[str, Any]:
        """路8+9: 时光轴事件 (含 Redis 实时注入的)"""
        events = []
        try:
            stmt = (
                select(
                    GrowthTimelineEvent.severity,
                    GrowthTimelineEvent.occurred_at,
                    GrowthTimelineEvent.event_type,
                )
                .where(
                    and_(
                        GrowthTimelineEvent.student_id == student_id,
                        GrowthTimelineEvent.school_id == school_id,
                        GrowthTimelineEvent.occurred_at >= since,
                    )
                )
                .order_by(desc(GrowthTimelineEvent.occurred_at))
                .limit(50)
            )
            result = await db.execute(stmt)
            for row in result:
                events.append(
                    {
                        "severity": row[0],
                        "occurred_at": row[1],
                        "event_type": row[2],
                    }
                )
        except Exception as e:
            logger.warning(f"[analytics] 时光轴采集失败 student={student_id}: {e}")

        return {
            "total": len(events),
            "critical": sum(1 for e in events if e["severity"] == "critical"),
            "warning": sum(1 for e in events if e["severity"] == "warning"),
            "bonus": sum(1 for e in events if e["severity"] == "bonus"),
            "events": events,
        }

    @classmethod
    async def _fetch_latest_snapshot(
        cls,
        db: AsyncSession,
        student_id: int,
        school_id: int,
    ) -> dict[str, Any] | None:
        """路10: 最新阶段性快照"""
        try:
            stmt = (
                select(GrowthPeriodicalSnapshot)
                .where(
                    and_(
                        GrowthPeriodicalSnapshot.student_id == student_id,
                        GrowthPeriodicalSnapshot.school_id == school_id,
                    )
                )
                .order_by(desc(GrowthPeriodicalSnapshot.created_at))
                .limit(1)
            )
            result = await db.execute(stmt)
            snap = result.scalar_one_or_none()
            if snap:
                return {
                    "academic_score": snap.academic_score,
                    "attendance_score": snap.attendance_score,
                    "behavior_score": snap.behavior_score,
                    "psych_score": snap.psych_score,
                    "activity_score": snap.activity_score,
                    "period_label": snap.period_label,
                }
        except Exception as e:
            logger.warning(f"[analytics] 快照采集失败 student={student_id}: {e}")
        return None

    @classmethod
    async def _fetch_activity_count(
        cls,
        db: AsyncSession,
        student_id: int,
    ) -> int:
        """综合实践: 活动参与次数"""
        try:
            from modules.research_activities.models import ActivityParticipant

            result = await db.execute(
                select(func.count(ActivityParticipant.id)).where(
                    ActivityParticipant.student_id == student_id
                )
            )
            return result.scalar() or 0
        except Exception as e:
            logger.warning(f"[analytics] 活动数据采集失败 student={student_id}: {e}")
            return 0


# ═══════════════════════════════════════════════════════════════
#  模块内引用 — 确保 GrowthTimelineEvent / GrowthPeriodicalSnapshot 可用
# ═══════════════════════════════════════════════════════════════

from modules.growth.models import GrowthPeriodicalSnapshot, GrowthTimelineEvent
