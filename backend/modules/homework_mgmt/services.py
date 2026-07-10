"""
homework_mgmt/services.py — 作业管理业务逻辑

核心功能:
  1. 作业 CRUD + 状态流转 (draft→published→closed)
  2. 学生提交 (自动判断迟交)
  3. 教师批改 + 错题标记 → 自动写入 error_funnel
  4. 统计看板
"""

from sqlalchemy import select, func, and_, update, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime, timedelta
import logging

from core.models import get_local_now, User, Student, Class
from modules.grades.models import GradeSubject
from .models import (
    HwAssignment, HwSubmission, HwGrading,
    ASSIGNMENT_DRAFT, ASSIGNMENT_PUBLISHED, ASSIGNMENT_CLOSED,
    SUBMISSION_PENDING, SUBMISSION_SUBMITTED, SUBMISSION_LATE, SUBMISSION_GRADED, SUBMISSION_MISSING,
    HW_DAILY, HW_WEEKLY, HW_UNIT_REVIEW, HW_EXAM_PREP,
    GRADE_EXCELLENT, GRADE_GOOD, GRADE_FAIR, GRADE_NEEDS_IMPROVEMENT,
)
from .schemas import (
    AssignmentCreate, AssignmentUpdate, AssignmentResponse,
    SubmissionCreate, SubmissionResponse,
    GradingCreate, GradingResponse,
    DashboardResponse,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────

def _calculate_grade(percentage: float) -> str:
    """根据得分率计算等级"""
    if percentage >= 90:
        return GRADE_EXCELLENT
    elif percentage >= 75:
        return GRADE_GOOD
    elif percentage >= 60:
        return GRADE_FAIR
    else:
        return GRADE_NEEDS_IMPROVEMENT


async def _get_teacher_names_batch(db: AsyncSession, user_ids: List[int]) -> Dict[int, str]:
    """批量获取教师姓名"""
    if not user_ids:
        return {}
    result = await db.execute(
        select(User.id, User.display_name).where(User.id.in_(user_ids))
    )
    return {row[0]: row[1] for row in result.all()}


async def _get_student_names_batch(db: AsyncSession, student_ids: List[int]) -> Dict[int, str]:
    """批量获取学生姓名"""
    if not student_ids:
        return {}
    result = await db.execute(
        select(Student.id, Student.name).where(Student.id.in_(student_ids))
    )
    return {row[0]: row[1] for row in result.all()}


async def _get_subject_names_batch(db: AsyncSession, subject_ids: List[int]) -> Dict[int, str]:
    """批量获取科目名"""
    if not subject_ids:
        return {}
    result = await db.execute(
        select(GradeSubject.id, GradeSubject.name).where(GradeSubject.id.in_(subject_ids))
    )
    return {row[0]: row[1] for row in result.all()}


async def _get_class_names_batch(db: AsyncSession, class_ids: List[int]) -> Dict[int, str]:
    """批量获取班级名"""
    if not class_ids:
        return {}
    result = await db.execute(
        select(Class.id, Class.name).where(Class.id.in_(class_ids))
    )
    return {row[0]: row[1] for row in result.all()}


async def _enrich_assignment(db: AsyncSession, a: HwAssignment, submission_stats: Optional[dict] = None) -> dict:
    """将 ORM 对象转换为带关联名称的 dict"""
    teacher_map = await _get_teacher_names_batch(db, [a.teacher_id])
    subject_map = await _get_subject_names_batch(db, [a.subject_id])
    class_map = await _get_class_names_batch(db, [a.class_id]) if a.class_id else {}

    stats = submission_stats or {}
    return {
        "id": a.id,
        "school_id": a.school_id,
        "teacher_id": a.teacher_id,
        "teacher_name": teacher_map.get(a.teacher_id, f"教师{a.teacher_id}"),
        "subject_id": a.subject_id,
        "subject_name": subject_map.get(a.subject_id, f"科目{a.subject_id}"),
        "class_id": a.class_id,
        "class_name": class_map.get(a.class_id, "") if a.class_id else None,
        "grade_id": a.grade_id,
        "title": a.title,
        "description": a.description,
        "homework_type": a.homework_type,
        "assigned_date": a.assigned_date,
        "due_date": a.due_date,
        "status": a.status,
        "knowledge_point_ids": a.knowledge_point_ids or [],
        "attachment_url": a.attachment_url,
        "total_score": float(a.total_score) if a.total_score else 100.0,
        "submission_count": stats.get("submission_count", 0),
        "graded_count": stats.get("graded_count", 0),
        "total_students": stats.get("total_students", 0),
        "created_at": a.created_at,
    }


# ──────────────────────────────────────────────
# 作业 CRUD
# ──────────────────────────────────────────────

async def create_assignment(
    db: AsyncSession, school_id: int, teacher_id: int, data: AssignmentCreate,
) -> HwAssignment:
    """创建作业"""
    assignment = HwAssignment(
        school_id=school_id,
        teacher_id=teacher_id,
        subject_id=data.subject_id,
        class_id=data.class_id,
        grade_id=data.grade_id,
        title=data.title,
        description=data.description,
        homework_type=data.homework_type,
        assigned_date=data.assigned_date,
        due_date=data.due_date,
        status=ASSIGNMENT_PUBLISHED,
        knowledge_point_ids=data.knowledge_point_ids,
        attachment_url=data.attachment_url,
        total_score=data.total_score,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return assignment


async def list_assignments(
    db: AsyncSession, school_id: int,
    teacher_id: Optional[int] = None,
    class_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = 1, page_size: int = 20,
) -> Tuple[List[dict], int]:
    """列出作业"""
    conditions = [HwAssignment.school_id == school_id]
    if teacher_id:
        conditions.append(HwAssignment.teacher_id == teacher_id)
    if class_id:
        conditions.append(HwAssignment.class_id == class_id)
    if subject_id:
        conditions.append(HwAssignment.subject_id == subject_id)
    if status:
        conditions.append(HwAssignment.status == status)

    where_clause = and_(*conditions)

    # 总数
    count_result = await db.execute(
        select(func.count(HwAssignment.id)).where(where_clause)
    )
    total = count_result.scalar() or 0

    # 分页查询
    result = await db.execute(
        select(HwAssignment)
        .where(where_clause)
        .order_by(HwAssignment.assigned_date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    assignments = result.scalars().all()

    # 批量查询提交统计
    items = []
    for a in assignments:
        sub_stats = await _get_assignment_submission_stats(db, school_id, a.id)
        items.append(await _enrich_assignment(db, a, sub_stats))

    return items, total


async def _get_assignment_submission_stats(db: AsyncSession, school_id: int, assignment_id: int) -> dict:
    """获取单个作业的提交统计"""
    result = await db.execute(
        select(
            func.count(HwSubmission.id).label("submission_count"),
            func.sum(case((HwSubmission.status == SUBMISSION_GRADED, 1), else_=0)).label("graded_count"),
        ).where(
            and_(
                HwSubmission.school_id == school_id,
                HwSubmission.assignment_id == assignment_id,
            )
        )
    )
    row = result.one_or_none()
    return {
        "submission_count": row.submission_count or 0 if row else 0,
        "graded_count": row.graded_count or 0 if row else 0,
        "total_students": 0,  # TODO: 按班级学生数计算
    }


async def get_assignment(db: AsyncSession, school_id: int, assignment_id: int) -> Optional[HwAssignment]:
    """获取单个作业"""
    result = await db.execute(
        select(HwAssignment).where(
            and_(
                HwAssignment.school_id == school_id,
                HwAssignment.id == assignment_id,
            )
        )
    )
    return result.scalar_one_or_none()


async def update_assignment(
    db: AsyncSession, school_id: int, assignment_id: int, data: AssignmentUpdate,
) -> Optional[HwAssignment]:
    """更新作业"""
    assignment = await get_assignment(db, school_id, assignment_id)
    if not assignment:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(assignment, key, value)

    await db.commit()
    await db.refresh(assignment)
    return assignment


async def close_assignment(db: AsyncSession, school_id: int, assignment_id: int) -> Optional[HwAssignment]:
    """关闭作业 — 将未提交的标记为missing"""
    assignment = await get_assignment(db, school_id, assignment_id)
    if not assignment:
        return None

    assignment.status = ASSIGNMENT_CLOSED

    # 将pending的提交标记为missing
    await db.execute(
        update(HwSubmission)
        .where(
            and_(
                HwSubmission.school_id == school_id,
                HwSubmission.assignment_id == assignment_id,
                HwSubmission.status == SUBMISSION_PENDING,
            )
        )
        .values(status=SUBMISSION_MISSING)
    )

    await db.commit()
    await db.refresh(assignment)
    return assignment


# ──────────────────────────────────────────────
# 学生提交
# ──────────────────────────────────────────────

async def submit_homework(
    db: AsyncSession, school_id: int, assignment_id: int, student_id: int,
    data: SubmissionCreate,
) -> Optional[HwSubmission]:
    """学生提交作业 — 自动判断迟交"""
    assignment = await get_assignment(db, school_id, assignment_id)
    if not assignment:
        return None

    now = get_local_now()
    is_late = now > assignment.due_date
    late_minutes = int((now - assignment.due_date).total_seconds() / 60) if is_late else 0

    # 检查是否已提交
    existing = await db.execute(
        select(HwSubmission).where(
            and_(
                HwSubmission.school_id == school_id,
                HwSubmission.assignment_id == assignment_id,
                HwSubmission.student_id == student_id,
            )
        )
    )
    submission = existing.scalar_one_or_none()

    if submission:
        # 更新已有提交
        submission.content = data.content
        submission.attachment_url = data.attachment_url
        submission.submitted_at = now
        submission.status = SUBMISSION_LATE if is_late else SUBMISSION_SUBMITTED
        submission.late_minutes = late_minutes
    else:
        # 新建提交
        submission = HwSubmission(
            school_id=school_id,
            assignment_id=assignment_id,
            student_id=student_id,
            content=data.content,
            attachment_url=data.attachment_url,
            submitted_at=now,
            status=SUBMISSION_LATE if is_late else SUBMISSION_SUBMITTED,
            late_minutes=late_minutes,
        )
        db.add(submission)

    await db.commit()
    await db.refresh(submission)
    return submission


async def list_submissions(
    db: AsyncSession, school_id: int, assignment_id: int,
    status: Optional[str] = None,
) -> Tuple[List[dict], int]:
    """列出作业的所有提交"""
    conditions = [
        HwSubmission.school_id == school_id,
        HwSubmission.assignment_id == assignment_id,
    ]
    if status:
        conditions.append(HwSubmission.status == status)

    result = await db.execute(
        select(HwSubmission)
        .where(and_(*conditions))
        .order_by(HwSubmission.submitted_at.desc())
    )
    submissions = result.scalars().all()

    # 批量获取学生名
    student_ids = [s.student_id for s in submissions]
    student_map = await _get_student_names_batch(db, student_ids)

    # 批量获取批改信息
    sub_ids = [s.id for s in submissions]
    grading_map = {}
    if sub_ids:
        grading_result = await db.execute(
            select(HwGrading).where(
                and_(
                    HwGrading.school_id == school_id,
                    HwGrading.submission_id.in_(sub_ids),
                )
            )
        )
        for g in grading_result.scalars().all():
            grading_map[g.submission_id] = {
                "score": float(g.score) if g.score else None,
                "max_score": float(g.max_score) if g.max_score else 100.0,
                "score_percentage": float(g.score_percentage) if g.score_percentage else None,
                "grade": g.grade,
                "feedback": g.feedback,
                "error_count": g.error_count,
                "graded_at": g.graded_at,
            }

    items = []
    for s in submissions:
        items.append({
            "id": s.id,
            "assignment_id": s.assignment_id,
            "student_id": s.student_id,
            "student_name": student_map.get(s.student_id, f"学生{s.student_id}"),
            "content": s.content,
            "attachment_url": s.attachment_url,
            "submitted_at": s.submitted_at,
            "status": s.status,
            "late_minutes": s.late_minutes,
            "created_at": s.created_at,
            "grading": grading_map.get(s.id),
        })

    return items, len(items)


async def get_student_submission(
    db: AsyncSession, school_id: int, assignment_id: int, student_id: int,
) -> Optional[dict]:
    """获取学生在某作业的提交"""
    result = await db.execute(
        select(HwSubmission).where(
            and_(
                HwSubmission.school_id == school_id,
                HwSubmission.assignment_id == assignment_id,
                HwSubmission.student_id == student_id,
            )
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return None

    student_map = await _get_student_names_batch(db, [sub.student_id])

    # 获取批改
    grading = None
    g_result = await db.execute(
        select(HwGrading).where(
            and_(
                HwGrading.school_id == school_id,
                HwGrading.submission_id == sub.id,
            )
        )
    )
    g = g_result.scalar_one_or_none()
    if g:
        grading = {
            "score": float(g.score) if g.score else None,
            "max_score": float(g.max_score) if g.max_score else 100.0,
            "score_percentage": float(g.score_percentage) if g.score_percentage else None,
            "grade": g.grade,
            "feedback": g.feedback,
            "error_items": g.error_items or [],
            "error_count": g.error_count,
            "graded_at": g.graded_at,
        }

    return {
        "id": sub.id,
        "assignment_id": sub.assignment_id,
        "student_id": sub.student_id,
        "student_name": student_map.get(sub.student_id, f"学生{sub.student_id}"),
        "content": sub.content,
        "attachment_url": sub.attachment_url,
        "submitted_at": sub.submitted_at,
        "status": sub.status,
        "late_minutes": sub.late_minutes,
        "created_at": sub.created_at,
        "grading": grading,
    }


# ──────────────────────────────────────────────
# 教师批改 + 错题标记 → error_funnel
# ──────────────────────────────────────────────

async def grade_submission(
    db: AsyncSession, school_id: int, submission_id: int,
    teacher_id: int, data: GradingCreate,
) -> Optional[dict]:
    """教师批改提交 — 含错题标记，自动同步到 error_funnel"""
    # 获取提交
    sub_result = await db.execute(
        select(HwSubmission).where(
            and_(
                HwSubmission.school_id == school_id,
                HwSubmission.id == submission_id,
            )
        )
    )
    submission = sub_result.scalar_one_or_none()
    if not submission:
        return None

    # 计算得分率
    score = data.score
    max_score = data.max_score
    percentage = round(score / max_score * 100, 1) if max_score > 0 else 0
    grade = _calculate_grade(percentage)

    # 序列化错题
    error_items_data = []
    if data.error_items:
        for ei in data.error_items:
            error_items_data.append({
                "question_no": ei.question_no,
                "question_content": ei.question_content,
                "question_type": ei.question_type,
                "student_answer": ei.student_answer,
                "correct_answer": ei.correct_answer,
                "error_type": ei.error_type,
                "knowledge_point_ids": ei.knowledge_point_ids or [],
                "difficulty": ei.difficulty,
            })

    # 检查是否已有批改
    existing_result = await db.execute(
        select(HwGrading).where(
            and_(
                HwGrading.school_id == school_id,
                HwGrading.submission_id == submission_id,
            )
        )
    )
    grading = existing_result.scalar_one_or_none()

    if grading:
        grading.teacher_id = teacher_id
        grading.score = score
        grading.max_score = max_score
        grading.score_percentage = percentage
        grading.grade = grade
        grading.feedback = data.feedback
        grading.error_items = error_items_data if error_items_data else None
        grading.error_count = len(error_items_data)
        grading.graded_at = get_local_now()
    else:
        grading = HwGrading(
            school_id=school_id,
            submission_id=submission_id,
            teacher_id=teacher_id,
            score=score,
            max_score=max_score,
            score_percentage=percentage,
            grade=grade,
            feedback=data.feedback,
            error_items=error_items_data if error_items_data else None,
            error_count=len(error_items_data),
            graded_at=get_local_now(),
        )
        db.add(grading)

    # 更新提交状态为已批改
    submission.status = SUBMISSION_GRADED

    await db.commit()
    await db.refresh(grading)

    # ── 自动同步错题到 error_funnel ──
    if error_items_data:
        try:
            await _sync_errors_to_funnel(
                db, school_id, submission.student_id,
                submission.assignment_id, error_items_data,
            )
        except Exception as e:
            logger.error(f"同步错题到 error_funnel 失败: {e}")

    # 获取教师名
    teacher_map = await _get_teacher_names_batch(db, [grading.teacher_id])

    return {
        "id": grading.id,
        "submission_id": grading.submission_id,
        "teacher_id": grading.teacher_id,
        "teacher_name": teacher_map.get(grading.teacher_id, f"教师{grading.teacher_id}"),
        "score": float(grading.score) if grading.score else None,
        "max_score": float(grading.max_score) if grading.max_score else 100.0,
        "score_percentage": float(grading.score_percentage) if grading.score_percentage else None,
        "grade": grading.grade,
        "feedback": grading.feedback,
        "error_items": grading.error_items or [],
        "error_count": grading.error_count,
        "graded_at": grading.graded_at,
    }


async def _sync_errors_to_funnel(
    db: AsyncSession, school_id: int, student_id: int,
    assignment_id: int, error_items: List[dict],
) -> None:
    """将批改标记的错题同步到 error_funnel 模块"""
    try:
        from modules.error_funnel.services import ingest_errors_from_homework
        await ingest_errors_from_homework(
            db, school_id, student_id, assignment_id, error_items,
        )
    except ImportError:
        logger.warning("error_funnel 模块未安装，跳过错题同步")
    except Exception as e:
        logger.error(f"同步错题失败: {e}")


# ──────────────────────────────────────────────
# 看板统计
# ──────────────────────────────────────────────

async def get_dashboard(
    db: AsyncSession, school_id: int,
    teacher_id: Optional[int] = None,
    class_id: Optional[int] = None,
) -> dict:
    """作业管理看板统计"""
    conditions = [HwAssignment.school_id == school_id]
    if teacher_id:
        conditions.append(HwAssignment.teacher_id == teacher_id)
    if class_id:
        conditions.append(HwAssignment.class_id == class_id)

    where_clause = and_(*conditions)

    # 作业总数
    total_result = await db.execute(
        select(func.count(HwAssignment.id)).where(where_clause)
    )
    total_assignments = total_result.scalar() or 0

    # 进行中作业
    active_result = await db.execute(
        select(func.count(HwAssignment.id)).where(
            and_(where_clause, HwAssignment.status == ASSIGNMENT_PUBLISHED)
        )
    )
    active_assignments = active_result.scalar() or 0

    # 提交总数 (关联查询)
    sub_conditions = [HwSubmission.school_id == school_id]
    if teacher_id or class_id:
        sub_query = select(HwAssignment.id).where(where_clause)
        sub_conditions.append(HwSubmission.assignment_id.in_(sub_query))

    total_sub_result = await db.execute(
        select(func.count(HwSubmission.id)).where(and_(*sub_conditions))
    )
    total_submissions = total_sub_result.scalar() or 0

    # 待批改数
    pending_result = await db.execute(
        select(func.count(HwSubmission.id)).where(
            and_(*sub_conditions, HwSubmission.status.in_([SUBMISSION_SUBMITTED, SUBMISSION_LATE]))
        )
    )
    pending_grading = pending_result.scalar() or 0

    # 平均分
    avg_result = await db.execute(
        select(func.avg(HwGrading.score_percentage)).where(
            and_(
                HwGrading.school_id == school_id,
                HwGrading.score_percentage.isnot(None),
            )
        )
    )
    avg_val = avg_result.scalar()
    avg_score = float(avg_val) if avg_val else None

    # 按类型统计
    type_result = await db.execute(
        select(
            HwAssignment.homework_type,
            func.count(HwAssignment.id),
        ).where(where_clause).group_by(HwAssignment.homework_type)
    )
    by_type = {row[0]: row[1] for row in type_result.all()}

    # 最近作业
    recent_result = await db.execute(
        select(HwAssignment)
        .where(where_clause)
        .order_by(HwAssignment.assigned_date.desc())
        .limit(5)
    )
    recent = []
    for a in recent_result.scalars().all():
        stats = await _get_assignment_submission_stats(db, school_id, a.id)
        recent.append(await _enrich_assignment(db, a, stats))

    # 错题热点 (按error_type统计)
    error_hotspots = []
    try:
        from modules.error_funnel.models import ErrorBookItem
        error_result = await db.execute(
            select(
                ErrorBookItem.error_type,
                func.count(ErrorBookItem.id),
            ).where(
                and_(
                    ErrorBookItem.school_id == school_id,
                    ErrorBookItem.source_type == "homework",
                )
            ).group_by(ErrorBookItem.error_type)
        )
        error_hotspots = [{"error_type": row[0], "count": row[1]} for row in error_result.all()]
    except Exception:
        pass

    return {
        "total_assignments": total_assignments,
        "active_assignments": active_assignments,
        "total_submissions": total_submissions,
        "pending_grading": pending_grading,
        "avg_score": round(avg_score, 1) if avg_score else None,
        "avg_completion_rate": None,
        "by_type": by_type,
        "recent_assignments": recent,
        "error_hotspots": error_hotspots,
    }
