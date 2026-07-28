"""
modules/student_registry/routers.py — 学籍管理 API 路由

遵循 WINGS 3.0 路由规范：
- APIRouter(tags=["student-registry"])
- Depends(get_db) + Depends(get_current_user) + Depends(require_role(...))
- ValueError -> 400, 其他异常向上抛
"""

import logging

from core.access import get_student_or_403
from core.models import User, UserRole
from core.routers import get_current_user, get_db, require_role, verify_school_access
from fastapi import APIRouter, Depends, HTTPException, Query
from modules.student_registry.rollover import RolloverEngine, RolloverError
from modules.student_registry.schemas import (
    BatchImportResult,
    PaginatedStudents,
    RegistryStatsOut,
    RolloverRequest,
    RolloverResult,
    StatusChangeCreate,
    StatusChangeOut,
    StudentCreate,
    StudentOut,
    StudentUpdate,
)
from modules.student_registry.services import StudentRegistryService
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(tags=["student-registry"])

# 允许操作的角色
REGISTRY_ROLES = (
    UserRole.MS_ADMIN,
    UserRole.GRADE_LEADER,
    UserRole.CLASS_TEACHER,
)


# ═══════════════════════════════════════════════════════════════
# CRUD
# ═══════════════════════════════════════════════════════════════


@router.post("/students", response_model=StudentOut, status_code=201)
async def create_student(
    body: StudentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*REGISTRY_ROLES)),
):
    """创建学籍"""
    try:
        student = await StudentRegistryService.create_student(
            db, current_user.school_id, body, current_user.id
        )
        result = await StudentRegistryService.get_student(db, student.id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/students", response_model=PaginatedStudents)
async def list_students(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    class_id: int | None = None,
    grade_id: int | None = None,
    status: str | None = None,
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """学籍列表（分页/筛选/搜索）"""
    items, total = await StudentRegistryService.list_students(
        db,
        current_user.school_id,
        page,
        page_size,
        class_id,
        grade_id,
        status,
        keyword,
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/students/{student_id}", response_model=StudentOut)
async def get_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    学籍详情（含 PII：身份证/住址/父母电话）

    2026-07-24 整改：原实现只有 verify_school_access（学校级），
    本校任意账号顺序枚举 id 即可逐条拖走全部学籍 PII。
    改为行级归属校验：越权请求在触碰 PII 之前即被拦截（404/403）。
    """
    # 归属校验放在取数之前 —— 越权请求不触碰 PII 数据
    await get_student_or_403(db, current_user, student_id)

    result = await StudentRegistryService.get_student(db, student_id)
    if not result:
        raise HTTPException(status_code=404, detail="学生不存在")
    # 纵深防御：保留学校级校验（归属校验已含此层，双重保险）
    verify_school_access(result["school_id"], current_user)
    return result


@router.put("/students/{student_id}", response_model=StudentOut)
async def update_student(
    student_id: int,
    body: StudentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*REGISTRY_ROLES)),
):
    """更新学籍信息"""
    try:
        student = await StudentRegistryService.update_student(db, student_id, body)
        result = await StudentRegistryService.get_student(db, student.id)
        if result:
            verify_school_access(result["school_id"], current_user)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 状态变更（状态机）
# ═══════════════════════════════════════════════════════════════


@router.post("/students/{student_id}/transfer", response_model=StatusChangeOut)
async def transfer_student(
    student_id: int,
    body: StatusChangeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    """转学办理"""
    try:
        change = await StudentRegistryService.change_status(
            db,
            current_user.school_id,
            student_id,
            StatusChangeCreate(
                change_type="transfer",
                reason=body.reason,
                target_school=body.target_school,
                remark=body.remark,
            ),
            current_user.id,
            current_user.display_name,
        )
        return change
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/students/{student_id}/suspend", response_model=StatusChangeOut)
async def suspend_student(
    student_id: int,
    body: StatusChangeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    """休学办理"""
    try:
        change = await StudentRegistryService.change_status(
            db,
            current_user.school_id,
            student_id,
            StatusChangeCreate(
                change_type="suspend",
                reason=body.reason,
                expected_resume_date=body.expected_resume_date,
                remark=body.remark,
            ),
            current_user.id,
            current_user.display_name,
        )
        return change
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/students/{student_id}/resume", response_model=StatusChangeOut)
async def resume_student(
    student_id: int,
    body: StatusChangeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    """复学办理"""
    try:
        change = await StudentRegistryService.change_status(
            db,
            current_user.school_id,
            student_id,
            StatusChangeCreate(
                change_type="resume",
                reason=body.reason or "休学期满复学",
                remark=body.remark,
            ),
            current_user.id,
            current_user.display_name,
        )
        return change
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/students/{student_id}/graduate", response_model=StatusChangeOut)
async def graduate_student(
    student_id: int,
    body: StatusChangeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """毕业处理"""
    try:
        change = await StudentRegistryService.change_status(
            db,
            current_user.school_id,
            student_id,
            StatusChangeCreate(
                change_type="graduate",
                reason=body.reason or "顺利毕业",
                target_school=body.target_school,
                remark=body.remark,
            ),
            current_user.id,
            current_user.display_name,
        )
        return change
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/students/{student_id}/status-history", response_model=list[StatusChangeOut])
async def get_status_history(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """学籍状态变更历史"""
    history = await StudentRegistryService.get_status_history(db, student_id)
    return history


# ═══════════════════════════════════════════════════════════════
# 批量导入
# ═══════════════════════════════════════════════════════════════


@router.post("/students/batch-import", response_model=BatchImportResult)
async def batch_import(
    students_data: list[dict],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    """
    批量导入学籍。
    前端解析 Excel/CSV 后，将数据以 JSON 数组传入。
    每条记录需包含: name, class_id, grade_id。其他字段可选。
    """
    result = await StudentRegistryService.batch_import(
        db, current_user.school_id, students_data, current_user.id
    )
    return result


# ═══════════════════════════════════════════════════════════════
# 统计
# ═══════════════════════════════════════════════════════════════


@router.get("/stats", response_model=RegistryStatsOut)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """学籍统计（在校/休学/转出等 + 同步来源分布）"""
    stats = await StudentRegistryService.get_stats(db, current_user.school_id)
    return stats


# ═══════════════════════════════════════════════════════════════
# 新学年滚动晋升（仅 ms_admin）
# ═══════════════════════════════════════════════════════════════


@router.post("/rollover", response_model=RolloverResult)
async def rollover(
    body: RolloverRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """
    新学年滚动晋升 — 毕业出档 + 年级晋升 + 新生导入（可选）。

    - 仅 ms_admin 可调用。
    - 单事务原子操作；异常自动回滚，成功自动提交。
    - 幂等：rollover_lock(school_id, school_year) 唯一约束拦截重复/并发。
    - dry_run=True 仅做预检与计数，不写入任何数据。
    """
    try:
        result = await RolloverEngine.run(
            db,
            current_user.school_id,
            current_user,
            school_year=body.school_year,
            dry_run=body.dry_run,
            freshmen=body.freshmen,
            note=body.note,
        )
        return result
    except RolloverError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
