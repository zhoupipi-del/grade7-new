"""
teacher_mgmt 路由层

端点:
  GET    /teachers                           — 教师列表
  POST   /teachers                           — 创建教师 (一步到位)
  GET    /teachers/{user_id}                 — 教师详情
  PUT    /teachers/{user_id}/extension       — 更新扩展信息
  PUT    /teachers/{user_id}/subjects        — 分配任教学科
  GET    /teachers/{user_id}/workloads       — 查询工作量
  POST   /teachers/{user_id}/workloads       — 新增工作量
  GET    /teachers/{user_id}/workload-stats  — 工作量统计

角色分配 CRUD (双重角色解耦 overlay):
  POST   /teachers/{user_id}/roles           — 分配角色
  GET    /teachers/{user_id}/roles           — 查询角色列表
  PATCH  /teachers/roles/{assignment_id}     — 更新角色 (启用/停用/过期)
  DELETE /teachers/roles/{assignment_id}     — 删除角色分配

核心聚合:
  GET    /teachers/{user_id}/effective-roles — 有效角色集合 (排课+审批+大盘)
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession

from core.routers import get_db, get_current_user, require_role
from core.models import User, UserRole
from modules.teacher_mgmt.services import TeacherService
from modules.teacher_mgmt.schemas import (
    TeacherListResponse, TeacherDetailOut,
    TeacherCreate, TeacherCreateOut,
    TeacherExtensionCreate, TeacherExtensionOut,
    SubjectAssignRequest, SubjectAssignResponse,
    WorkloadCreate, WorkloadOut, WorkloadStatsOut,
    TeacherRoleAssignmentCreate, TeacherRoleAssignmentOut, TeacherRoleAssignmentList,
    EffectiveRolesOut,
)

logger = logging.getLogger("teacher_mgmt.routers")
router = APIRouter()


# ═════════════════════════════════════════════════════════════════════════════════
# 教师列表 + 创建
# ═════════════════════════════════════════════════════════════════════════════════

@router.get("/teachers", response_model=TeacherListResponse)
async def list_teachers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: Optional[str] = Query(None, description="class_teacher / teacher"),
    is_active: Optional[bool] = Query(None),
    keyword: Optional[str] = Query(None, description="搜索姓名"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """教师列表（支持按角色/状态/姓名筛选）"""
    return await TeacherService.list_teachers(
        db=db, school_id=current_user.school_id,
        page=page, page_size=page_size,
        role=role, is_active=is_active, keyword=keyword,
    )


@router.post("/teachers", status_code=201, response_model=TeacherCreateOut)
async def create_teacher(
    body: TeacherCreate,
    current_user: User = Depends(require_role("ms_admin", "grade_leader")),
    db: AsyncSession = Depends(get_db),
):
    """
    创建教师 (一步到位: User+Teacher+Extension)

    需要 ms_admin 或 grade_leader 权限。
    """
    try:
        return await TeacherService.create_teacher(
            db=db, school_id=current_user.school_id, data=body,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═════════════════════════════════════════════════════════════════════════════════
# 教师详情
# ═════════════════════════════════════════════════════════════════════════════════

@router.get("/teachers/{user_id}", response_model=TeacherDetailOut)
async def get_teacher_detail(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """教师详情（含扩展信息、任教学科、班主任班级）"""
    detail = await TeacherService.get_teacher_detail(db, user_id)
    if not detail:
        raise HTTPException(status_code=404, detail="教师不存在")
    return detail


# ═════════════════════════════════════════════════════════════════════════════════
# 教师扩展信息 + 任教学科
# ═════════════════════════════════════════════════════════════════════════════════

@router.put("/teachers/{user_id}/extension", response_model=TeacherExtensionOut)
async def upsert_extension(
    user_id: int,
    body: TeacherExtensionCreate,
    current_user: User = Depends(require_role("ms_admin", "grade_leader")),
    db: AsyncSession = Depends(get_db),
):
    """更新教师扩展信息（职称/学历/资质/课时上限等）"""
    return await TeacherService.upsert_extension(
        db=db, user_id=user_id, data=body, school_id=current_user.school_id,
    )


@router.put("/teachers/{user_id}/subjects", response_model=SubjectAssignResponse)
async def assign_subjects(
    user_id: int,
    body: SubjectAssignRequest,
    current_user: User = Depends(require_role("ms_admin", "grade_leader")),
    db: AsyncSession = Depends(get_db),
):
    """分配教师任教学科（覆盖式更新）"""
    return await TeacherService.assign_subjects(
        db=db, user_id=user_id, subjects=body.subjects,
        school_id=current_user.school_id,
    )


# ═════════════════════════════════════════════════════════════════════════════════
# 工作量
# ═════════════════════════════════════════════════════════════════════════════════

@router.get("/teachers/{user_id}/workloads", response_model=list[WorkloadOut])
async def list_workloads(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询教师所有学期工作量"""
    return await TeacherService.list_workloads(
        db=db, user_id=user_id, school_id=current_user.school_id,
    )


@router.post("/teachers/{user_id}/workloads", status_code=201, response_model=WorkloadOut)
async def add_workload(
    user_id: int,
    body: WorkloadCreate,
    current_user: User = Depends(require_role("ms_admin", "grade_leader")),
    db: AsyncSession = Depends(get_db),
):
    """新增/更新教师工作量记录（按学期去重）"""
    return await TeacherService.add_workload(
        db=db, user_id=user_id, data=body, school_id=current_user.school_id,
    )


@router.get("/teachers/{user_id}/workload-stats", response_model=WorkloadStatsOut)
async def get_workload_stats(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """教师工作量统计汇总"""
    stats = await TeacherService.get_workload_stats(
        db=db, user_id=user_id, school_id=current_user.school_id,
    )
    if not stats:
        raise HTTPException(status_code=404, detail="教师或工作量记录不存在")
    return stats


# ═════════════════════════════════════════════════════════════════════════════════
# 角色分配 CRUD (双重角色解耦 overlay — BOSS 核心需求)
# ═════════════════════════════════════════════════════════════════════════════════

@router.post("/teachers/{user_id}/roles", status_code=201, response_model=TeacherRoleAssignmentOut)
async def assign_role(
    user_id: int,
    body: TeacherRoleAssignmentCreate,
    current_user: User = Depends(require_role("ms_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    分配角色 — 双重角色解耦 overlay

    示例: 给张老师分配"年级组长"角色(初一年级)
    POST /teachers/5/roles {role_type: "grade_leader", scope_type: "grade", scope_id: 1}

    需要 ms_admin 权限。
    """
    try:
        return await TeacherService.assign_role(
            db=db, school_id=current_user.school_id,
            user_id=user_id, data=body,
            assigned_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/teachers/{user_id}/roles", response_model=TeacherRoleAssignmentList)
async def list_roles(
    user_id: int,
    is_active: Optional[bool] = Query(None, description="筛选启用/停用"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询教师角色分配列表"""
    roles = await TeacherService.list_roles(
        db=db, school_id=current_user.school_id,
        user_id=user_id, is_active=is_active,
    )
    return TeacherRoleAssignmentList(assignments=roles, total=len(roles))


@router.patch("/teachers/roles/{assignment_id}", response_model=TeacherRoleAssignmentOut)
async def update_role(
    assignment_id: int,
    is_active: Optional[bool] = Body(None, embed=True, description="启用/停用"),
    expires_at: Optional[str] = Body(None, embed=True, description="过期时间"),
    notes: Optional[str] = Body(None, embed=True, description="备注"),
    current_user: User = Depends(require_role("ms_admin")),
    db: AsyncSession = Depends(get_db),
):
    """更新角色分配 (启用/停用/设过期)"""
    try:
        return await TeacherService.update_role(
            db=db, school_id=current_user.school_id,
            assignment_id=assignment_id,
            is_active=is_active, expires_at=expires_at, notes=notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/teachers/roles/{assignment_id}", status_code=204)
async def delete_role(
    assignment_id: int,
    current_user: User = Depends(require_role("ms_admin")),
    db: AsyncSession = Depends(get_db),
):
    """删除角色分配"""
    success = await TeacherService.delete_role(
        db=db, school_id=current_user.school_id,
        assignment_id=assignment_id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="角色分配不存在")


# ═════════════════════════════════════════════════════════════════════════════════
# 核心聚合: 有效角色集合 (排课+审批+大盘三切面)
# ═════════════════════════════════════════════════════════════════════════════════

@router.get("/teachers/{user_id}/effective-roles", response_model=EffectiveRolesOut)
async def get_effective_roles(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    教师有效角色集合 — BOSS 核心需求

    三个权限切面:
      - workload_profile:  排课引擎供给侧数据 (课时上限/当前负载/可用容量)
      - permission_scopes:  审批流权限切面 (能否审批违纪/请假/可见年级班级)
      - effective_roles:    大盘视角 (所有叠加角色)

    示例响应:
      张老师 = subject_teacher(2501班数学) + grade_leader(初一年级) + moral_admin(全校)
    """
    result = await TeacherService.resolve_effective_roles(
        db=db, school_id=current_user.school_id, user_id=user_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="教师不存在")
    return result
