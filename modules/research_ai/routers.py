"""
modules/research_ai/routers.py
===============================
教研 AI 工具 API 路由。

V2.1 修复（生产上线前审计）：
  - [P0] 作文详情/复核增加 teacher_id 所有权校验（普通教师只能看/改自己的记录）
  - [P0] 教师复核 final_score 后端校验 <= total_score_config
  - [P0] LessonTaskOut 使用 selectinload 避免 Async SQLAlchemy lazy-load 500
  - [P1] 删除假 concurrency 配置（UI可选但实际无效），后端不再接收/存储
  - GRADE_LEADER/MS_ADMIN 可查看本校所有教师记录（年级组长管理需要）

挂载前缀：/api/v1/research_ai
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.models import User, UserRole, get_local_now
from core.routers import get_current_user, get_db, require_role
from modules.research_ai.models_essay import EssayGradeRecord
from modules.research_ai.models_homework import HomeworkTask
from modules.research_ai.models_lesson_plan import LessonPlanItem, LessonPlanTask
from modules.research_ai.models_paper import PaperTask
from modules.research_ai.models_analysis import AnalysisTask
from modules.research_ai.models_comment import CommentTask
from modules.research_ai.schemas import (
    EssayGradeIn,
    EssayGradeOut,
    EssayHistoryOut,
    EssayReviewIn,
    HomeworkCreateIn,
    HomeworkOut,
    LessonBatchCreateIn,
    LessonTaskOut,
    PaperCreateIn,
    PaperOut,
    AnalysisCreateIn,
    AnalysisOut,
    CommentCreateIn,
    CommentOut,
)
from modules.research_ai.services_essay import grade_essay
from modules.research_ai.tasks import (
    generate_analysis,
    generate_comments,
    generate_homework,
    generate_lesson_plan,
    generate_paper,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["教研 AI"])

TEACHING_ROLES = (
    UserRole.TEACHER,
    UserRole.CLASS_TEACHER,
    UserRole.GRADE_LEADER,
    UserRole.MS_ADMIN,
)

# 可跨教师查看/操作的管理角色
CROSS_TEACHER_ROLES = (UserRole.GRADE_LEADER, UserRole.MS_ADMIN)

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

# [P0 安全] 输出目录必须与 SEC-001 后的非 root 写路径一致
OUTPUT_DIR = os.environ.get(
    "RESEARCH_AI_OUTPUT_DIR", "/opt/wings3/shared/uploads/research_ai"
)


def _check_role(current_user: User) -> None:
    require_role(*TEACHING_ROLES)(current_user)


def _can_access_teacher_record(current_user: User, record_teacher_id: int) -> bool:
    """
    判断当前用户是否有权访问某教师的记录。
    - 记录创建者本人：可以
    - 年级组长/管理员：可以查看本校所有教师
    - 其他普通教师：不可以（防同校横向越权）
    """
    if record_teacher_id == current_user.id:
        return True
    return current_user.role in CROSS_TEACHER_ROLES


# ════════════════════════════════════════════════════════════
# 批量教案生成
# ════════════════════════════════════════════════════════════

@router.post(
    "/lesson-plans/batch",
    response_model=LessonTaskOut,
    status_code=202,
    summary="提交批量教案生成任务",
)
async def create_lesson_batch(
    body: LessonBatchCreateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    school_id = current_user.school_id

    task = LessonPlanTask(
        school_id=school_id,
        created_by=current_user.id,
        task_name=body.task_name,
        status="pending",
        total_count=len(body.items),
    )
    db.add(task)
    await db.flush()

    for it in body.items:
        item = LessonPlanItem(
            task_id=task.id,
            school_id=school_id,
            subject=it.subject,
            textbook=it.textbook,
            grade=it.grade,
            unit=it.unit,
            topic=it.topic,
            periods=it.periods,
            key_point=it.key_point,
            diff_point=it.diff_point,
            status="pending",
        )
        db.add(item)
    await db.commit()
    await db.refresh(task)

    # 逐篇派发 Celery（worker concurrency 实际控制并行度）
    result = await db.execute(
        select(LessonPlanItem.id).where(LessonPlanItem.task_id == task.id)
    )
    for (item_id,) in result.all():
        generate_lesson_plan.apply_async(args=[item_id], queue="high_priority")

    task.status = "processing"
    db.add(task)
    await db.commit()
    # [P0] 使用 selectinload 预加载 items，避免 Pydantic 序列化时 lazy-load
    await db.refresh(task, attribute_names=["items"])
    logger.info(
        "[ResearchAI] 教案批量任务已提交 task=%s items=%s user=%s",
        task.id, task.total_count, current_user.username,
    )
    return task


@router.get(
    "/lesson-plans/batch",
    response_model=list[LessonTaskOut],
    summary="教案批量任务列表",
)
async def list_lesson_batches(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    # [P0] selectinload 预加载 items
    result = await db.execute(
        select(LessonPlanTask)
        .options(selectinload(LessonPlanTask.items))
        .where(LessonPlanTask.school_id == current_user.school_id)
        .order_by(desc(LessonPlanTask.created_at))
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get(
    "/lesson-plans/batch/{task_id}",
    response_model=LessonTaskOut,
    summary="教案批量任务详情",
)
async def get_lesson_batch(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    result = await db.execute(
        select(LessonPlanTask)
        .options(selectinload(LessonPlanTask.items))
        .where(LessonPlanTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task or task.school_id != current_user.school_id:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/lesson-plans/items/{item_id}/download", summary="下载单篇教案 docx")
async def download_lesson_docx(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    item = await db.get(LessonPlanItem, item_id)
    if not item or item.school_id != current_user.school_id:
        raise HTTPException(status_code=404, detail="教案不存在")
    if item.status != "success" or not item.file_path:
        raise HTTPException(status_code=400, detail="教案尚未生成完成")

    file_path = (Path(OUTPUT_DIR) / item.file_path).resolve()
    output_root = Path(OUTPUT_DIR).resolve()
    if output_root not in file_path.parents or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    filename = item.file_name or os.path.basename(file_path)
    return FileResponse(
        path=str(file_path),
        media_type=DOCX_MEDIA_TYPE,
        filename=filename,
    )


# ════════════════════════════════════════════════════════════
# AI 作文批改（同步）
# ════════════════════════════════════════════════════════════

@router.post(
    "/essay/grade",
    response_model=EssayGradeOut,
    summary="AI 作文批改（同步，约 30-60 秒）",
)
async def api_grade_essay(
    body: EssayGradeIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    rec = EssayGradeRecord(
        school_id=current_user.school_id,
        teacher_id=current_user.id,
        student_id=body.student_id,
        # [P0 隐私] student_name 仅存库用于教师本地显示，不发给 LLM
        student_name=body.student_name,
        subject=body.subject,
        grade=body.grade,
        total_score_config=body.total_score_config,
        essay_prompt=body.essay_prompt,
        essay_text=body.essay_text,
        rubric=body.rubric,
        review_status="pending",
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)

    await grade_essay(db, rec.id)
    await db.refresh(rec)
    return rec


@router.get(
    "/essay/records",
    response_model=list[EssayHistoryOut],
    summary="作文批改历史列表",
)
async def list_essay_records(
    subject: str | None = Query(None, pattern="^(chinese|english)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    # 普通教师只看自己的；年级组长/管理员可看全校
    q = select(EssayGradeRecord).where(
        EssayGradeRecord.school_id == current_user.school_id,
    )
    if current_user.role not in CROSS_TEACHER_ROLES:
        q = q.where(EssayGradeRecord.teacher_id == current_user.id)
    if subject:
        q = q.where(EssayGradeRecord.subject == subject)
    q = (
        q.order_by(desc(EssayGradeRecord.created_at))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(q)
    return result.scalars().all()


@router.get(
    "/essay/records/{record_id}",
    response_model=EssayGradeOut,
    summary="作文批改记录详情",
)
async def get_essay_record(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    rec = await db.get(EssayGradeRecord, record_id)
    if not rec or rec.school_id != current_user.school_id:
        raise HTTPException(status_code=404, detail="记录不存在")
    # [P0] 同校横向越权修复：普通教师只能看自己的作文记录
    if not _can_access_teacher_record(current_user, rec.teacher_id):
        raise HTTPException(status_code=404, detail="记录不存在")
    return rec


@router.post(
    "/essay/records/{record_id}/review",
    response_model=EssayGradeOut,
    summary="教师复核（修改分数/评语）",
)
async def review_essay(
    record_id: int,
    body: EssayReviewIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    rec = await db.get(EssayGradeRecord, record_id)
    if not rec or rec.school_id != current_user.school_id:
        raise HTTPException(status_code=404, detail="记录不存在")
    # [P0] 同校横向越权修复：不能复核别人的作文
    if not _can_access_teacher_record(current_user, rec.teacher_id):
        raise HTTPException(status_code=404, detail="记录不存在")

    if body.final_score is not None:
        # [P0] 后端校验 final_score 不超过卷面总分
        if body.final_score > rec.total_score_config:
            raise HTTPException(
                status_code=422,
                detail=f"最终分数不能超过卷面总分 {rec.total_score_config}",
            )
        rec.final_score = body.final_score
    elif rec.final_score is None:
        rec.final_score = rec.ai_total_score  # 默认采纳 AI 分
    if body.teacher_comment is not None:
        rec.teacher_comment = body.teacher_comment
    rec.review_status = "reviewed"
    rec.reviewed_by = current_user.id
    rec.reviewed_at = get_local_now()
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec


# ════════════════════════════════════════════════════════════
# 分层作业设计
# ════════════════════════════════════════════════════════════

@router.post(
    "/homework",
    response_model=HomeworkOut,
    status_code=202,
    summary="提交分层作业生成任务",
)
async def create_homework(
    body: HomeworkCreateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    task = HomeworkTask(
        school_id=current_user.school_id,
        created_by=current_user.id,
        subject=body.subject,
        grade=body.grade,
        textbook=body.textbook,
        unit=body.unit,
        topic=body.topic,
        knowledge_points=body.knowledge_points,
        class_profile=body.class_profile,
        question_counts=body.question_counts,
        difficulty_distribution=body.difficulty_distribution,
        estimated_minutes=body.estimated_minutes,
        include_answers=body.include_answers,
        extra_requirements=body.extra_requirements,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    generate_homework.apply_async(args=[task.id], queue="high_priority")
    logger.info(
        "[ResearchAI] 分层作业任务已提交 task=%s user=%s",
        task.id, current_user.username,
    )
    return task


@router.get(
    "/homework",
    response_model=list[HomeworkOut],
    summary="分层作业列表",
)
async def list_homework(
    subject: str | None = Query(None, max_length=50),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    q = select(HomeworkTask).where(
        HomeworkTask.school_id == current_user.school_id,
        HomeworkTask.created_by == current_user.id,
    )
    if subject:
        q = q.where(HomeworkTask.subject == subject)
    q = (
        q.order_by(desc(HomeworkTask.created_at))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(q)
    return result.scalars().all()


@router.get(
    "/homework/{task_id}",
    response_model=HomeworkOut,
    summary="分层作业详情",
)
async def get_homework(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    task = await db.get(HomeworkTask, task_id)
    # [P0 V2.1.1] 详情同样校验 created_by，与列表策略一致（仅本人）
    if (
        not task
        or task.school_id != current_user.school_id
        or task.created_by != current_user.id
    ):
        raise HTTPException(status_code=404, detail="作业不存在")
    return task


@router.get("/homework/{task_id}/download", summary="下载分层作业 docx")
async def download_homework(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    task = await db.get(HomeworkTask, task_id)
    # [P0 V2.1.1] 下载同样校验 created_by，防止同校横向越权
    if (
        not task
        or task.school_id != current_user.school_id
        or task.created_by != current_user.id
    ):
        raise HTTPException(status_code=404, detail="作业不存在")
    if task.status != "success" or not task.file_path:
        raise HTTPException(status_code=400, detail="作业尚未生成完成")

    file_path = (Path(OUTPUT_DIR) / task.file_path).resolve()
    output_root = Path(OUTPUT_DIR).resolve()
    if output_root not in file_path.parents or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    filename = task.file_name or os.path.basename(file_path)
    return FileResponse(
        path=str(file_path),
        media_type=DOCX_MEDIA_TYPE,
        filename=filename,
    )



# ════════════════════════════════════════════════════════════
# V2.2 新功能：AI 试卷命制
# ════════════════════════════════════════════════════════════

@router.post(
    "/paper",
    response_model=PaperOut,
    status_code=202,
    summary="提交试卷命制任务",
)
async def create_paper(
    body: PaperCreateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    task = PaperTask(
        school_id=current_user.school_id,
        created_by=current_user.id,
        subject=body.subject,
        grade=body.grade,
        textbook=body.textbook,
        unit=body.unit,
        topic=body.topic,
        knowledge_points=body.knowledge_points,
        question_types=body.question_types,
        total_score=body.total_score,
        difficulty=body.difficulty,
        include_answers=body.include_answers,
        extra_requirements=body.extra_requirements,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    generate_paper.apply_async(args=[task.id], queue="high_priority")
    logger.info(
        "[ResearchAI] 试卷命制任务已提交 task=%s user=%s",
        task.id, current_user.username,
    )
    return task


@router.get(
    "/paper",
    response_model=list[PaperOut],
    summary="试卷命制任务列表",
)
async def list_paper(
    subject: str | None = Query(None, max_length=50),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    q = select(PaperTask).where(
        PaperTask.school_id == current_user.school_id,
        PaperTask.created_by == current_user.id,
    )
    if subject:
        q = q.where(PaperTask.subject == subject)
    q = q.order_by(desc(PaperTask.created_at)).limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.get(
    "/paper/{task_id}",
    response_model=PaperOut,
    summary="试卷命制任务详情",
)
async def get_paper(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    task = await db.get(PaperTask, task_id)
    if (
        not task
        or task.school_id != current_user.school_id
        or task.created_by != current_user.id
    ):
        raise HTTPException(status_code=404, detail="试卷任务不存在")
    return task


@router.get("/paper/{task_id}/download", summary="下载试卷 docx")
async def download_paper(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    task = await db.get(PaperTask, task_id)
    if (
        not task
        or task.school_id != current_user.school_id
        or task.created_by != current_user.id
    ):
        raise HTTPException(status_code=404, detail="试卷任务不存在")
    if task.status != "success" or not task.file_path:
        raise HTTPException(status_code=400, detail="试卷尚未生成完成")

    file_path = (Path(OUTPUT_DIR) / task.file_path).resolve()
    output_root = Path(OUTPUT_DIR).resolve()
    if output_root not in file_path.parents or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    filename = task.file_name or os.path.basename(file_path)
    return FileResponse(
        path=str(file_path),
        media_type=DOCX_MEDIA_TYPE,
        filename=filename,
    )


# ════════════════════════════════════════════════════════════
# V2.2 新功能：AI 学情分析报告
# ════════════════════════════════════════════════════════════

@router.post(
    "/analysis",
    response_model=AnalysisOut,
    status_code=202,
    summary="提交学情分析任务",
)
async def create_analysis(
    body: AnalysisCreateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    task = AnalysisTask(
        school_id=current_user.school_id,
        created_by=current_user.id,
        scope_name=body.scope_name,
        subject=body.subject,
        grade=body.grade,
        exam_name=body.exam_name,
        data_summary=body.data_summary,
        analysis_focus=body.analysis_focus,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    generate_analysis.apply_async(args=[task.id], queue="high_priority")
    logger.info(
        "[ResearchAI] 学情分析任务已提交 task=%s user=%s",
        task.id, current_user.username,
    )
    return task


@router.get(
    "/analysis",
    response_model=list[AnalysisOut],
    summary="学情分析任务列表",
)
async def list_analysis(
    subject: str | None = Query(None, max_length=50),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    q = select(AnalysisTask).where(
        AnalysisTask.school_id == current_user.school_id,
        AnalysisTask.created_by == current_user.id,
    )
    if subject:
        q = q.where(AnalysisTask.subject == subject)
    q = q.order_by(desc(AnalysisTask.created_at)).limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.get(
    "/analysis/{task_id}",
    response_model=AnalysisOut,
    summary="学情分析任务详情",
)
async def get_analysis(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    task = await db.get(AnalysisTask, task_id)
    if (
        not task
        or task.school_id != current_user.school_id
        or task.created_by != current_user.id
    ):
        raise HTTPException(status_code=404, detail="学情分析任务不存在")
    return task


@router.get("/analysis/{task_id}/download", summary="下载学情分析报告 docx")
async def download_analysis(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    task = await db.get(AnalysisTask, task_id)
    if (
        not task
        or task.school_id != current_user.school_id
        or task.created_by != current_user.id
    ):
        raise HTTPException(status_code=404, detail="学情分析任务不存在")
    if task.status != "success" or not task.file_path:
        raise HTTPException(status_code=400, detail="报告尚未生成完成")

    file_path = (Path(OUTPUT_DIR) / task.file_path).resolve()
    output_root = Path(OUTPUT_DIR).resolve()
    if output_root not in file_path.parents or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    filename = task.file_name or os.path.basename(file_path)
    return FileResponse(
        path=str(file_path),
        media_type=DOCX_MEDIA_TYPE,
        filename=filename,
    )


# ════════════════════════════════════════════════════════════
# V2.2 新功能：AI 学生评语生成
# ════════════════════════════════════════════════════════════

@router.post(
    "/comments",
    response_model=CommentOut,
    status_code=202,
    summary="提交学生评语生成任务",
)
async def create_comments(
    body: CommentCreateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    students = [s.model_dump() for s in body.students]
    task = CommentTask(
        school_id=current_user.school_id,
        created_by=current_user.id,
        class_name=body.class_name,
        term=body.term,
        comment_type=body.comment_type,
        students=students,
        student_count=len(students),
        style=body.style,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    generate_comments.apply_async(args=[task.id], queue="high_priority")
    logger.info(
        "[ResearchAI] 学生评语任务已提交 task=%s students=%s user=%s",
        task.id, task.student_count, current_user.username,
    )
    return task


@router.get(
    "/comments",
    response_model=list[CommentOut],
    summary="学生评语任务列表",
)
async def list_comments(
    comment_type: str | None = Query(None, max_length=50),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    q = select(CommentTask).where(
        CommentTask.school_id == current_user.school_id,
        CommentTask.created_by == current_user.id,
    )
    if comment_type:
        q = q.where(CommentTask.comment_type == comment_type)
    q = q.order_by(desc(CommentTask.created_at)).limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.get(
    "/comments/{task_id}",
    response_model=CommentOut,
    summary="学生评语任务详情",
)
async def get_comments(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    task = await db.get(CommentTask, task_id)
    if (
        not task
        or task.school_id != current_user.school_id
        or task.created_by != current_user.id
    ):
        raise HTTPException(status_code=404, detail="评语任务不存在")
    return task


@router.get("/comments/{task_id}/download", summary="下载学生评语 docx")
async def download_comments(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_role(current_user)
    task = await db.get(CommentTask, task_id)
    if (
        not task
        or task.school_id != current_user.school_id
        or task.created_by != current_user.id
    ):
        raise HTTPException(status_code=404, detail="评语任务不存在")
    if task.status != "success" or not task.file_path:
        raise HTTPException(status_code=400, detail="评语尚未生成完成")

    file_path = (Path(OUTPUT_DIR) / task.file_path).resolve()
    output_root = Path(OUTPUT_DIR).resolve()
    if output_root not in file_path.parents or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    filename = task.file_name or os.path.basename(file_path)
    return FileResponse(
        path=str(file_path),
        media_type=DOCX_MEDIA_TYPE,
        filename=filename,
    )
