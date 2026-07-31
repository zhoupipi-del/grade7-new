"""
error_funnel/routers.py — 错题断层漏斗引擎 API 端点

端点清单 (14端点):
  知识点: GET/ POST/ PUT/{id}
  错题本: GET/ POST/ GET/{id} PUT/{id}/resolve
  断层:   GET/ GET/{id} POST/{id}/resolve POST/{id}/generate-prescription
  看板:   GET/dashboard
  导入:   POST/import-from-exam
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from core.routers import get_db, get_current_user, require_role
from core.models import User, UserRole

from .schemas import (
    KnowledgePointCreate, KnowledgePointUpdate, KnowledgePointResponse,
    ErrorItemCreate, ErrorItemResponse,
    KnowledgeGapResponse,
    DashboardResponse,
    BatchImportFromExam,
)
from . import services as svc

MGMT_ROLES = [UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER]

router = APIRouter(tags=["错题断层"])


# ──────────────────────────────────────────────
# 知识点管理
# ──────────────────────────────────────────────

@router.get("/knowledge-points")
async def list_knowledge_points(
    subject_id: Optional[int] = Query(None),
    parent_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """列出知识点"""
    return await svc.list_knowledge_points(
        db, user.school_id, subject_id=subject_id, parent_id=parent_id,
    )


@router.post("/knowledge-points", status_code=201, dependencies=[Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER))])
async def create_knowledge_point(
    data: KnowledgePointCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建知识点"""
    kp = await svc.create_knowledge_point(db, user.school_id, data)
    return {"id": kp.id, "name": kp.name, "code": kp.code}


@router.put("/knowledge-points/{kp_id}", dependencies=[Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER))])
async def update_knowledge_point(
    kp_id: int,
    data: KnowledgePointUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新知识点"""
    kp = await svc.update_knowledge_point(db, user.school_id, kp_id, data)
    if not kp:
        raise HTTPException(404, "知识点不存在")
    return {"id": kp.id, "name": kp.name}


# ──────────────────────────────────────────────
# 错题本
# ──────────────────────────────────────────────

@router.get("/errors")
async def list_error_items(
    student_id: Optional[int] = Query(None),
    subject_id: Optional[int] = Query(None),
    source_type: Optional[str] = Query(None),
    error_type: Optional[str] = Query(None),
    is_resolved: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """列出错题本条目"""
    # 班主任只能看自己班学生, 家长只能看自己孩子
    filter_student_id = student_id
    if user.role.upper() == "PARENT":
        filter_student_id = user.bound_student_id
        if not filter_student_id:
            raise HTTPException(403, "未绑定学生")

    items, total = await svc.list_error_items(
        db, user.school_id,
        student_id=filter_student_id,
        subject_id=subject_id,
        source_type=source_type,
        error_type=error_type,
        is_resolved=is_resolved,
        page=page, page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/errors", status_code=201, dependencies=[Depends(require_role(*MGMT_ROLES))])
async def add_error_item(
    data: ErrorItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """手动添加错题"""
    item = await svc.add_error_item(db, user.school_id, data)
    return {"id": item.id, "student_id": item.student_id, "question_content": item.question_content[:100]}


@router.put("/errors/{error_id}/resolve", dependencies=[Depends(require_role(*MGMT_ROLES))])
async def resolve_error_item(
    error_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """标记错题为已纠错"""
    item = await svc.resolve_error_item(db, user.school_id, error_id)
    if not item:
        raise HTTPException(404, "错题不存在")
    return {"id": item.id, "is_resolved": item.is_resolved}


# ──────────────────────────────────────────────
# 知识点断层
# ──────────────────────────────────────────────

@router.get("/gaps")
async def list_gaps(
    student_id: Optional[int] = Query(None),
    subject_id: Optional[int] = Query(None),
    gap_level: Optional[str] = Query(None),
    gap_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """列出知识点断层"""
    filter_student_id = student_id
    if user.role.upper() == "PARENT":
        filter_student_id = user.bound_student_id
        if not filter_student_id:
            raise HTTPException(403, "未绑定学生")

    items, total = await svc.list_gaps(
        db, user.school_id,
        student_id=filter_student_id,
        subject_id=subject_id,
        gap_level=gap_level,
        gap_status=gap_status,
        page=page, page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/gaps/{gap_id}/resolve", dependencies=[Depends(require_role(*MGMT_ROLES))])
async def resolve_gap(
    gap_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """标记断层为已解决"""
    gap = await svc.resolve_gap(db, user.school_id, gap_id)
    if not gap:
        raise HTTPException(404, "断层记录不存在")
    return {"id": gap.id, "gap_status": gap.gap_status}


@router.post("/gaps/{gap_id}/generate-prescription", dependencies=[Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER))])
async def generate_prescription(
    gap_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """为知识点断层生成 AI 处方 (调用 DeepSeek)"""
    result = await svc.generate_ai_prescription(db, user.school_id, gap_id)
    if not result:
        raise HTTPException(404, "断层记录不存在")
    return result


# ──────────────────────────────────────────────
# 看板
# ──────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(
    student_id: Optional[int] = Query(None),
    subject_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """错题断层看板"""
    filter_student_id = student_id
    if user.role.upper() == "PARENT":
        filter_student_id = user.bound_student_id
        if not filter_student_id:
            raise HTTPException(403, "未绑定学生")

    return await svc.get_dashboard(
        db, user.school_id,
        student_id=filter_student_id,
        subject_id=subject_id,
    )


# ──────────────────────────────────────────────
# 从考试成绩批量导入
# ──────────────────────────────────────────────

@router.post("/import-from-exam", dependencies=[Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER))])
async def import_from_exam(
    data: BatchImportFromExam,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """从考试成绩批量导入错题 — 得分率低于阈值的学生自动生成"""
    return await svc.batch_import_from_exam(
        db, user.school_id, data.exam_id, data.subject_id, data.threshold,
    )
