"""
AI 德育处方大脑 — 黄金上下文组装器
跨 behavior / discipline / evaluation / attendance / red_flag 五大模块
打包全维德育快照，注入 LLM Prompt
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from modules.attendance.models import AttendanceRecord
from modules.behavior.models import DisciplineRecord
from modules.discipline.models import DisciplineSanction
from modules.evaluation.models import StudentScore

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 时间工具
# ─────────────────────────────────────────────


def _utcnow():
    return datetime.now(timezone.utc)


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
            if att_stats["total"] else 100.0
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
            select(StudentScore).where(
                StudentScore.student_id == student_id,
                StudentScore.school_id == school_id,
            ).order_by(StudentScore.updated_at.desc())
        )
        all_scores = score_result.scalars().all()
        score_snapshot = None
        academic_trend = None
        if all_scores:
            latest = all_scores[0]
            score_snapshot = {
                "moral": float(latest.moral_score) if latest.moral_score is not None else None,
                "academic": float(latest.academic_score) if latest.academic_score is not None else None,
                "health": float(latest.health_score) if latest.health_score is not None else None,
                "art": float(latest.art_score) if latest.art_score is not None else None,
                "social": float(latest.social_score) if latest.social_score is not None else None,
                "total": float(latest.total_score) if latest.total_score is not None else None,
                "semester": latest.semester,
            }
            # 学业趋势: 如果有多个学期记录，计算 delta
            if len(all_scores) >= 2:
                prev = all_scores[1]
                curr_academic = float(latest.academic_score) if latest.academic_score is not None else 0
                prev_academic = float(prev.academic_score) if prev.academic_score is not None else 0
                delta = round(curr_academic - prev_academic, 1)
                academic_trend = {
                    "current_semester": latest.semester,
                    "previous_semester": prev.semester,
                    "current_academic": curr_academic,
                    "previous_academic": prev_academic,
                    "delta": delta,
                    "direction": "up" if delta > 0 else ("down" if delta < 0 else "stable"),
                    "current_total": float(latest.total_score) if latest.total_score is not None else None,
                    "previous_total": float(prev.total_score) if prev.total_score is not None else None,
                }

        # 6. RDI 风险诊断（最新活跃预警）
        rdi_context = None
        try:
            from modules.risk_models.models import RiskWarning
            rw = await db.scalar(
                select(RiskWarning).where(
                    RiskWarning.student_id == student_id,
                    RiskWarning.school_id == school_id,
                    RiskWarning.status == "active",
                ).order_by(RiskWarning.warned_at.desc()).limit(1)
            )
            if rw:
                rdi_context = {
                    "rdi_score": round(rw.rdi_score, 2),
                    "risk_level": rw.risk_level,
                    "behavior_deviation": round(rw.behavior_deviation, 2),
                    "attendance_deviation": round(rw.attendance_deviation, 2),
                    "score_deviation": round(rw.score_deviation, 2),
                    "ewma_trend": round(rw.ewma_trend, 2),
                    "is_escalating": bool(rw.is_escalating),
                    "trigger": rw.trigger_event_type,
                    "warned_at": rw.warned_at.isoformat() if rw.warned_at else None,
                }
        except Exception as exc:
            logger.warning("[AI-Aggregator] RDI 风险数据查询失败 (不影响主流程): %s", exc)

        # 组装最终上下文
        context = {
            "student": {
                "id": student_info["id"],
                "name": student_info["name"],
                "gender": student_info["gender"],
                "class_id": student_info["class_id"],
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
                "by_category": behavior_stats,
            },
            "sanctions": sanction_info,
            "evaluation": score_snapshot,
            "academic_trend": academic_trend,
            "rdi_diagnosis": rdi_context,
        }

        logger.info(
            "[AI-Aggregator] 学生上下文组装完成：student_id=%s, "
            "考勤=%s条, 违纪=%s条, 处分=%s条, 学期记录=%s, RDI=%s",
            student_id, att_stats["total"], len(b_list), len(s_list),
            len(all_scores), "有" if rdi_context else "无"
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
            att_rate = round(
                att_stats["present"] / total_possible * 100, 1
            ) if total_possible else 0.0
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
            select(FlagArchiveReport).where(
                FlagArchiveReport.class_id == class_id,
                FlagArchiveReport.school_id == school_id,
            ).order_by(FlagArchiveReport.archived_at.desc()).limit(3)
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
        active_sanctions = await db.scalar(
            select(func.count()).select_from(DisciplineSanction).where(
                DisciplineSanction.school_id == school_id,
                DisciplineSanction.status == "ACTIVE",
                DisciplineSanction.student_id.in_(student_ids),
            )
        ) if student_ids else 0

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
                avg_moral = sum(float(s.moral_score) for s in score_list if s.moral_score is not None) / len(score_list)
                avg_academic = sum(float(s.academic_score) for s in score_list if s.academic_score is not None) / len(score_list)
                avg_sports = sum(float(s.health_score) for s in score_list if s.health_score is not None) / len(score_list)
                avg_arts = sum(float(s.art_score) for s in score_list if s.art_score is not None) / len(score_list)
                avg_labor = sum(float(s.social_score) for s in score_list if s.social_score is not None) / len(score_list)
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
                "incident_per_student": round(len(b_list) / len(students), 2)
                if students else 0,
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
            "[AI-Aggregator] 班级上下文组装完成：class_id=%s, "
            "学生=%s人, 违纪=%s条, 活跃处分=%s条",
            class_id, len(students), len(b_list), active_sanctions
        )

        return context
