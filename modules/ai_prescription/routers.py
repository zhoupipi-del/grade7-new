"""
AI 德育处方大脑 — API 路由
双核心端点：班级诊断 + 学生干预
异步 Celery 模式：202 Accepted → 轮询结果
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from celery.result import AsyncResult
from core.models import User, Student, Class as SchoolClass
from core.routers import UserRole, get_current_user, get_db, require_role
from core.psych_capability import require_psych_access, PSY_DETAIL
from core.access import role_str
from core.ratelimit import ai_prescription_rate_limit
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from modules.ai_prescription.aggregator import AIPrescriptionAggregator
from modules.ai_prescription.models import (
    AIPrescription,
    PrescriptionType,
    ReviewStatus,
)
from modules.ai_prescription.schemas import (
    ClassDiagnosisRequest,
    ModifyRequest,
    PrescriptionHistoryOut,
    PrescriptionResultOut,
    PrescriptionTaskOut,
    ReviewNoteRequest,
    ReviewResultOut,
    StudentInterventionRequest,
    TaskStatusOut,
)
from modules.ai_prescription.tasks import (
    activate_prescription_after_review,
    celery_engine,
    generate_class_diagnosis,
    generate_student_intervention,
)
from sqlalchemy import select, text
from sqlalchemy import or_

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
    dependencies=[Depends(ai_prescription_rate_limit)],
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
    dependencies=[Depends(ai_prescription_rate_limit)],
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
async def poll_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
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
    review_status: str | None = Query(None, description="PENDING_REVIEW / CONFIRMED / MODIFIED / REJECTED"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    分页查询本校历史 AI 处方记录
    支持按类型 + 目标 ID + 目标类型过滤
    """

    # S0-2 P0 修复（SEC-INC-20260810-001）：
    #   此前端点零守卫 + 仅 school_id 过滤 → 家长/学生可读全校 AI 干预记录，
    #   含 full_text/raw_snapshot 涉心理/处分/成绩敏感字段。
    #   修法：角色闸排除 PARENT/STUDENT；教师/年级组长按行级 scope 收口。
    _role = current_user.role if isinstance(current_user.role, UserRole) else UserRole(current_user.role)
    if _role not in (UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER):
        raise HTTPException(status_code=403, detail="无权查看 AI 处方")

    school_id = current_user.school_id

    # 构建查询（条件列表复用）
    conditions = [AIPrescription.school_id == school_id]

    # 行级 scope（按 prescription_type/target_type 分流强制覆盖）
    if _role == UserRole.CLASS_TEACHER:
        bound_cid = getattr(current_user, "class_id", None)
        if not bound_cid:
            raise HTTPException(status_code=403, detail="班主任未绑定班级，无权查看 AI 处方")
        if prescription_type == "CLASS_DIAGNOSIS" or target_type == "class":
            conditions.append(AIPrescription.target_id == bound_cid)
        elif prescription_type == "STUDENT_INTV" or target_type == "student":
            conditions.append(
                AIPrescription.target_id.in_(
                    select(Student.id).where(
                        Student.class_id == bound_cid,
                        Student.school_id == school_id,
                    )
                )
            )
        else:
            # 未指定类型：限定 target_id 是本班 OR 本班学生
            conditions.append(
                or_(
                    AIPrescription.target_id == bound_cid,
                    AIPrescription.target_id.in_(
                        select(Student.id).where(
                            Student.class_id == bound_cid,
                            Student.school_id == school_id,
                        )
                    ),
                )
            )
    elif _role == UserRole.GRADE_LEADER:
        bound_gid = getattr(current_user, "grade_id", None)
        if not bound_gid:
            raise HTTPException(status_code=403, detail="年级组长未绑定年级，无权查看 AI 处方")
        if prescription_type == "CLASS_DIAGNOSIS" or target_type == "class":
            conditions.append(
                AIPrescription.target_id.in_(
                    select(SchoolClass.id).where(
                        SchoolClass.grade_id == bound_gid,
                        SchoolClass.school_id == school_id,
                    )
                )
            )
        elif prescription_type == "STUDENT_INTV" or target_type == "student":
            conditions.append(
                AIPrescription.target_id.in_(
                    select(Student.id).where(
                        Student.grade_id == bound_gid,
                        Student.school_id == school_id,
                    )
                )
            )
        else:
            # 未指定类型：本年级班级 OR 本年级学生
            conditions.append(
                or_(
                    AIPrescription.target_id.in_(
                        select(SchoolClass.id).where(
                            SchoolClass.grade_id == bound_gid,
                            SchoolClass.school_id == school_id,
                        )
                    ),
                    AIPrescription.target_id.in_(
                        select(Student.id).where(
                            Student.grade_id == bound_gid,
                            Student.school_id == school_id,
                        )
                    ),
                )
            )
    # MS_ADMIN: 保持全校

    if prescription_type:
        conditions.append(AIPrescription.prescription_type == prescription_type)
    if target_id is not None:
        conditions.append(AIPrescription.target_id == target_id)
    if target_type:
        conditions.append(AIPrescription.target_type == target_type)
    if review_status:
        conditions.append(AIPrescription.review_status == review_status)

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
                "review_status": r.review_status.value if r.review_status else None,
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
    # S0-2 P0 修复（SEC-INC-20260810-001）：角色闸 + 行级归属校验
    _role = current_user.role if isinstance(current_user.role, UserRole) else UserRole(current_user.role)
    if _role not in (UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER):
        raise HTTPException(status_code=403, detail="无权查看 AI 处方")

    record = await db.scalar(
        select(AIPrescription).where(
            AIPrescription.id == record_id,
            AIPrescription.school_id == current_user.school_id,
        )
    )
    if not record:
        raise HTTPException(status_code=404, detail="处方记录不存在")

    # 行级归属校验（按 target_type 决定查 Student 还是 SchoolClass）
    if _role == UserRole.CLASS_TEACHER:
        bound_cid = getattr(current_user, "class_id", None)
        if not bound_cid:
            raise HTTPException(status_code=403, detail="班主任未绑定班级，无权查看 AI 处方")
        if record.target_type == "class":
            if record.target_id != bound_cid:
                raise HTTPException(status_code=403, detail="无权查看其他班级的处方")
        elif record.target_type == "student":
            stu = await db.scalar(
                select(Student).where(
                    Student.id == record.target_id,
                    Student.school_id == current_user.school_id,
                )
            )
            if not stu or stu.class_id != bound_cid:
                raise HTTPException(status_code=403, detail="无权查看其他班级学生的处方")
    elif _role == UserRole.GRADE_LEADER:
        bound_gid = getattr(current_user, "grade_id", None)
        if not bound_gid:
            raise HTTPException(status_code=403, detail="年级组长未绑定年级，无权查看 AI 处方")
        if record.target_type == "class":
            cls = await db.scalar(
                select(SchoolClass).where(
                    SchoolClass.id == record.target_id,
                    SchoolClass.school_id == current_user.school_id,
                )
            )
            if not cls or cls.grade_id != bound_gid:
                raise HTTPException(status_code=403, detail="无权查看其他年级班级的处方")
        elif record.target_type == "student":
            stu = await db.scalar(
                select(Student).where(
                    Student.id == record.target_id,
                    Student.school_id == current_user.school_id,
                )
            )
            if not stu or stu.grade_id != bound_gid:
                raise HTTPException(status_code=403, detail="无权查看其他年级学生的处方")
    # MS_ADMIN: pass

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
# CF-04 人工复核（Human Review Gate）
# ─────────────────────────────────────────────


async def require_prescription_review_access(db, user, prescription) -> None:
    """CF-04 人审授权（不绕过 CF-01 心理授权）：

    - 心理来源处方 (STUDENT_INTV) → 仅 active counselor assignment 覆盖该学生可复核
      （require_psych_access 写审计；ms_admin / 年级组长 / 班主任 一律 403）。
    - 非心理处方 (CLASS_DIAGNOSIS) → 有 scope 的管理责任角色
      （ms_admin 全校 / grade_leader 本年级 / class_teacher 本班）。
    绝不以 user.role 给 ms_admin 默认心理复核权。
    """
    if prescription.prescription_type == PrescriptionType.STUDENT_INTV:
        level = await require_psych_access(
            db, user, prescription.target_id,
            resource_type="ai_prescription",
            action="review",
            purpose="human_review_psych_prescription",
        )
        if level != PSY_DETAIL:
            raise HTTPException(
                status_code=403,
                detail="无权复核心理处方（需心理专业授权 counselor）",
            )
        return

    # 非心理：班级诊断 → 班级管理责任
    clazz = await db.scalar(
        select(SchoolClass).where(
            SchoolClass.id == prescription.target_id,
            SchoolClass.school_id == user.school_id,
        )
    )
    if clazz is None:
        raise HTTPException(status_code=404, detail="班级不存在")
    role = role_str(user)
    if role in ("ms_admin", "group_admin", "branch_admin"):
        return
    if role == "grade_leader" and user.grade_id and clazz.grade_id == user.grade_id:
        return
    if role == "class_teacher" and user.class_id and clazz.id == user.class_id:
        return
    raise HTTPException(
        status_code=403,
        detail="无权复核该班级处方（需对应年级/班级管理责任）",
    )


async def _get_reviewable_prescription(db, record_id: int, current_user) -> AIPrescription:
    """CF-04: 装载处方 + 人审授权（心理走 CF-01，非心理走 scope 管理责任）"""
    record = await db.scalar(
        select(AIPrescription).where(
            AIPrescription.id == record_id,
            AIPrescription.school_id == current_user.school_id,
        )
    )
    if not record:
        raise HTTPException(status_code=404, detail="处方记录不存在")
    # 历史遗留（review_status=NULL，legacy_unreviewed）不可复核，先于此做硬闸，
    # 避免对根本不可复核的 legacy 记录写心理审计。
    if record.review_status is None:
        raise HTTPException(status_code=409, detail="legacy_prescription_not_reviewable")
    await require_prescription_review_access(db, current_user, record)
    return record


def _ensure_pending(record) -> None:
    """CF-04: 状态机锁死——NULL=历史遗留不可复核；CONFIRMED/MODIFIED/REJECTED 为终态不可重复复核"""
    if record.review_status is None:
        # 历史 163 行 review_status=NULL（legacy_unreviewed），不可 activate
        raise HTTPException(
            status_code=409,
            detail="legacy_prescription_not_reviewable",
        )
    if record.review_status != ReviewStatus.PENDING_REVIEW:
        current = record.review_status.value if record.review_status else "UNKNOWN"
        raise HTTPException(
            status_code=409,
            detail=f"处方已复核（当前状态 {current}），终态不可重复复核",
        )


@router.post(
    "/records/{record_id}/confirm",
    response_model=ReviewResultOut,
    summary="人工确认采用 AI 处方（CF-04 人审闸）",
)
async def confirm_prescription(
    record_id: int,
    body: ReviewNoteRequest | None = Body(default=None),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """人工确认采用 AI 原输出。RDI 桥接处方才触发 bridge（审批工单 + 通知班主任）。"""
    record = await _get_reviewable_prescription(db, record_id, current_user)
    _ensure_pending(record)
    record.review_status = ReviewStatus.CONFIRMED
    record.reviewed_by = current_user.id
    record.reviewed_at = datetime.now(timezone.utc)
    record.review_note = body.review_note if body else None
    await db.commit()

    is_rdi = (record.raw_snapshot or {}).get("trigger") == "rdi_bridge"
    if is_rdi:
        activate_prescription_after_review.delay(record_id, current_user.school_id)

    return {
        "id": record.id,
        "review_status": record.review_status.value,
        "reviewed_by": record.reviewed_by,
        "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
        "review_note": record.review_note,
        "modified_content": None,
        "bridged": is_rdi,
    }


@router.post(
    "/records/{record_id}/modify",
    response_model=ReviewResultOut,
    summary="人工修改后采用 AI 处方（CF-04 人审闸，不覆盖 AI 原文）",
)
async def modify_prescription(
    record_id: int,
    body: ModifyRequest,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """人工修改后采用。改动写入 modified_content/modified_payload，不覆盖 AI 原文。"""
    record = await _get_reviewable_prescription(db, record_id, current_user)
    _ensure_pending(record)
    record.review_status = ReviewStatus.MODIFIED
    record.reviewed_by = current_user.id
    record.reviewed_at = datetime.now(timezone.utc)
    record.review_note = body.review_note
    record.modified_content = body.modified_content
    record.modified_payload = body.modified_payload
    await db.commit()

    is_rdi = (record.raw_snapshot or {}).get("trigger") == "rdi_bridge"
    if is_rdi:
        activate_prescription_after_review.delay(record_id, current_user.school_id)

    return {
        "id": record.id,
        "review_status": record.review_status.value,
        "reviewed_by": record.reviewed_by,
        "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
        "review_note": record.review_note,
        "modified_content": record.modified_content,
        "bridged": is_rdi,
    }


@router.post(
    "/records/{record_id}/reject",
    response_model=ReviewResultOut,
    summary="人工驳回 AI 处方（CF-04 人审闸，永不 bridge）",
)
async def reject_prescription(
    record_id: int,
    body: ReviewNoteRequest | None = Body(default=None),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """人工驳回。REJECTED 为终态，永不触发 bridge、永不进入正式业务。"""
    record = await _get_reviewable_prescription(db, record_id, current_user)
    _ensure_pending(record)
    record.review_status = ReviewStatus.REJECTED
    record.reviewed_by = current_user.id
    record.reviewed_at = datetime.now(timezone.utc)
    record.review_note = body.review_note if body else None
    await db.commit()

    # REJECTED 永不 bridge —— 不调用 activate_prescription_after_review

    return {
        "id": record.id,
        "review_status": record.review_status.value,
        "reviewed_by": record.reviewed_by,
        "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
        "review_note": record.review_note,
        "modified_content": None,
        "bridged": False,
    }
