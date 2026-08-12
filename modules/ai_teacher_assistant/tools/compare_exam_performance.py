"""
modules/ai_teacher_assistant/tools/compare_exam_performance.py — V1 第二个 Tool

考试比较 Tool：接收 EffectiveScope 已批准的 student_ids，只做聚合。
不返回 student_id / student_name / 单生成绩。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from statistics import mean
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.grades.models import GradeExam, GradeRecord, GradeSubject


class ExamSubjectComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: int
    subject_name: str
    previous_average: float | None
    current_average: float | None
    delta: float | None
    direction: str


class CompareExamPerformanceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_ids: list[int]
    student_count: int
    subjects: list[ExamSubjectComparison]


async def compare_exam_performance_handler(
    *,
    db: AsyncSession,
    effective_student_ids: set[int],
    exam_ids: list[int],
    **_: Any,
) -> CompareExamPerformanceOutput:
    """聚合-only。不返回 student_id / student_name / 单生成绩。"""

    if not effective_student_ids:
        return CompareExamPerformanceOutput(
            exam_ids=exam_ids,
            student_count=0,
            subjects=[],
        )

    # Auto-discover latest exams if not provided or insufficient
    if not exam_ids or len(exam_ids) < 2:
        discovered = await _discover_latest_exam_ids(
            db=db,
            effective_student_ids=effective_student_ids,
            limit=2,
        )
        exam_ids = discovered if discovered else exam_ids

    if len(exam_ids) < 2:
        return CompareExamPerformanceOutput(
            exam_ids=exam_ids,
            student_count=len(effective_student_ids),
            subjects=[],
        )

    selected_exam_ids = exam_ids[-2:]

    stmt = (
        select(
            GradeRecord.exam_id,
            GradeRecord.subject_id,
            GradeRecord.score,
            GradeSubject.name,
        )
        .join(
            GradeSubject,
            GradeSubject.id == GradeRecord.subject_id,
        )
        .where(
            GradeRecord.exam_id.in_(selected_exam_ids),
            GradeRecord.student_id.in_(effective_student_ids),
            GradeRecord.score.is_not(None),
        )
    )

    rows = (await db.execute(stmt)).all()

    scores: dict[tuple[int, int], list[float]] = defaultdict(list)
    subject_names: dict[int, str] = {}

    for exam_id, subject_id, score, subject_name in rows:
        scores[(int(exam_id), int(subject_id))].append(float(score))
        subject_names[int(subject_id)] = subject_name

    previous_exam, current_exam = selected_exam_ids
    result: list[ExamSubjectComparison] = []

    for subject_id in sorted(subject_names):
        previous_values = scores.get((previous_exam, subject_id), [])
        current_values = scores.get((current_exam, subject_id), [])

        prev_avg = mean(previous_values) if previous_values else None
        curr_avg = mean(current_values) if current_values else None

        if prev_avg is None or curr_avg is None:
            delta = None
            direction = "insufficient_data"
        else:
            delta = round(curr_avg - prev_avg, 2)
            if delta > 1:
                direction = "up"
            elif delta < -1:
                direction = "down"
            else:
                direction = "stable"

        result.append(
            ExamSubjectComparison(
                subject_id=subject_id,
                subject_name=subject_names[subject_id],
                previous_average=round(prev_avg, 2) if prev_avg is not None else None,
                current_average=round(curr_avg, 2) if curr_avg is not None else None,
                delta=delta,
                direction=direction,
            )
        )

    return CompareExamPerformanceOutput(
        exam_ids=selected_exam_ids,
        student_count=len(effective_student_ids),
        subjects=result,
    )


async def _discover_latest_exam_ids(
    *,
    db: AsyncSession,
    effective_student_ids: set[int],
    limit: int = 2,
) -> list[int]:
    """Auto-discover the most recent exams with actual grade records."""
    if not effective_student_ids:
        return []

    from sqlalchemy import func as _func, distinct as _distinct

    stmt = (
        select(GradeRecord.exam_id)
        .where(
            GradeRecord.student_id.in_(effective_student_ids),
            GradeRecord.exam_id.is_not(None),
            GradeRecord.score.is_not(None),
        )
        .group_by(GradeRecord.exam_id)
        .having(_func.count(_distinct(GradeRecord.student_id)) > 0)
        .order_by(GradeRecord.exam_id.desc())
        .limit(limit)
    )

    rows = (await db.execute(stmt)).scalars().all()
    return [int(x) for x in rows]
