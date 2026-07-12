"""
modules/class_mgmt/routers.py — 班级管理 API 路由
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User, UserRole
from core.routers import get_db, get_current_user, require_role, verify_school_access
from modules.class_mgmt.schemas import (
    ClassCreate, ClassUpdate, ClassOut,
    AssignStudentsRequest, TransferStudentRequest, AssignTeacherRequest,
    ClassChangeLogOut, ClassStatsOut,
)
from modules.class_mgmt.services import ClassMgmtService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["class-mgmt"])

MGMT_ROLES = (UserRole.MS_ADMIN, UserRole.GRADE_LEADER)


@router.post("/classes", response_model=ClassOut, status_code=201)
async def create_class(
    body: ClassCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*MGMT_ROLES)),
):
    """创建班级"""
    try:
        cls = await ClassMgmtService.create_class(db, current_user.school_id, body)
        result = await ClassMgmtService.get_class(db, cls.id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/classes")
async def list_classes(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    grade_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """班级列表"""
    items, total = await ClassMgmtService.list_classes(
        db, current_user.school_id, grade_id, page, page_size
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/classes/{class_id}", response_model=ClassOut)
async def get_class(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """班级详情"""
    result = await ClassMgmtService.get_class(db, class_id)
    if not result:
        raise HTTPException(status_code=404, detail="班级不存在")
    verify_school_access(result["school_id"], current_user)
    return result


@router.put("/classes/{class_id}", response_model=ClassOut)
async def update_class(
    class_id: int,
    body: ClassUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*MGMT_ROLES)),
):
    """更新班级信息"""
    try:
        await ClassMgmtService.update_class(db, class_id, body)
        result = await ClassMgmtService.get_class(db, class_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/classes/{class_id}/assign-students")
async def assign_students(
    class_id: int,
    body: AssignStudentsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*MGMT_ROLES)),
):
    """学生分班"""
    try:
        result = await ClassMgmtService.assign_students(
            db, current_user.school_id, class_id,
            body.student_ids, current_user.id, current_user.display_name,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/classes/transfer-student")
async def transfer_student(
    body: TransferStudentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*MGMT_ROLES)),
):
    """学生调班"""
    try:
        result = await ClassMgmtService.transfer_student(
            db, current_user.school_id,
            body.student_id, body.target_class_id,
            current_user.id, current_user.display_name,
            body.reason,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/classes/{class_id}/assign-teacher", response_model=ClassOut)
async def assign_teacher(
    class_id: int,
    body: AssignTeacherRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """分配班主任"""
    try:
        await ClassMgmtService.assign_head_teacher(
            db, current_user.school_id, class_id,
            body.head_teacher_id, current_user.id, current_user.display_name,
        )
        result = await ClassMgmtService.get_class(db, class_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/classes/{class_id}/students")
async def get_class_students(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """班级学生名单"""
    students = await ClassMgmtService.get_class_students(db, class_id)
    return {"class_id": class_id, "total": len(students), "students": students}


@router.get("/stats", response_model=ClassStatsOut)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """班级统计"""
    return await ClassMgmtService.get_stats(db, current_user.school_id)
