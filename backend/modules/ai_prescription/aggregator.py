"""
AI 德育处方大脑 — 黄金上下文组装器 V3
跨 behavior / discipline / evaluation / attendance / red_flag / psych
  + growth / homework_mgmt / error_funnel / psych_profiles / psych_counseling
共 11 大模块打包全维德育快照，注入 LLM Prompt

V2 升维 (Task #1354):
  - rdi_diagnosis 新增 psych_deviation / psych_veto_triggered / veto_dimension
  - 新增 psych_profile 段: 心理10维因子详情 (PsychSurvey.dimension_scores)
  - 新增 timeline 段: 历史事件时间线 (违纪+学业+心理按日期排序)

V3 升维 (Task #1448 — AIContextHydrator 提示词网关):
  - 第9路 growth_timeline: 成长时光轴事件 (Redis事件总线聚合, dimension/severity/payload)
  - 第10路 growth_snapshot: 周期五维快照 (academic/attendance/behavior/psych/activity + 教师评语 + AI处方)
  - 第11路 homework: 作业提交+批改数据 (HwSubmission→HwGrading 两跳关联, 得分率/错题/迟交)
  - 第12路 error_funnel: 错题本+知识断层 (KnowledgeGap gap_level: watch/warning/critical)
  - 第13路 psych_deep: 心理档案+筛查+咨询元数据 (PsyProfile/PsyScreeningRecord/PsyConsultRecord,
           严格排除 encrypted_clog 加密字段)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from modules.attendance.models import AttendanceRecord
from modules.behavior.models import DisciplineRecord
from modules.discipline.models import DisciplineSanction
from modules.evaluation.models import StudentScore
from sqlalchemy import func, select, text

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 心理10维中文映射 (与 risk_models/schemas.py DIMENSION_KEYS 同源)
# ─────────────────────────────────────────────

_DIMENSION_CN_MAP = {
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

# ─────────────────────────────────────────────
# 时间工具
# ─────────────────────────────────────────────


def _utcnow():
    return datetime.now(UTC)


def _days_ago(days: int) -> datetime:
    return _utcnow() - timedelta(days=days)


# ─────────────────────────────────────────────
# 学生上下文组装
# ─────────────────────────────────────────────


class AIPrescriptionAggregator:
    """
    静态工具类：组装 AI 处方所需的全维上下文
    """

    @staticmethod
    async def build_student_context(
        db,
        student_id: int,
        school_id: int,
        days: int = 30,
    ) -> dict:
        """
        组装单名学生黄金上下文
        返回结构化 dict，直接注入 LLM Prompt
        """
        since = _days_ago(days)
        now = _utcnow()

        # 1. 学生基本信息
        # 直接查询 students 表（Wings 3.0 中无 students ORM 模型）
        student_result = await db.execute(
            text(
                "SELECT id, name, class_id, student_no, gender "
                "FROM students "
                "WHERE id = :student_id AND school_id = :school_id"
            ),
            {"student_id": student_id, "school_id": school_id},
        )
        student_row = student_result.fetchone()
        if not student_row:
            raise ValueError(f"学生不存在：student_id={student_id}")

        student_info = {
            "id": student_row.id,
            "name": student_row.name,
            "class_id": student_row.class_id,
            "student_no": student_row.student_no,
            "gender": student_row.gender,
        }

        # 1b. 查询班级名称 (class_id → class_name)
        class_name = None
        if student_info["class_id"]:
            clazz_result = await db.execute(
                text("SELECT name FROM classes WHERE id = :class_id AND school_id = :school_id"),
                {"class_id": student_info["class_id"], "school_id": school_id},
            )
            clazz_row = clazz_result.fetchone()
            if clazz_row:
                class_name = clazz_row.name

        # 2. 考勤统计（present/late/absent/leave）
        att_records = await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.student_id == student_id,
                AttendanceRecord.school_id == school_id,
                AttendanceRecord.record_date >= since.date(),
            )
        )
        att_list = att_records.scalars().all()
        att_stats = {
            "total": len(att_list),
            "present": sum(1 for r in att_list if r.status == "present"),
            "late": sum(1 for r in att_list if r.status == "late"),
            "absent": sum(1 for r in att_list if r.status == "absent"),
            "leave": sum(1 for r in att_list if r.status == "leave"),
            "early": sum(1 for r in att_list if r.status == "early"),
        }
        att_rate = (
            round(att_stats["present"] / att_stats["total"] * 100, 1)
            if att_stats["total"]
            else 100.0
        )

        # 3. 违纪行为（已核实）
        behavior_records = await db.execute(
            select(DisciplineRecord).where(
                DisciplineRecord.student_id == student_id,
                DisciplineRecord.school_id == school_id,
                DisciplineRecord.verify_status == "VERIFIED",
                DisciplineRecord.incident_date >= since.date(),
            )
        )
        b_list = behavior_records.scalars().all()
        behavior_stats = {}
        for rec in b_list:
            cat = rec.category or "其他"
            behavior_stats.setdefault(cat, 0)
            behavior_stats[cat] += 1

        # 4. 活跃处分（ACTIVE）
        sanctions = await db.execute(
            select(DisciplineSanction).where(
                DisciplineSanction.student_id == student_id,
                DisciplineSanction.school_id == school_id,
                DisciplineSanction.status == "ACTIVE",
            )
        )
        s_list = sanctions.scalars().all()
        sanction_info = [
            {
                "level": s.level,
                "reason": s.reason,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in s_list
        ]

        # 5. 素质评价快照（最新）+ 学业趋势（全学期）
        score_result = await db.execute(
            select(StudentScore)
            .where(
                StudentScore.student_id == student_id,
                StudentScore.school_id == school_id,
            )
            .order_by(StudentScore.updated_at.desc())
        )
        all_scores = score_result.scalars().all()
        score_snapshot = None
        academic_trend = None
        if all_scores:
            latest = all_scores[0]
            score_snapshot = {
                "moral": float(latest.moral_score) if latest.moral_score is not None else None,
                "academic": float(latest.academic_score)
                if latest.academic_score is not None
                else None,
                "health": float(latest.health_score) if latest.health_score is not None else None,
                "art": float(latest.art_score) if latest.art_score is not None else None,
                "social": float(latest.social_score) if latest.social_score is not None else None,
                "total": float(latest.total_score) if latest.total_score is not None else None,
                "semester": latest.semester,
            }
            # 学业趋势: 如果有多个学期记录，计算 delta
            if len(all_scores) >= 2:
                prev = all_scores[1]
                curr_academic = (
                    float(latest.academic_score) if latest.academic_score is not None else 0
                )
                prev_academic = float(prev.academic_score) if prev.academic_score is not None else 0
                delta = round(curr_academic - prev_academic, 1)
                academic_trend = {
                    "current_semester": latest.semester,
                    "previous_semester": prev.semester,
                    "current_academic": curr_academic,
                    "previous_academic": prev_academic,
                    "delta": delta,
                    "direction": "up" if delta > 0 else ("down" if delta < 0 else "stable"),
                    "current_total": float(latest.total_score)
                    if latest.total_score is not None
                    else None,
                    "previous_total": float(prev.total_score)
                    if prev.total_score is not None
                    else None,
                }

        # 6. RDI 风险诊断（最新活跃预警）
        rdi_context = None
        try:
            from modules.risk_models.models import RiskWarning

            rw = await db.scalar(
                select(RiskWarning)
                .where(
                    RiskWarning.student_id == student_id,
                    RiskWarning.school_id == school_id,
                    RiskWarning.status == "active",
                )
                .order_by(RiskWarning.warned_at.desc())
                .limit(1)
            )
            if rw:
                rdi_context = {
                    "rdi_score": round(rw.rdi_score, 2),
                    "risk_level": rw.risk_level,
                    "behavior_deviation": round(rw.behavior_deviation, 2),
                    "attendance_deviation": round(rw.attendance_deviation, 2),
                    "score_deviation": round(rw.score_deviation, 2),
                    "psych_deviation": round(rw.psych_deviation, 2) if rw.psych_deviation else None,
                    "psych_veto_triggered": bool(rw.psych_veto_triggered),
                    "veto_dimension": rw.veto_dimension,
                    "ewma_trend": round(rw.ewma_trend, 2),
                    "is_escalating": bool(rw.is_escalating),
                    "trigger": rw.trigger_event_type,
                    "warned_at": rw.warned_at.isoformat() if rw.warned_at else None,
                }
        except Exception as exc:
            logger.warning("[AI-Aggregator] RDI 风险数据查询失败 (不影响主流程): %s", exc)

        # 7. 心理10维因子详情 (PsychSurvey.dimension_scores)
        psych_profile = None
        try:
            from modules.risk_models.models import PsychSurvey

            psych_result = await db.execute(
                select(PsychSurvey)
                .where(
                    PsychSurvey.student_id == student_id,
                    PsychSurvey.school_id == school_id,
                    PsychSurvey.is_valid == True,
                    PsychSurvey.verify_status.in_(["VERIFIED", "PENDING", "COMPLETED"]),
                )
                .order_by(PsychSurvey.completed_at.desc())
                .limit(5)
            )
            # 优先选有 dimension_scores 的记录（MSSMHS-55 > PCE-55）
            psych_surveys = psych_result.scalars().all()
            psych_survey = None
            for ps in psych_surveys:
                if ps.dimension_scores:
                    psych_survey = ps
                    break
            if psych_survey is None and psych_surveys:
                psych_survey = psych_surveys[0]  # fallback: 最新记录
            if psych_survey and psych_survey.dimension_scores:
                raw_dims = (
                    psych_survey.dimension_scores
                )  # JSON dict: {"depression_score": 5.086, ...}
                # 翻译为中文标签 + 标记极端维度
                dim_items = []
                max_dim_key = None
                max_dim_value = 0.0
                for en_key, cn_label in _DIMENSION_CN_MAP.items():
                    val = raw_dims.get(en_key)
                    if val is not None:
                        dim_items.append(
                            {
                                "dimension": en_key,
                                "label": cn_label,
                                "score": round(float(val), 2),
                            }
                        )
                        if abs(float(val)) > abs(max_dim_value):
                            max_dim_key = en_key
                            max_dim_value = float(val)

                # 极端维度标注
                if max_dim_key:
                    for item in dim_items:
                        if item["dimension"] == max_dim_key:
                            item["is_extreme"] = True
                            item["extreme_label"] = (
                                f"最高偏离维度 ({_DIMENSION_CN_MAP[max_dim_key]}: "
                                f"{round(max_dim_value, 2)}σ)"
                            )

                psych_profile = {
                    "survey_type": psych_survey.survey_type,
                    "total_score": float(psych_survey.total_score)
                    if psych_survey.total_score
                    else None,
                    "completed_at": psych_survey.completed_at.isoformat()
                    if psych_survey.completed_at
                    else None,
                    "dimensions": dim_items,
                    "extreme_dimension": max_dim_key,
                    "extreme_dimension_cn": _DIMENSION_CN_MAP.get(max_dim_key, ""),
                    "extreme_value": round(max_dim_value, 2) if max_dim_key else None,
                }
        except Exception as exc:
            logger.warning("[AI-Aggregator] 心理10维数据查询失败 (不影响主流程): %s", exc)

        # 8. 历史时间线 (违纪事件 + 学业变化 + 心理问卷 按日期排序)
        timeline = []
        try:
            # 8a. 违纪事件 (最近30天)
            timeline_behaviors = await db.execute(
                select(DisciplineRecord)
                .where(
                    DisciplineRecord.student_id == student_id,
                    DisciplineRecord.school_id == school_id,
                    DisciplineRecord.verify_status == "VERIFIED",
                    DisciplineRecord.incident_date >= since.date(),
                )
                .order_by(DisciplineRecord.incident_date.desc())
                .limit(10)
            )
            for rec in timeline_behaviors.scalars().all():
                timeline.append(
                    {
                        "date": rec.incident_date.isoformat() if rec.incident_date else None,
                        "event_type": "discipline",
                        "summary": f"{rec.category or '违纪'}: {rec.description[:60] if rec.description else ''}",
                        "severity": rec.severity if rec.severity else None,
                    }
                )

            # 8b. 学业变化 (学期分对比)
            if all_scores and len(all_scores) >= 2:
                for i, score_rec in enumerate(all_scores[:2]):  # 最近2条
                    timeline.append(
                        {
                            "date": score_rec.updated_at.isoformat()
                            if score_rec.updated_at
                            else None,
                            "event_type": "academic_snapshot",
                            "summary": f"素质评价快照: 总分={float(score_rec.total_score) if score_rec.total_score else 0}",
                            "semester": score_rec.semester,
                        }
                    )

            # 8c. 心理问卷完成事件
            from modules.risk_models.models import PsychSurvey as _PS

            psych_timeline = await db.execute(
                select(_PS)
                .where(
                    _PS.student_id == student_id,
                    _PS.school_id == school_id,
                    _PS.is_valid == True,
                )
                .order_by(_PS.completed_at.desc())
                .limit(5)
            )
            for ps in psych_timeline.scalars().all():
                if ps.completed_at:
                    timeline.append(
                        {
                            "date": ps.completed_at.isoformat(),
                            "event_type": "psych_survey",
                            "summary": f"完成心理筛查 ({ps.survey_type})",
                            "risk_flag": ps.total_score,
                        }
                    )

            # 8d. 处分状态变化
            timeline_sanctions = await db.execute(
                select(DisciplineSanction)
                .where(
                    DisciplineSanction.student_id == student_id,
                    DisciplineSanction.school_id == school_id,
                )
                .order_by(DisciplineSanction.created_at.desc())
                .limit(5)
            )
            for s in timeline_sanctions.scalars().all():
                timeline.append(
                    {
                        "date": s.created_at.isoformat() if s.created_at else None,
                        "event_type": "sanction",
                        "summary": f"处分 ({s.level}): {s.reason[:40] if s.reason else ''}",
                        "status": s.status,
                    }
                )

            # 按日期排序 (倒序: 最近事件优先)
            timeline.sort(key=lambda x: x.get("date") or "", reverse=True)
        except Exception as exc:
            logger.warning("[AI-Aggregator] 时间线组装失败 (不影响主流程): %s", exc)

        # ═══════════════════════════════════════════════════════════════
        # V3 升维: 5路新数据源注入 (Task #1448 — AIContextHydrator)
        # ═══════════════════════════════════════════════════════════════

        # 9. 成长时光轴事件 (growth_timeline_events — Redis事件总线聚合)
        growth_timeline = None
        try:
            from modules.growth.models import GrowthTimelineEvent

            gte_result = await db.execute(
                select(GrowthTimelineEvent)
                .where(
                    GrowthTimelineEvent.student_id == student_id,
                    GrowthTimelineEvent.school_id == school_id,
                )
                .order_by(GrowthTimelineEvent.occurred_at.desc())
                .limit(15)
            )
            gte_list = gte_result.scalars().all()
            growth_timeline = [
                {
                    "dimension": gte.dimension,
                    "severity": gte.severity,
                    "event_type": gte.event_type,
                    "title": gte.title,
                    "occurred_at": gte.occurred_at.isoformat() if gte.occurred_at else None,
                    "payload": gte.payload,
                }
                for gte in gte_list
            ]
        except Exception as exc:
            logger.warning("[AI-Aggregator] 成长时光轴查询失败 (不影响主流程): %s", exc)

        # 10. 周期成长快照 (growth_periodical_snapshots — 五维雷达画像)
        growth_snapshot = None
        try:
            from modules.growth.models import GrowthPeriodicalSnapshot

            gps_result = await db.execute(
                select(GrowthPeriodicalSnapshot)
                .where(
                    GrowthPeriodicalSnapshot.student_id == student_id,
                    GrowthPeriodicalSnapshot.school_id == school_id,
                )
                .order_by(GrowthPeriodicalSnapshot.created_at.desc())
                .limit(3)
            )
            gps_list = gps_result.scalars().all()
            growth_snapshot = [
                {
                    "snapshot_type": gps.snapshot_type,
                    "period_label": gps.period_label,
                    "academic_score": round(float(gps.academic_score), 1)
                    if gps.academic_score is not None
                    else None,
                    "attendance_score": round(float(gps.attendance_score), 1)
                    if gps.attendance_score is not None
                    else None,
                    "behavior_score": round(float(gps.behavior_score), 1)
                    if gps.behavior_score is not None
                    else None,
                    "psych_score": round(float(gps.psych_score), 1)
                    if gps.psych_score is not None
                    else None,
                    "activity_score": round(float(gps.activity_score), 1)
                    if gps.activity_score is not None
                    else None,
                    "teacher_comment": gps.teacher_comment,
                    "ai_growth_prescription": gps.ai_growth_prescription,
                }
                for gps in gps_list
            ]
        except Exception as exc:
            logger.warning("[AI-Aggregator] 成长快照查询失败 (不影响主流程): %s", exc)

        # 11. 作业提交与批改数据 (homework_mgmt — HwSubmission + HwGrading)
        homework_context = None
        try:
            from modules.homework_mgmt.models import HwGrading, HwSubmission

            hw_sub_result = await db.execute(
                select(HwSubmission)
                .where(
                    HwSubmission.student_id == student_id,
                    HwSubmission.school_id == school_id,
                )
                .order_by(HwSubmission.created_at.desc())
                .limit(20)
            )
            hw_subs = hw_sub_result.scalars().all()
            if hw_subs:
                submission_ids = [s.id for s in hw_subs]
                # 批改数据: 通过 submission_id 两跳关联 student_id
                hw_grade_result = await db.execute(
                    select(HwGrading)
                    .where(
                        HwGrading.submission_id.in_(submission_ids),
                        HwGrading.school_id == school_id,
                    )
                    .order_by(HwGrading.created_at.desc())
                )
                grade_map = {g.submission_id: g for g in hw_grade_result.scalars().all()}

                hw_items = []
                total_score_pct = []
                total_errors = 0
                late_count = 0
                for sub in hw_subs:
                    item = {
                        "assignment_id": sub.assignment_id,
                        "status": sub.status,
                        "late_minutes": sub.late_minutes,
                        "submitted_at": sub.submitted_at.isoformat() if sub.submitted_at else None,
                    }
                    grade = grade_map.get(sub.id)
                    if grade:
                        item["score"] = float(grade.score) if grade.score is not None else None
                        item["max_score"] = (
                            float(grade.max_score) if grade.max_score is not None else None
                        )
                        item["score_percentage"] = (
                            round(float(grade.score_percentage), 1)
                            if grade.score_percentage is not None
                            else None
                        )
                        item["grade"] = grade.grade
                        item["error_count"] = grade.error_count
                        item["feedback"] = grade.feedback[:100] if grade.feedback else None
                        if grade.score_percentage is not None:
                            total_score_pct.append(float(grade.score_percentage))
                        total_errors += grade.error_count or 0
                    if sub.late_minutes and sub.late_minutes > 0:
                        late_count += 1
                    hw_items.append(item)

                homework_context = {
                    "recent_submissions": hw_items[:10],
                    "summary": {
                        "total_submissions": len(hw_subs),
                        "graded_count": len(grade_map),
                        "late_count": late_count,
                        "avg_score_pct": round(sum(total_score_pct) / len(total_score_pct), 1)
                        if total_score_pct
                        else None,
                        "total_errors": total_errors,
                    },
                }
        except Exception as exc:
            logger.warning("[AI-Aggregator] 作业数据查询失败 (不影响主流程): %s", exc)

        # 12. 错题本与知识断层 (error_funnel — ErrorBookItem + KnowledgeGap)
        error_funnel_context = None
        try:
            from modules.error_funnel.models import ErrorBookItem, KnowledgeGap

            # 12a. 知识断层 (KnowledgeGap — 优先 critical/warning)
            gap_result = await db.execute(
                select(KnowledgeGap)
                .where(
                    KnowledgeGap.student_id == student_id,
                    KnowledgeGap.school_id == school_id,
                    KnowledgeGap.gap_status == "active",
                )
                .order_by(KnowledgeGap.consecutive_errors.desc())
                .limit(15)
            )
            gaps = gap_result.scalars().all()
            gap_items = []
            critical_count = 0
            warning_count = 0
            for g in gaps:
                gap_items.append(
                    {
                        "knowledge_point": g.knowledge_point_name,
                        "error_count": g.error_count,
                        "consecutive_errors": g.consecutive_errors,
                        "gap_level": g.gap_level,
                        "ai_prescription": g.ai_prescription[:100] if g.ai_prescription else None,
                    }
                )
                if g.gap_level == "critical":
                    critical_count += 1
                elif g.gap_level == "warning":
                    warning_count += 1

            # 12b. 最近错题 (ErrorBookItem)
            error_result = await db.execute(
                select(ErrorBookItem)
                .where(
                    ErrorBookItem.student_id == student_id,
                    ErrorBookItem.school_id == school_id,
                )
                .order_by(ErrorBookItem.created_at.desc())
                .limit(10)
            )
            errors = error_result.scalars().all()
            error_items = []
            unresolved_count = 0
            for e in errors:
                error_items.append(
                    {
                        "source_type": e.source_type,
                        "error_type": e.error_type,
                        "difficulty": e.difficulty,
                        "question_preview": e.question_content[:80] if e.question_content else None,
                        "is_resolved": e.is_resolved,
                    }
                )
                if not e.is_resolved:
                    unresolved_count += 1

            error_funnel_context = {
                "knowledge_gaps": gap_items,
                "recent_errors": error_items,
                "summary": {
                    "total_gaps": len(gaps),
                    "critical_gaps": critical_count,
                    "warning_gaps": warning_count,
                    "total_errors": len(errors),
                    "unresolved_errors": unresolved_count,
                },
            }
        except Exception as exc:
            logger.warning("[AI-Aggregator] 错题/断层数据查询失败 (不影响主流程): %s", exc)

        # 13. 心理综合档案 + 筛查记录 + 咨询记录 (Phase 2 心理双模块)
        # 严格排除 PsyConsultRecord.encrypted_clog 加密字段
        psych_deep_context = None
        try:
            from modules.psych_counseling.models import PsyConsultRecord
            from modules.psych_profiles.models import PsyProfile, PsyScreeningRecord

            # 13a. 心理综合档案主表 (一学生一档案)
            psy_profile = await db.scalar(
                select(PsyProfile).where(
                    PsyProfile.student_id == student_id,
                    PsyProfile.school_id == school_id,
                )
            )
            # 13b. 最近筛查记录 (量表流水)
            screening_result = await db.execute(
                select(PsyScreeningRecord)
                .where(
                    PsyScreeningRecord.student_id == student_id,
                    PsyScreeningRecord.school_id == school_id,
                )
                .order_by(PsyScreeningRecord.test_date.desc())
                .limit(3)
            )
            screenings = screening_result.scalars().all()
            # 13c. 咨询记录元数据 (仅明文字段, encrypted_clog 被严格排除!)
            consult_result = await db.execute(
                select(PsyConsultRecord)
                .where(
                    PsyConsultRecord.student_id == student_id,
                    PsyConsultRecord.school_id == school_id,
                )
                .order_by(PsyConsultRecord.created_at.desc())
                .limit(5)
            )
            consults = consult_result.scalars().all()

            psych_deep_context = {
                "profile": {
                    "risk_level": psy_profile.risk_level,
                    "risk_level_source": psy_profile.risk_level_source,
                    "tags": psy_profile.tags or [],
                    "highest_risk_level": psy_profile.highest_risk_level,
                    "total_counseling_count": psy_profile.total_counseling_count or 0,
                    "total_screening_count": psy_profile.total_screening_count or 0,
                    "is_referred": bool(psy_profile.is_referred),
                    "last_counseling_date": psy_profile.last_counseling_date.isoformat()
                    if psy_profile.last_counseling_date
                    else None,
                }
                if psy_profile
                else None,
                "screenings": [
                    {
                        "scale_name": s.scale_name,
                        "total_score": float(s.total_score) if s.total_score is not None else None,
                        "risk_level": s.risk_level,
                        "risk_factors": s.risk_factors or [],
                        "conclusion": s.conclusion[:100] if s.conclusion else None,
                        "test_date": s.test_date.isoformat() if s.test_date else None,
                    }
                    for s in screenings
                ],
                "consults": [
                    {
                        # 明文元数据 only — encrypted_clog 严格排除
                        "risk_level": c.risk_level,
                        "consult_category": c.consult_category,
                        "is_crisis": bool(c.is_crisis),
                        "is_referred": bool(c.is_referred),
                        "session_duration_min": c.session_duration_min,
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                    }
                    for c in consults
                ],
            }
        except Exception as exc:
            logger.warning("[AI-Aggregator] 心理深度数据查询失败 (不影响主流程): %s", exc)

        # 组装最终上下文
        # 提取 rdi_score (从 rdi_context 中获取)
        rdi_score_value = rdi_context.get("rdi_score") if rdi_context else None

        context = {
            "student": {
                "id": student_info["id"],
                "name": student_info["name"],
                "gender": student_info["gender"],
                "class_id": student_info["class_id"],
                "class_name": class_name or f"班级{student_info['class_id']}",
            },
            # ── V2 平铺字段: 前端可直接从 raw_snapshot 读取 ──
            "student_name": student_info["name"],
            "class_name": class_name or f"班级{student_info['class_id']}",
            "rdi_score": rdi_score_value,
            # ── 嵌套数据段 ──
            "analysis_period": {
                "days": days,
                "since": since.isoformat(),
                "until": now.isoformat(),
            },
            "attendance": {
                **att_stats,
                "attendance_rate": f"{att_rate}%",
            },
            "behavior": {
                "total_incidents": len(b_list),
                "by_category": behavior_stats,
            },
            "sanctions": sanction_info,
            "evaluation": score_snapshot,
            "academic_trend": academic_trend,
            "rdi_diagnosis": rdi_context,
            "psych_profile": psych_profile,
            "timeline": timeline,
            # ── V3 升维: 5路新数据源 (Task #1448) ──
            "growth_timeline": growth_timeline,
            "growth_snapshot": growth_snapshot,
            "homework": homework_context,
            "error_funnel": error_funnel_context,
            "psych_deep": psych_deep_context,
        }

        logger.info(
            "[AI-Aggregator] 学生上下文组装完成(V3)：student_id=%s, "
            "考勤=%s条, 违纪=%s条, 处分=%s条, 学期记录=%s, RDI=%s, "
            "心理10维=%s, 时间线=%s条 | "
            "成长事件=%s, 快照=%s, 作业=%s, 错题断层=%s, 心理深度=%s",
            student_id,
            att_stats["total"],
            len(b_list),
            len(s_list),
            len(all_scores),
            "有" if rdi_context else "无",
            "有" if psych_profile else "无",
            len(timeline),
            len(growth_timeline) if growth_timeline else 0,
            len(growth_snapshot) if growth_snapshot else 0,
            "有" if homework_context else "无",
            "有" if error_funnel_context else "无",
            "有" if psych_deep_context else "无",
        )

        return context

    # ─────────────────────────────────────────────
    # 班级上下文组装
    # ─────────────────────────────────────────────

    @staticmethod
    async def build_class_context(
        db,
        class_id: int,
        school_id: int,
        semester: str | None = None,
        days: int = 30,
    ) -> dict:
        """
        组装班级宏观黄金上下文
        返回结构化 dict，直接注入 LLM Prompt
        """
        since = _days_ago(days)
        now = _utcnow()

        # 1. 班级基本信息 + 学生列表
        # 直接查询 classes 表（Wings 3.0 中无 classes ORM 模型）
        clazz_result = await db.execute(
            text(
                "SELECT id, name, grade_id "
                "FROM classes "
                "WHERE id = :class_id AND school_id = :school_id"
            ),
            {"class_id": class_id, "school_id": school_id},
        )
        clazz_row = clazz_result.fetchone()
        if not clazz_row:
            raise ValueError(f"班级不存在：class_id={class_id}")

        # clazz_row 是 Row 对象，按列名访问
        clazz_info = {
            "id": clazz_row.id,
            "name": clazz_row.name,
            "grade_id": clazz_row.grade_id,
        }

        # 获取班级学生 ID 列表
        students_result = await db.execute(
            text(
                "SELECT id, name "
                "FROM students "
                "WHERE class_id = :class_id AND school_id = :school_id"
            ),
            {"class_id": class_id, "school_id": school_id},
        )
        students = students_result.fetchall()
        student_ids = [s.id for s in students]

        # 2. 全班考勤率
        if student_ids:
            att_records = await db.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.student_id.in_(student_ids),
                    AttendanceRecord.school_id == school_id,
                    AttendanceRecord.record_date >= since.date(),
                )
            )
            att_list = att_records.scalars().all()
            att_stats = {
                "total_records": len(att_list),
                "present": sum(1 for r in att_list if r.status == "present"),
                "late": sum(1 for r in att_list if r.status == "late"),
                "absent": sum(1 for r in att_list if r.status == "absent"),
                "leave": sum(1 for r in att_list if r.status == "leave"),
            }
            total_possible = len(student_ids) * days
            att_rate = (
                round(att_stats["present"] / total_possible * 100, 1) if total_possible else 0.0
            )
        else:
            att_stats = {"total_records": 0, "present": 0, "late": 0, "absent": 0, "leave": 0}
            att_rate = 0.0

        # 3. 全班违纪密度分布
        if student_ids:
            behavior_records = await db.execute(
                select(DisciplineRecord).where(
                    DisciplineRecord.student_id.in_(student_ids),
                    DisciplineRecord.school_id == school_id,
                    DisciplineRecord.verify_status == "VERIFIED",
                    DisciplineRecord.incident_date >= since.date(),
                )
            )
            b_list = behavior_records.scalars().all()
            behavior_by_cat = {}
            for rec in b_list:
                cat = rec.category or "其他"
                behavior_by_cat.setdefault(cat, 0)
                behavior_by_cat[cat] += 1
        else:
            b_list = []
            behavior_by_cat = {}

        # 4. 流动红旗历史（最近3次）
        from modules.red_flag.models import FlagArchiveReport

        flag_history = await db.execute(
            select(FlagArchiveReport)
            .where(
                FlagArchiveReport.class_id == class_id,
                FlagArchiveReport.school_id == school_id,
            )
            .order_by(FlagArchiveReport.archived_at.desc())
            .limit(3)
        )
        flag_list = flag_history.scalars().all()
        flag_info = [
            {
                "final_score": float(f.final_score) if f.final_score else 0,
                "has_flag": f.has_flag,
                "rank": f.rank,
                "period_label": f.period_label,
            }
            for f in flag_list
        ]

        # 5. 活跃处分人数
        active_sanctions = (
            await db.scalar(
                select(func.count())
                .select_from(DisciplineSanction)
                .where(
                    DisciplineSanction.school_id == school_id,
                    DisciplineSanction.status == "ACTIVE",
                    DisciplineSanction.student_id.in_(student_ids),
                )
            )
            if student_ids
            else 0
        )

        # 6. 素质评价分布（五维平均分）
        if student_ids:
            scores = await db.execute(
                select(StudentScore).where(
                    StudentScore.student_id.in_(student_ids),
                    StudentScore.school_id == school_id,
                    StudentScore.semester == semester if semester else True,
                )
            )
            score_list = scores.scalars().all()
            if score_list:
                avg_moral = sum(
                    float(s.moral_score) for s in score_list if s.moral_score is not None
                ) / len(score_list)
                avg_academic = sum(
                    float(s.academic_score) for s in score_list if s.academic_score is not None
                ) / len(score_list)
                avg_sports = sum(
                    float(s.health_score) for s in score_list if s.health_score is not None
                ) / len(score_list)
                avg_arts = sum(
                    float(s.art_score) for s in score_list if s.art_score is not None
                ) / len(score_list)
                avg_labor = sum(
                    float(s.social_score) for s in score_list if s.social_score is not None
                ) / len(score_list)
            else:
                avg_moral = avg_academic = avg_sports = avg_arts = avg_labor = None
        else:
            score_list = []
            avg_moral = avg_academic = avg_sports = avg_arts = avg_labor = None

        context = {
            "class": {
                "id": clazz_info["id"],
                "name": clazz_info["name"],
                "grade_id": clazz_info["grade_id"],
                "student_count": len(students),
            },
            "analysis_period": {
                "days": days,
                "since": since.isoformat(),
                "until": now.isoformat(),
            },
            "attendance": {
                **att_stats,
                "attendance_rate": f"{att_rate}%",
            },
            "behavior": {
                "total_incidents": len(b_list),
                "by_category": behavior_by_cat,
                "incident_per_student": round(len(b_list) / len(students), 2) if students else 0,
            },
            "red_flag": flag_info,
            "active_sanctions_count": active_sanctions,
            "evaluation_avg": {
                "moral": round(avg_moral, 1) if avg_moral else None,
                "academic": round(avg_academic, 1) if avg_academic else None,
                "sports": round(avg_sports, 1) if avg_sports else None,
                "arts": round(avg_arts, 1) if avg_arts else None,
                "labor": round(avg_labor, 1) if avg_labor else None,
            },
        }

        logger.info(
            "[AI-Aggregator] 班级上下文组装完成：class_id=%s, 学生=%s人, 违纪=%s条, 活跃处分=%s条",
            class_id,
            len(students),
            len(b_list),
            active_sanctions,
        )

        return context
