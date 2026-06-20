# -*- coding: utf-8 -*-
"""
学生数据聚合器 — 统一为 AI 评语生成提供多维度数字画像

职责：
- 成绩趋势（考试斜率分析）
- 五翼行为分汇总
- 违纪记录统计
- 活动参与统计
- 心理健康评估
- 班主任手记/干预效果
- 隐形好学生识别（增值评价专用）

所有 AI 评语模块（期末评语/增值评价）共享此模块，禁止各自重复查询。
"""
import time
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from models import db, Student, Exam, Score, Subject, WingsScore
from models import DisciplineRecord, ActivityRegistration, Activity
from models import MentalHealthAssessment, TeacherNote, InterventionRecord
from models import Attendance
from utils import get_local_now


# ── 考试级缓存（最近一次考试，全校通用，60秒 TTL）──
_latest_exam_cache = {"value": None, "ts": 0}
_LATEST_EXAM_CACHE_TTL = 60


class StudentDataAggregator:
    """学生多维度数据聚合器 — 单例模式，无状态"""

    @staticmethod
    def _get_latest_exam():
        """获取最近一次考试（缓存60秒，避免逐学生重复查询）"""
        now = time.time()
        if now - _latest_exam_cache["ts"] < _LATEST_EXAM_CACHE_TTL:
            return _latest_exam_cache["value"]
        exam = Exam.query.order_by(Exam.exam_date.desc()).first()
        _latest_exam_cache["value"] = exam
        _latest_exam_cache["ts"] = now
        return exam

    @staticmethod
    def current_semester():
        """获取当前学期标识，如 '2025-2026-2'"""
        now = get_local_now()
        y = now.year
        m = now.month
        if m >= 9:
            return f"{y}-{y + 1}-1"
        elif m >= 2:
            return f"{y - 1}-{y}-2"
        else:
            return f"{y - 1}-{y}-2"

    # ═══════════════════════════════════════════════════════════
    #  基础画像：违纪·成绩·活动·心理
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def build_student_context(stu):
        """拉取学生多维度基础数据，供评语参考"""
        ctx = {
            "student": stu,
            "discipline": {},
            "scores": {},
            "activities": {},
            "mental_health": {},
        }

        # 1. 违纪记录统计
        records = DisciplineRecord.query.filter_by(student_id=stu.id).all()
        ctx["discipline"] = {
            "total": len(records),
            "active": sum(1 for r in records if r.status == "active"),
            "points": sum(r.points for r in records),
            "recent": records[-3:] if records else [],
        }

        # 2. 最近考试成绩
        latest_exam = StudentDataAggregator._get_latest_exam()
        if latest_exam:
            scores = Score.query.filter_by(
                student_id=stu.id, exam_id=latest_exam.id
            ).all()
            ctx["scores"] = {
                "exam_name": latest_exam.name,
                "exam_date": latest_exam.exam_date,
                "scores": scores,
                "avg": round(sum(s.score for s in scores) / len(scores), 1)
                if scores else 0,
            }

        # 3. 活动参与
        regs = (
            ActivityRegistration.query.filter_by(
                student_id=stu.id, status="confirmed"
            )
            .options(joinedload(ActivityRegistration.activity))
            .all()
        )
        activity_list = [reg.activity for reg in regs if reg.activity]
        ctx["activities"] = {
            "total": len(regs),
            "list": activity_list[:5],
        }

        # 4. 心理健康
        mh = (
            MentalHealthAssessment.query.filter_by(student_id=stu.id)
            .order_by(MentalHealthAssessment.created_at.desc())
            .first()
        )
        if mh:
            ctx["mental_health"] = {
                "total_score": mh.total_score,
                "risk_level": mh.risk_level,
                "conclusion": mh.conclusion,
            }

        return ctx

    # ═══════════════════════════════════════════════════════════
    #  增强画像：成绩斜率·五翼分·班主任手记·干预效果
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def build_llm_context(stu):
        """为 LLM 构建增强版数字灵魂画像（含斜率、行为趋势、随访文本）"""
        ctx = StudentDataAggregator.build_student_context(stu)

        # ── 5. 考试斜率分析 ──
        exams = (
            Exam.query.filter_by(grade_id=stu.grade_id)
            .order_by(Exam.exam_date.asc())
            .all()
        )
        subjects = Subject.query.order_by(Subject.sort_order).all()
        subject_map = {s.id: s.name for s in subjects}

        if len(exams) >= 2 and subjects:
            all_scores = Score.query.filter(
                Score.student_id == stu.id,
                Score.exam_id.in_([e.id for e in exams]),
            ).all()

            exam_map = {e.id: e.name for e in exams}
            timeline = {}
            for s in all_scores:
                subj_name = subject_map.get(
                    s.subject_id, f"科目{s.subject_id}"
                )
                if subj_name not in timeline:
                    timeline[subj_name] = []
                timeline[subj_name].append(
                    (exam_map.get(s.exam_id, "?"), s.score)
                )

            slopes = {}
            for subj, records in timeline.items():
                if len(records) >= 2:
                    records.sort(key=lambda x: x[0])
                    first, last = records[0], records[-1]
                    n = len(records)
                    slope = round(
                        (last[1] - first[1]) / max(n - 1, 1), 1
                    )
                    slopes[subj] = {
                        "slope": slope,
                        "trend": (
                            "上升"
                            if slope > 0
                            else ("下降" if slope < 0 else "平稳")
                        ),
                        "first_score": first[1],
                        "last_score": last[1],
                        "exams_count": n,
                    }
            ctx["score_trends"] = slopes

        # ── 6. 五翼行为分汇总 ──
        wing_scores = WingsScore.query.filter_by(student_id=stu.id).all()
        if wing_scores:
            dim_summary = {}
            for ws in wing_scores:
                d = ws.dimension
                if d not in dim_summary:
                    dim_summary[d] = {
                        "total": 0,
                        "count": 0,
                        "recent": [],
                    }
                dim_summary[d]["total"] += ws.score
                dim_summary[d]["count"] += 1
                dim_summary[d]["recent"].append(
                    {
                        "score": ws.score,
                        "scorer_type": ws.scorer_type,
                        "date": ws.created_at.strftime("%m-%d")
                        if ws.created_at
                        else "?",
                    }
                )
            for d in dim_summary:
                dim_summary[d]["avg"] = round(
                    dim_summary[d]["total"] / dim_summary[d]["count"], 1
                )
                dim_summary[d]["recent"] = dim_summary[d]["recent"][
                    -5:
                ]
            ctx["wings"] = dim_summary

        # ── 7. 班主任手记（最近3条）──
        notes = (
            TeacherNote.query.filter_by(student_id=stu.id)
            .order_by(TeacherNote.created_at.desc())
            .limit(3)
            .all()
        )
        if notes:
            ctx["teacher_notes"] = [
                {
                    "category": n.category,
                    "content": n.content,
                    "date": n.created_at.strftime("%m-%d")
                    if n.created_at
                    else "?",
                }
                for n in notes
            ]

        # ── 8. 干预效果 ──
        interventions = (
            InterventionRecord.query.filter_by(student_id=stu.id)
            .order_by(InterventionRecord.created_at.desc())
            .limit(5)
            .all()
        )
        if interventions:
            ctx["interventions"] = [
                {
                    "type": iv.intervention_type,
                    "effect": iv.effect_rating,
                    "notes": iv.notes[:100] if iv.notes else "",
                }
                for iv in interventions
            ]

        return ctx

    # ═══════════════════════════════════════════════════════════
    #  LLM Prompt 序列化
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def format_llm_prompt(stu, context):
        """将结构化数据编织为 LLM 的自然语言提示"""
        parts = []
        parts.append(f"学生姓名：{stu.name}")
        parts.append(
            f"班级：{stu.class_.name if stu.class_ else '未知'}"
        )
        parts.append(f"性别：{stu.gender or '未知'}")

        # 成绩斜率
        if context.get("score_trends"):
            parts.append("\n【考试成绩趋势】")
            for subj, info in context["score_trends"].items():
                direction = (
                    "↑"
                    if info["slope"] > 0
                    else ("↓" if info["slope"] < 0 else "→")
                )
                parts.append(
                    f"  {subj}: {info['first_score']}→{info['last_score']} "
                    f"({direction}{info['slope']}分/次, {info['exams_count']}次考试, "
                    f"整体{info['trend']})"
                )

        # 最近考试成绩
        if context.get("scores") and context["scores"].get("exam_name"):
            sc = context["scores"]
            parts.append(
                f"\n【最近考试】{sc['exam_name']} ({sc['exam_date']})"
            )
            parts.append(f"  均分: {sc['avg']}")
            for s_item in sc.get("scores", []):
                subj_name = (
                    s_item.subject.name if s_item.subject else "?"
                )
                parts.append(f"  {subj_name}: {s_item.score}分")

        # 五翼行为分
        if context.get("wings"):
            parts.append("\n【五维行为分沉淀】")
            dim_names = {
                "德": "品德修养",
                "智": "学业表现",
                "体": "身心健康",
                "美": "审美素养",
                "劳": "劳动实践",
            }
            for dim, info in context["wings"].items():
                dim_label = dim_names.get(dim, dim)
                parts.append(
                    f"  {dim_label}({dim}): 均分{info['avg']}分, "
                    f"共{info['count']}次评分"
                )

        # 违纪
        disc = context.get("discipline", {})
        if disc.get("total", 0) > 0:
            parts.append(
                f"\n【违纪记录】共{disc['total']}条, "
                f"累计扣分{disc.get('points', 0)}分"
            )

        # 活动
        acts = context.get("activities", {})
        if acts.get("total", 0) > 0:
            act_names = [
                a.title
                for a in acts.get("list", [])
                if hasattr(a, "title")
            ]
            parts.append(
                f"\n【活动参与】共{acts['total']}次: "
                f"{', '.join(act_names[:3])}"
            )

        # 心理健康
        mh = context.get("mental_health", {})
        if mh.get("risk_level"):
            parts.append(
                f"\n【心理健康】风险等级: {mh['risk_level']}, "
                f"总分: {mh.get('total_score', '?')}"
            )

        # 班主任手记
        if context.get("teacher_notes"):
            parts.append("\n【班主任随访手记】")
            for note in context["teacher_notes"]:
                parts.append(
                    f"  [{note['category']}] {note['content'][:150]}"
                )

        # 干预效果
        if context.get("interventions"):
            parts.append("\n【历史干预效果】")
            for iv in context["interventions"]:
                parts.append(f"  {iv['type']}: {iv['effect']}")

        return "\n".join(parts)

    # ═══════════════════════════════════════════════════════════
    #  增值评价专用：隐形好学生识别
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def get_student_totals_by_exam(exam_id, grade_id=None):
        """获取某次考试每个学生的总分（按student_id聚合）"""
        q = db.session.query(
            Score.student_id,
            func.sum(Score.score).label("total"),
            func.count(Score.score).label("subject_count"),
        ).filter(
            Score.exam_id == exam_id,
            Score.verify_status == "VERIFIED",
        )
        if grade_id:
            q = q.filter(Score.grade_id == grade_id)
        q = q.group_by(Score.student_id)
        results = q.all()
        return {
            r.student_id: {
                "total": float(r.total) if r.total else 0,
                "subjects": int(r.subject_count),
            }
            for r in results
        }

    @staticmethod
    def get_student_ranks_by_exam(exam_id, grade_id=None):
        """获取某次考试每个学生的年级排名"""
        totals = StudentDataAggregator.get_student_totals_by_exam(
            exam_id, grade_id
        )
        if not totals:
            return {}
        sorted_students = sorted(
            totals.items(), key=lambda x: x[1]["total"], reverse=True
        )
        return {sid: rank + 1 for rank, (sid, _) in enumerate(sorted_students)}

    @staticmethod
    def identify_hidden_gems(prev_exam_id, curr_exam_id, grade_id=None):
        """
        识别"隐形好学生"——成绩中下游但品行好、进步大的学生。

        条件：
        1. 分数进步（delta > 0）
        2. 当前排名在后50%
        3. 行为分高于平均或无违纪

        返回: [{student, prev_total, curr_total, score_delta, ...}]
        """
        prev_totals = StudentDataAggregator.get_student_totals_by_exam(
            prev_exam_id, grade_id
        )
        curr_totals = StudentDataAggregator.get_student_totals_by_exam(
            curr_exam_id, grade_id
        )

        common_ids = set(prev_totals.keys()) & set(curr_totals.keys())
        if not common_ids:
            return []

        # 批量加载学生
        students = {
            s.id: s
            for s in Student.query.filter(
                Student.id.in_(common_ids)
            ).all()
        }

        prev_ranks = StudentDataAggregator.get_student_ranks_by_exam(
            prev_exam_id, grade_id
        )
        curr_ranks = StudentDataAggregator.get_student_ranks_by_exam(
            curr_exam_id, grade_id
        )
        total_students = len(curr_ranks)

        # 行为均分
        wings_avg = {}
        ws_rows = (
            db.session.query(
                WingsScore.student_id,
                func.avg(WingsScore.score).label("avg_score"),
            )
            .filter(WingsScore.student_id.in_(common_ids))
            .group_by(WingsScore.student_id)
            .all()
        )
        for r in ws_rows:
            wings_avg[r.student_id] = (
                float(r.avg_score) if r.avg_score else 0
            )

        all_ws = db.session.query(func.avg(WingsScore.score)).scalar()
        avg_behavior = float(all_ws) if all_ws else 50.0

        # 违纪次数
        disc_count = {}
        disc_rows = (
            db.session.query(
                DisciplineRecord.student_id,
                func.count(DisciplineRecord.id).label("cnt"),
            )
            .filter(
                DisciplineRecord.student_id.in_(common_ids),
                DisciplineRecord.status == "active",
            )
            .group_by(DisciplineRecord.student_id)
            .all()
        )
        for r in disc_rows:
            disc_count[r.student_id] = int(r.cnt)

        # 出勤率
        att_rate = {}
        att_rows = (
            db.session.query(
                Attendance.student_id,
                func.count(Attendance.id).label("total_days"),
                func.sum(
                    func.IF(Attendance.status == "present", 1, 0)
                ).label("present_days"),
            )
            .filter(Attendance.student_id.in_(common_ids))
            .group_by(Attendance.student_id)
            .all()
        )
        for r in att_rows:
            if r.total_days and r.total_days > 0:
                att_rate[r.student_id] = round(
                    float(r.present_days or 0)
                    / float(r.total_days)
                    * 100,
                    1,
                )

        # 筛选
        gems = []
        for sid in common_ids:
            s = students.get(sid)
            if not s:
                continue

            prev_t = prev_totals[sid]["total"]
            curr_t = curr_totals[sid]["total"]
            delta = curr_t - prev_t
            curr_rank = curr_ranks.get(sid, total_students)

            if delta <= 0:
                continue
            if curr_rank > total_students * 0.5:
                continue

            b_score = wings_avg.get(sid, 0)
            d_cnt = disc_count.get(sid, 0)
            if b_score < avg_behavior and d_cnt > 2:
                continue

            gems.append(
                {
                    "student": s,
                    "prev_total": prev_t,
                    "curr_total": curr_t,
                    "score_delta": delta,
                    "prev_rank": prev_ranks.get(sid, total_students),
                    "curr_rank": curr_rank,
                    "rank_delta": prev_ranks.get(sid, total_students)
                    - curr_rank,
                    "behavior_score": b_score,
                    "discipline_count": d_cnt,
                    "attendance_rate": att_rate.get(sid, 100.0),
                }
            )

        gems.sort(key=lambda x: x["score_delta"], reverse=True)
        return gems

    @staticmethod
    def build_gem_context(gem):
        """为隐形好学生构建 LLM 上下文（增值评价专用）"""
        s = gem["student"]
        cls_name = (
            s.class_.name
            if hasattr(s, "class_") and s.class_
            else ""
        )
        lines = [
            f"姓名: {s.name}",
            f"班级: {cls_name}",
            f"上次考试总分: {gem['prev_total']:.1f} (排名第{gem['prev_rank']}名)",
            f"本次考试总分: {gem['curr_total']:.1f} (排名第{gem['curr_rank']}名)",
            f"进步: +{gem['score_delta']:.1f}分",
            f"五翼行为均分: {gem['behavior_score']:.1f}",
            f"违纪记录: {gem['discipline_count']}条",
            f"出勤率: {gem['attendance_rate']:.1f}%",
        ]
        return "\n".join(lines)
