"""
modules/tasks/routers.py — Task Center Foundation V1 API

权限模型（复用 scope verification + ResponsibleOwnerResolver）：
  - 创建：ms_admin 全校 / grade_leader 本年级 / class_teacher 本班（Resolver 内部校验，越权 403）
  - 查看：创建者 / 负责人 / 本人管理 scope 内
  - 处理（accept/start/complete/reject/evidence）：仅负责人（ms_admin 全校）
  - cancel：创建者 / 负责人 / 管理员
  - reassign：创建者 / 管理员（V1 保守：负责人不可自我甩锅）
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User, UserRole
from core.routers import get_current_user, get_db, require_role
from .schemas import (
    CommentCreate,
    EvidenceCreate,
    TaskActionOut,
    TaskCreate,
    TaskListOut,
    TaskOut,
    TaskReassign,
)
from .services import TaskService

router = APIRouter(tags=["tasks"])  # prefix 由 module_loader 按 manifest 挂载（/api/v1/tasks）

STAFF_ROLES = (
    UserRole.MS_ADMIN,
    UserRole.GRADE_LEADER,
    UserRole.CLASS_TEACHER,
    UserRole.TEACHER,
)


def _task_out(t: object) -> TaskOut:
    """ORM Task → TaskOut（含责任快照/事件/证据/评论）"""
    return TaskOut(
        id=t.id,
        school_id=t.school_id,
        task_type=t.task_type,
        title=t.title,
        description=t.description,
        status=t.status,
        priority=t.priority,
        due_at=t.due_at,
        owner_user_id=t.owner_user_id,
        owner_name_snapshot=t.owner_name_snapshot,
        responsibility_role=t.responsibility_role,
        responsibility_scope_type=t.responsibility_scope_type,
        responsibility_scope_id=t.responsibility_scope_id,
        resolution_source=t.resolution_source,
        resolution_confidence=t.resolution_confidence,
        resolved_at=t.resolved_at,
        assignment_id=t.assignment_id,
        unresolved_reason=t.unresolved_reason,
        closure_status=t.closure_status,
        closed_at=t.closed_at,
        created_by=t.created_by,
        created_at=t.created_at,
        updated_at=t.updated_at,
        assignments=[_assignment_out(a) for a in (t.assignments or [])],
        events=[_event_out(e) for e in (t.events or [])],
        evidence=[_evidence_out(e) for e in (t.evidence or [])],
        comments=[_comment_out(c) for c in (t.comments or [])],
    )


def _assignment_out(a) -> dict:
    return {
        "id": a.id, "assignment_id": a.assignment_id,
        "owner_user_id": a.owner_user_id, "owner_name_snapshot": a.owner_name_snapshot,
        "responsibility_role": a.responsibility_role,
        "responsibility_scope_type": a.responsibility_scope_type,
        "responsibility_scope_id": a.responsibility_scope_id,
        "resolution_source": a.resolution_source, "resolution_confidence": a.resolution_confidence,
        "resolved_at": a.resolved_at, "reassigned_from_user_id": a.reassigned_from_user_id,
        "assigned_by": a.assigned_by, "assigned_at": a.assigned_at, "is_current": a.is_current,
    }


def _event_out(e) -> dict:
    return {
        "id": e.id, "event_type": e.event_type,
        "actor_user_id": e.actor_user_id, "actor_name": e.actor_name,
        "detail": TaskService._json_loads(e.detail), "created_at": e.created_at,
    }


def _evidence_out(e) -> dict:
    return {
        "id": e.id, "kind": e.kind, "content": e.content,
        "file_path": e.file_path, "file_name": e.file_name,
        "created_by": e.created_by, "created_at": e.created_at,
    }


def _comment_out(c) -> dict:
    return {
        "id": c.id, "content": c.content, "created_by": c.created_by, "created_at": c.created_at,
    }


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(
    body: TaskCreate,
    current_user: User = Depends(require_role(*STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """人工创建任务（V1：年级组长 → 班主任跟进）。责任由 Resolver 解析，禁止猜人。"""
    task = await TaskService.create(db, current_user, body)
    return _task_out(task)


@router.get("", response_model=TaskListOut)
async def list_tasks(
    status: str | None = Query(None, description="OPEN/ACCEPTED/IN_PROGRESS/DONE/REJECTED/CANCELLED"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """任务列表（创建者/负责人/管理 scope 内可见）"""
    result = await TaskService.list_tasks(db, current_user, status=status, limit=limit, offset=offset)
    return TaskListOut(
        total=result["total"],
        items=[_task_out(t) for t in result["items"]],
    )


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await TaskService.get_task(db, current_user, task_id)
    return _task_out(task)


@router.post("/{task_id}/accept", response_model=TaskActionOut)
async def accept_task(task_id: int, current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    t = await TaskService.accept(db, current_user, task_id)
    return TaskActionOut(id=t.id, status=t.status, message="已接受")


@router.post("/{task_id}/start", response_model=TaskActionOut)
async def start_task(task_id: int, current_user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    t = await TaskService.start(db, current_user, task_id)
    return TaskActionOut(id=t.id, status=t.status, message="已开始处理")


@router.post("/{task_id}/complete", response_model=TaskActionOut)
async def complete_task(task_id: int, note: str | None = Query(None, max_length=500),
                        current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    t = await TaskService.complete(db, current_user, task_id, note=note)
    return TaskActionOut(id=t.id, status=t.status,
                         message="已完成（closure_status=pending，待复核）")


@router.post("/{task_id}/reject", response_model=TaskActionOut)
async def reject_task(task_id: int, note: str | None = Query(None, max_length=500),
                      current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    t = await TaskService.reject(db, current_user, task_id, note=note)
    return TaskActionOut(id=t.id, status=t.status, message="已驳回")


@router.post("/{task_id}/cancel", response_model=TaskActionOut)
async def cancel_task(task_id: int, note: str | None = Query(None, max_length=500),
                      current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    t = await TaskService.cancel(db, current_user, task_id, note=note)
    return TaskActionOut(id=t.id, status=t.status, message="已取消")


@router.post("/{task_id}/reassign", response_model=TaskOut)
async def reassign_task(task_id: int, body: TaskReassign,
                        current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    t = await TaskService.reassign(db, current_user, task_id, body.new_owner_user_id, reason=body.reason)
    return _task_out(t)


@router.post("/{task_id}/evidence", response_model=TaskOut)
async def add_evidence(task_id: int, body: EvidenceCreate,
                       current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    t = await TaskService.add_evidence(db, current_user, task_id, body)
    return _task_out(t)


@router.post("/{task_id}/comments", response_model=TaskOut)
async def add_comment(task_id: int, body: CommentCreate,
                      current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    t = await TaskService.add_comment(db, current_user, task_id, body)
    return _task_out(t)
