"""
modules/ai_teacher_assistant/tools/compare_exam_performance.py — V2

考试比较 Tool：自动发现最近两场考试 → matched cohort → 比较。
不返回 student_id / student_name / 单生成绩。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date as date_type  # noqa: F401
from statistics import mean
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from modules.grades.models import GradeExam, GradeRecord, GradeSubject


class ExamMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    exam_date: str | None = None
    exam_type: str | None = None
    student_count: int = 0
    subject_count: int = 0


class ExamSubjectComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: int
    subject_name: str
    full_score: float | None = None
    matched_students: int = 0
    previous_average: float | None
    current_average: float | None
    delta: float | None
    direction: str


class CompareExamPerformanceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    previous_exam: ExamMeta | None = None
    current_exam: ExamMeta | None = None
    scope_students: int = 0
    matched_students: int = 0
    common_subjects: int = 0
    subjects: list[ExamSubjectComparison] = []


async def compare_exam_performance_handler(
    *,
    db: AsyncSession,
    effective_student_ids: set[int],
    exam_ids: list[int],
    **_: Any,
) -> CompareExamPerformanceOutput:
    """Matched-cohort comparison with exam metadata."""

    if not effective_student_ids:
        return CompareExamPerformanceOutput(scope_students=0)

    # ── Auto-discover ──
    if not exam_ids or len(exam_ids) < 2:
        discovered = await _discover_latest_exam_ids(
            db=db,
            effective_student_ids=effective_student_ids,
            limit=2,
        )
        exam_ids = discovered if discovered else exam_ids

    # Sort by exam_date ascending: [earlier, ..., latest]
    exam_rows_date = (await db.execute(
        select(GradeExam.id, GradeExam.exam_date).where(GradeExam.id.in_(exam_ids))
    )).all()
    id_with_date = [(int(r[0]), r[1]) for r in exam_rows_date if r[1] is not None]
    id_with_date.sort(key=lambda x: x[1])  # chronological
    exam_ids = [x[0] for x in id_with_date]

    if len(exam_ids) < 2:
        return CompareExamPerformanceOutput(scope_students=len(effective_student_ids))

    prev_id, curr_id = exam_ids[-2], exam_ids[-1]
    exam_rows = (await db.execute(
        select(GradeExam).where(GradeExam.id.in_([prev_id, curr_id]))
    )).scalars().all()
    exam_map = {e.id: e for e in exam_rows}

    prev_exam = _build_exam_meta(exam_map.get(prev_id))
    curr_exam = _build_exam_meta(exam_map.get(curr_id))

    # ── Temporal consistency guard ──
    if prev_exam and curr_exam and prev_exam.exam_date and curr_exam.exam_date:
        if prev_exam.exam_date >= curr_exam.exam_date:
            raise ValueError(
                f"compare_exam_performance: previous exam date ({prev_exam.exam_date}) "
                f">= current exam date ({curr_exam.exam_date}) — ordering broken"
            )

    # ── Matched cohort: students who took BOTH exams ──
    prev_students = set(await _exam_student_ids(db, prev_id, effective_student_ids))
    curr_students = set(await _exam_student_ids(db, curr_id, effective_student_ids))
    matched = prev_students & curr_students

    if not matched:
        return CompareExamPerformanceOutput(
            previous_exam=prev_exam, current_exam=curr_exam,
            scope_students=len(effective_student_ids), matched_students=0,
        )

    # ── Common subjects ──
    prev_subjects = set(await _exam_subject_ids(db, prev_id))
    curr_subjects = set(await _exam_subject_ids(db, curr_id))
    common_subject_ids = prev_subjects & curr_subjects

    # ── Subject metadata ──
    subject_rows = (await db.execute(
        select(GradeSubject).where(GradeSubject.id.in_(common_subject_ids))
    )).scalars().all()
    subject_map = {s.id: s for s in subject_rows}

    # ── Scores: matched cohort only ──
    rows = (await db.execute(
        select(GradeRecord.exam_id, GradeRecord.subject_id, GradeRecord.score)
        .where(
            GradeRecord.exam_id.in_([prev_id, curr_id]),
            GradeRecord.student_id.in_(matched),
            GradeRecord.subject_id.in_(common_subject_ids),
            GradeRecord.score.is_not(None),
        )
    )).all()

    scores: dict[tuple[int, int], list[float]] = defaultdict(list)
    for eid, sid, sc in rows:
        scores[(int(eid), int(sid))].append(float(sc))

    result: list[ExamSubjectComparison] = []
    for sid in sorted(common_subject_ids):
        prev_vals = scores.get((prev_id, sid), [])
        curr_vals = scores.get((curr_id, sid), [])
        prev_avg = mean(prev_vals) if prev_vals else None
        curr_avg = mean(curr_vals) if curr_vals else None

        if prev_avg is None or curr_avg is None:
            delta, direction = None, "insufficient_data"
        else:
            delta = round(curr_avg - prev_avg, 2)
            direction = "up" if delta > 1 else "down" if delta < -1 else "stable"

        subj = subject_map.get(sid)
        result.append(ExamSubjectComparison(
            subject_id=sid,
            subject_name=subj.name if subj else str(sid),
            full_score=float(subj.full_score) if subj and subj.full_score else None,
            matched_students=len(curr_vals) if curr_vals else len(prev_vals),
            previous_average=round(prev_avg, 2) if prev_avg else None,
            current_average=round(curr_avg, 2) if curr_avg else None,
            delta=delta, direction=direction,
        ))

    return CompareExamPerformanceOutput(
        previous_exam=prev_exam, current_exam=curr_exam,
        scope_students=len(effective_student_ids),
        matched_students=len(matched),
        common_subjects=len(common_subject_ids),
        subjects=result,
    )


def _build_exam_meta(exam: GradeExam | None) -> ExamMeta | None:
    if exam is None:
        return None
    dt = None
    if hasattr(exam, "exam_date") and exam.exam_date:
        dt = exam.exam_date if isinstance(exam.exam_date, str) else str(exam.exam_date)
    return ExamMeta(
        id=exam.id,
        name=exam.name or "",
        exam_date=dt,  # type: ignore
        exam_type=exam.exam_type,
    )


async def _exam_student_ids(db: AsyncSession, exam_id: int, scope: set[int]) -> list[int]:
    rows = (await db.execute(
        select(distinct(GradeRecord.student_id)).where(
            GradeRecord.exam_id == exam_id,
            GradeRecord.student_id.in_(scope),
            GradeRecord.score.is_not(None),
        )
    )).scalars().all()
    return [int(x) for x in rows]


async def _exam_subject_ids(db: AsyncSession, exam_id: int) -> list[int]:
    rows = (await db.execute(
        select(distinct(GradeRecord.subject_id)).where(
            GradeRecord.exam_id == exam_id,
            GradeRecord.score.is_not(None),
        )
    )).scalars().all()
    return [int(x) for x in rows]


async def _discover_latest_exam_ids(
    *, db: AsyncSession, effective_student_ids: set[int], limit: int = 2,
) -> list[int]:
    """Auto-discover most recent exams by exam_date, not exam_id."""
    if not effective_student_ids:
        return []

    rows = (await db.execute(
        select(GradeExam.id, GradeExam.exam_date)
        .where(
            GradeExam.id.in_(
                select(distinct(GradeRecord.exam_id)).where(
                    GradeRecord.student_id.in_(effective_student_ids),
                    GradeRecord.exam_id.is_not(None),
                    GradeRecord.score.is_not(None),
                )
            ),
            GradeExam.exam_date.is_not(None),
        )
        .order_by(GradeExam.exam_date.desc())
        .limit(limit)
    )).all()

    return [int(x[0]) for x in rows]


# ═══════════════════════════════════════════════════════════════
#  Copilot handler（V2 多工具编排路径，经 ToolExecutor 执行）
#  ★ 比较调用发生在 handler 内部，不绕过 ToolExecutor
#  ★ 只返回 matched-cohort 的科目均分对比，绝不携带 student_id / 单生成绩
# ═══════════════════════════════════════════════════════════════

async def compare_exam_performance_copilot_handler(run=None, **_) -> Dict[str, Any]:
    """V2 Copilot 执行点：经 ToolExecutor 调用，内部比较考试表现。"""
    run = run or {}
    db = run["db"]
    effective_student_ids = run.get("effective_student_ids") or set()
    args = run.get("args", {}) or {}
    output = await compare_exam_performance_handler(
        db=db,
        effective_student_ids=effective_student_ids,
        exam_ids=args.get("exam_ids") or [],
    )
    return {
        "status": "EXECUTED",
        "domain": "grades",
        "result": output.model_dump() if hasattr(output, "model_dump") else output,
        "actual_classification": "internal",
    }
