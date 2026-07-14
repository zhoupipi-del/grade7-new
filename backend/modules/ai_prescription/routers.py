"""
AI 德育处方大脑 — API 路由
双核心端点：班级诊断 + 学生干预
异步 Celery 模式：202 Accepted → 轮询结果
"""

from __future__ import annotations

import logging

from celery.result import AsyncResult
from core.routers import UserRole, get_current_user, get_db, require_role
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from modules.ai_prescription.aggregator import AIPrescriptionAggregator
from modules.ai_prescription.models import (
    AIPrescription,
)
from modules.ai_prescription.schemas import (
    ClassDiagnosisRequest,
    PrescriptionHistoryOut,
    PrescriptionResultOut,
    PrescriptionTaskOut,
    StudentInterventionRequest,
    TaskStatusOut,
)
from modules.ai_prescription.tasks import (
    celery_engine,
    generate_class_diagnosis,
    generate_student_intervention,
)
from sqlalchemy import select, text

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI 德育处方"])


# ─────────────────────────────────────────────
# 核心端点：提交诊断 / 干预任务
# ─────────────────────────────────────────────


@router.post(
    "/class-diagnosis",
    response_model=PrescriptionTaskOut,
    status_code=202,
    summary="发起班级月度诊断（异步）",
)
async def create_class_diagnosis(
    body: ClassDiagnosisRequest,
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    提交班级德育诊断任务，立即返回 task_id
    客户端需轮询 /tasks/{task_id} 获取结果
    """
    # 权限校验：年级组长 / 校管理员
    require_role(UserRole.GRADE_LEADER, UserRole.MS_ADMIN)(current_user)

    school_id = current_user.school_id

    # 校验班级存在（直接查询 classes 表）
    clazz_result = await db.execute(
        text("SELECT id, name FROM classes WHERE id = :class_id AND school_id = :school_id"),
        {"class_id": body.class_id, "school_id": school_id},
    )
    clazz_row = clazz_result.fetchone()
    if not clazz_row:
        raise HTTPException(status_code=404, detail="班级不存在")

    # 组装黄金上下文
    context = await AIPrescriptionAggregator.build_class_context(
        db, body.class_id, school_id, body.semester, body.analysis_days
    )

    # 提交 Celery 异步任务
    task: AsyncResult = generate_class_diagnosis.delay(context, current_user.id, school_id)

    logger.info(
        "[AI-Router] 班级诊断任务已提交：task_id=%s, class_id=%s, user=%s",
        task.id,
        body.class_id,
        current_user.username,
    )

    return {
        "task_id": task.id,
        "status": "PENDING",
        "message": "AI 班级诊断任务已提交，请轮询 /tasks/{task_id} 获取结果",
    }


@router.post(
    "/student-intervention",
    response_model=PrescriptionTaskOut,
    status_code=202,
    summary="发起学生心理干预话术生成（异步）",
)
async def create_student_intervention(
    body: StudentInterventionRequest,
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    提交学生心理干预话术生成任务，立即返回 task_id
    客户端需轮询 /tasks/{task_id} 获取结果
    """
    require_role(
        UserRole.CLASS_TEACHER,
        UserRole.GRADE_LEADER,
        UserRole.MS_ADMIN,
    )(current_user)

    school_id = current_user.school_id

    # 校验学生存在（直接查询 students 表）
    student_result = await db.execute(
        text(
            "SELECT id, name, class_id, student_no "
            "FROM students "
            "WHERE id = :student_id AND school_id = :school_id"
        ),
        {"student_id": body.student_id, "school_id": school_id},
    )
    student_row = student_result.fetchone()
    if not student_row:
        raise HTTPException(status_code=404, detail="学生不存在")

    # 组装黄金上下文
    context = await AIPrescriptionAggregator.build_student_context(
        db, body.student_id, school_id, body.analysis_days
    )

    # 提交 Celery 任务
    task: AsyncResult = generate_student_intervention.delay(context, current_user.id, school_id)

    logger.info(
        "[AI-Router] 学生干预任务已提交：task_id=%s, student_id=%s, user=%s",
        task.id,
        body.student_id,
        current_user.username,
    )

    return {
        "task_id": task.id,
        "status": "PENDING",
        "message": "AI 学生干预话术生成任务已提交，请轮询 /tasks/{task_id} 获取结果",
    }


# ─────────────────────────────────────────────
# 任务轮询端点
# ─────────────────────────────────────────────


@router.get(
    "/tasks/{task_id}",
    response_model=TaskStatusOut,
    summary="轮询 AI 任务状态",
)
async def poll_task_status(task_id: str):
    """
    轮询 Celery 任务状态
    - PENDING：排队中
    - PROGRESS：执行中（本实现暂未用 custom state）
    - SUCCESS：完成（返回 record_id + risk_level + summary）
    - FAILURE：失败（返回 error）
    """
    task = AsyncResult(task_id, app=celery_engine)

    response = {
        "task_id": task_id,
        "status": task.state,
        "result": None,
        "error": None,
    }

    if task.state == "SUCCESS":
        result = task.result
        response["result"] = {
            "record_id": result.get("record_id"),
            "risk_level": result.get("risk_level"),
            "summary": result.get("summary"),
        }
    elif task.state == "FAILURE":
        response["error"] = str(task.info) if task.info else "未知错误"

    return response


@router.get(
    "/tasks/{task_id}/result",
    response_model=PrescriptionResultOut,
    summary="获取 AI 任务完整结果（含 Markdown）",
)
async def get_task_result(
    task_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    任务 SUCCESS 后，通过 record_id 读取完整结果（含 full_text Markdown）
    """
    task = AsyncResult(task_id, app=celery_engine)

    if task.state != "SUCCESS":
        raise HTTPException(status_code=400, detail=f"任务尚未完成，当前状态：{task.state}")

    record_id = task.result.get("record_id")
    if not record_id:
        raise HTTPException(status_code=500, detail="任务结果中缺少 record_id")

    # 读取完整记录
    record = await db.scalar(
        select(AIPrescription).where(
            AIPrescription.id == record_id,
            AIPrescription.school_id == current_user.school_id,
        )
    )
    if not record:
        raise HTTPException(status_code=404, detail="处方记录不存在")

    return {
        "record_id": record.id,
        "prescription_type": record.prescription_type.value,
        "target_id": record.target_id,
        "target_type": record.target_type,
        "risk_level": record.risk_level.value if record.risk_level else None,
        "summary": record.summary,
        "full_text": record.full_text,
        "raw_snapshot": record.raw_snapshot,
        "creator_id": record.creator_id,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


# ─────────────────────────────────────────────
# 历史处方列表
# ─────────────────────────────────────────────


@router.get(
    "/history",
    response_model=PrescriptionHistoryOut,
    summary="查询历史 AI 处方列表（分页）",
)
async def list_prescription_history(
    prescription_type: str | None = Query(None, description="CLASS_DIAGNOSIS / STUDENT_INTV"),
    target_id: int | None = Query(None, description="按目标 ID 过滤"),
    target_type: str | None = Query(None, description="student / class"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    分页查询本校历史 AI 处方记录
    支持按类型 + 目标 ID + 目标类型过滤
    """

    school_id = current_user.school_id

    # 构建查询（条件列表复用）
    conditions = [AIPrescription.school_id == school_id]
    if prescription_type:
        conditions.append(AIPrescription.prescription_type == prescription_type)
    if target_id is not None:
        conditions.append(AIPrescription.target_id == target_id)
    if target_type:
        conditions.append(AIPrescription.target_type == target_type)

    stmt = select(AIPrescription).where(*conditions)

    # 统计总数（与查询同口径）
    from sqlalchemy import func

    total = await db.scalar(select(func.count()).select_from(AIPrescription).where(*conditions))

    # 分页查询（最新在前）
    records = await db.execute(
        stmt.order_by(AIPrescription.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = records.scalars().all()

    # 组装响应（附带创建人姓名）
    items = []
    for r in rows:
        creator_name = None
        if r.creator_id:
            # 直接查询 users 表（Wings 3.0 中无 users ORM 模型）
            user_result = await db.execute(
                text("SELECT username FROM users WHERE id = :user_id"),
                {"user_id": r.creator_id},
            )
            user_row = user_result.fetchone()
            if user_row:
                creator_name = user_row.username
        items.append(
            {
                "id": r.id,
                "prescription_type": r.prescription_type.value,
                "target_id": r.target_id,
                "target_type": r.target_type,
                "risk_level": r.risk_level.value if r.risk_level else None,
                "summary": r.summary,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "creator_name": creator_name,
            }
        )

    return {"total": total or 0, "items": items}


# ─────────────────────────────────────────────
# 单条处方详情
# ─────────────────────────────────────────────


@router.get(
    "/records/{record_id}",
    response_model=PrescriptionResultOut,
    summary="获取单条处方完整详情",
)
async def get_prescription_detail(
    record_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取历史处方的完整内容（含 full_text）"""
    record = await db.scalar(
        select(AIPrescription).where(
            AIPrescription.id == record_id,
            AIPrescription.school_id == current_user.school_id,
        )
    )
    if not record:
        raise HTTPException(status_code=404, detail="处方记录不存在")

    return {
        "record_id": record.id,
        "prescription_type": record.prescription_type.value,
        "target_id": record.target_id,
        "target_type": record.target_type,
        "risk_level": record.risk_level.value if record.risk_level else None,
        "summary": record.summary,
        "full_text": record.full_text,
        "raw_snapshot": record.raw_snapshot,
        "creator_id": record.creator_id,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
