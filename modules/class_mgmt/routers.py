"""
modules/class_mgmt/routers.py — 班级管理 API 路由
"""

import logging

from core.models import User, UserRole
from core.routers import get_db, require_role, verify_school_access
from core.access import (
    load_assignment_scopes, role_str, ROLE_CLASS_WIDE, ROLE_GRADE_WIDE,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from modules.class_mgmt.schemas import (
    AssignStudentsRequest,
    AssignTeacherRequest,
    ClassCreate,
    ClassOut,
    ClassStatsOut,
    ClassUpdate,
    TransferStudentRequest,
)
from modules.class_mgmt.services import ClassMgmtService
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(tags=["class-mgmt"])

MGMT_ROLES = (UserRole.MS_ADMIN, UserRole.GRADE_LEADER)

# P0 修复（2026-08-09 开学前审计）：班级名录属校内管理数据，家长/学生一律禁止访问
STAFF_ROLES = (
    UserRole.MS_ADMIN,
    UserRole.GROUP_ADMIN,
    UserRole.BRANCH_ADMIN,
    UserRole.GRADE_LEADER,
    UserRole.CLASS_TEACHER,
    UserRole.TEACHER,
    UserRole.COUNSELOR,
)


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
    grade_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*STAFF_ROLES)),
):
    """班级列表（家长/学生 403）"""
    items, total = await ClassMgmtService.list_classes(
        db, current_user.school_id, grade_id, page, page_size
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/classes/{class_id}", response_model=ClassOut)
async def get_class(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*STAFF_ROLES)),
):
    """班级详情（家长/学生 403）"""
    result = await ClassMgmtService.get_class(db, class_id)
    if not result:
        raise HTTPException(status_code=404, detail="班级不存在")
    # P0 修复（2026-08-09）：原代码漏 await，协程从未执行 → 跨校校验形同虚设
    await verify_school_access(result["school_id"], current_user, db)
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
            db,
            current_user.school_id,
            class_id,
            body.student_ids,
            current_user.id,
            current_user.display_name,
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
            db,
            current_user.school_id,
            body.student_id,
            body.target_class_id,
            current_user.id,
            current_user.display_name,
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
            db,
            current_user.school_id,
            class_id,
            body.head_teacher_id,
            current_user.id,
            current_user.display_name,
        )
        result = await ClassMgmtService.get_class(db, class_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/classes/{class_id}/students")
async def get_class_students(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*STAFF_ROLES)),
):
    """班级学生名单（家长/学生 403；跨校 404；横向 scope 隔离）"""
    # P0 修复（2026-08-09）：原端点零校级校验，可跨校读取任意班级学生名单
    cls = await ClassMgmtService.get_class(db, class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    # 跨校：404 防校名/班级枚举（与下方越权统一状态码）
    if cls.get("school_id") != current_user.school_id:
        raise HTTPException(status_code=404, detail="班级不存在")
    # UAT-F2 修复（2026-08-17）：班级花名册横向 scope —— 复用权威源
    # load_assignment_scopes（teacher_role_assignments），与 get_student_or_403 同机制；
    # assignment 为权威判定（class_teacher→本班 / grade_leader→本年级），
    # 仅当 assignment 无记录时 fallback 到 users.class_id/grade_id（与既有行为一致，
    # 防止 users.class_id 与真实 assignment 漂移导致越权放大）。
    # 404 而非 403，避免用状态码差异探测班级是否存在。
    scopes = await load_assignment_scopes(db, current_user)
    if scopes["school"]:
        pass  # 全校角色（ms_admin/group_admin/branch_admin/counselor）保持校级现状
    elif cls.get("grade_id") in scopes["grade"]:
        pass  # 年级组长：本年级
    elif class_id in scopes["class"]:
        pass  # 班主任：本班（assignment 权威）
    else:
        role = role_str(current_user)
        allowed = False
        if role in ROLE_CLASS_WIDE and current_user.class_id and current_user.class_id == class_id:
            allowed = True
        if role in ROLE_GRADE_WIDE and current_user.grade_id and current_user.grade_id == cls.get("grade_id"):
            allowed = True
        if not allowed:
            raise HTTPException(status_code=404, detail="班级不存在")
    students = await ClassMgmtService.get_class_students(db, class_id)
    return {"class_id": class_id, "total": len(students), "students": students}


@router.get("/stats", response_model=ClassStatsOut)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*STAFF_ROLES)),
):
    """班级统计（家长/学生 403）"""
    return await ClassMgmtService.get_stats(db, current_user.school_id)
