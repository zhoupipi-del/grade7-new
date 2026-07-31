"""
homework_mgmt/routers.py — 作业管理 API 端点

端点清单 (12端点):
  作业: GET/ POST/ GET/{id} PUT/{id} DELETE/{id} POST/{id}/close
  提交: GET/{id}/submissions POST/{id}/submit GET/{id}/submission/{student_id}
  批改: POST/submissions/{sub_id}/grade
  看板: GET/dashboard GET/my-homework
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime

from core.routers import get_db, get_current_user, require_role
from core.models import User, UserRole

from .schemas import (
    AssignmentCreate, AssignmentUpdate, AssignmentResponse,
    SubmissionCreate, SubmissionResponse,
    GradingCreate, GradingResponse,
    DashboardResponse,
)
from . import services as svc

MGMT_ROLES = [UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER]

router = APIRouter(tags=["作业管理"])


# ──────────────────────────────────────────────
# 作业 CRUD
# ──────────────────────────────────────────────

@router.get("/")
async def list_assignments(
    class_id: Optional[int] = Query(None),
    subject_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """列出作业"""
    teacher_id = None
    # 班主任看本班所有作业（多学科），年级组长/管理员看全部
    if user.role.upper() == "CLASS_TEACHER":
        class_id = user.class_id  # 强制覆盖为本班

    items, total = await svc.list_assignments(
        db, user.school_id,
        teacher_id=teacher_id,
        class_id=class_id,
        subject_id=subject_id,
        status=status,
        page=page, page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/", status_code=201, dependencies=[Depends(require_role(*MGMT_ROLES))])
async def create_assignment(
    data: AssignmentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建作业"""
    assignment = await svc.create_assignment(db, user.school_id, user.id, data)
    return await svc._enrich_assignment(db, assignment)


@router.get("/dashboard")
async def get_dashboard(
    class_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """作业管理看板"""
    teacher_id = None
    if user.role.upper() == "CLASS_TEACHER":
        class_id = user.class_id  # 班主任看本班看板
    return await svc.get_dashboard(db, user.school_id, teacher_id=teacher_id, class_id=class_id)


@router.get("/my-homework")
async def get_my_homework(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """学生/家长查看自己的作业列表"""
    # 通过 bound_student_id 获取学生ID
    student_id = user.bound_student_id
    if not student_id:
        raise HTTPException(403, "未绑定学生，无法查看作业")

    items, total = await svc.list_assignments(
        db, user.school_id,
        page=1, page_size=100,
    )

    # 补充学生的提交状态
    result = []
    for a in items:
        submission = await svc.get_student_submission(
            db, user.school_id, a["id"], student_id,
        )
        a["my_submission"] = submission
        result.append(a)

    return {"items": result, "total": total}


@router.get("/{assignment_id}")
async def get_assignment(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取作业详情"""
    assignment = await svc.get_assignment(db, user.school_id, assignment_id)
    if not assignment:
        raise HTTPException(404, "作业不存在")
    stats = await svc._get_assignment_submission_stats(db, user.school_id, assignment_id)
    return await svc._enrich_assignment(db, assignment, stats)


@router.put("/{assignment_id}", dependencies=[Depends(require_role(*MGMT_ROLES))])
async def update_assignment(
    assignment_id: int,
    data: AssignmentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新作业"""
    assignment = await svc.update_assignment(db, user.school_id, assignment_id, data)
    if not assignment:
        raise HTTPException(404, "作业不存在")
    return await svc._enrich_assignment(db, assignment)


@router.post("/{assignment_id}/close", dependencies=[Depends(require_role(*MGMT_ROLES))])
async def close_assignment(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """关闭作业 — 未提交标记为missing"""
    assignment = await svc.close_assignment(db, user.school_id, assignment_id)
    if not assignment:
        raise HTTPException(404, "作业不存在")
    return await svc._enrich_assignment(db, assignment)


# ──────────────────────────────────────────────
# 学生提交
# ──────────────────────────────────────────────

@router.get("/{assignment_id}/submissions", dependencies=[Depends(require_role(*MGMT_ROLES))])
async def list_submissions(
    assignment_id: int,
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """列出作业的所有提交"""
    items, total = await svc.list_submissions(
        db, user.school_id, assignment_id, status=status,
    )
    return {"items": items, "total": total}


@router.post("/{assignment_id}/submit", status_code=201)
async def submit_homework(
    assignment_id: int,
    data: SubmissionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """学生/家长提交作业"""
    student_id = user.bound_student_id
    if not student_id:
        raise HTTPException(403, "未绑定学生，无法提交作业")

    submission = await svc.submit_homework(
        db, user.school_id, assignment_id, student_id, data,
    )
    if not submission:
        raise HTTPException(404, "作业不存在")
    return submission


@router.get("/{assignment_id}/submission/{student_id}", dependencies=[Depends(require_role(*MGMT_ROLES))])
async def get_student_submission(
    assignment_id: int,
    student_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取学生在某作业的提交详情"""
    result = await svc.get_student_submission(
        db, user.school_id, assignment_id, student_id,
    )
    if not result:
        raise HTTPException(404, "提交记录不存在")
    return result


# ──────────────────────────────────────────────
# 教师批改
# ──────────────────────────────────────────────

@router.post("/submissions/{submission_id}/grade", status_code=201, dependencies=[Depends(require_role(*MGMT_ROLES))])
async def grade_submission(
    submission_id: int,
    data: GradingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """教师批改提交 — 含错题标记，自动同步到error_funnel"""
    result = await svc.grade_submission(
        db, user.school_id, submission_id, user.id, data,
    )
    if not result:
        raise HTTPException(404, "提交记录不存在")
    return result
