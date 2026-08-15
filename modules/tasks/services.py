"""
modules/tasks/services.py — Task Center Foundation V1 服务层

核心职责：
  1. create 时经 ResponsibleOwnerResolver 解析责任（禁止猜人）。
     resolved → 责任快照（含真实 assignment_id）+ source 关联写入 tasks + task_assignments(is_current=True)
     no_assignment / conflict / invalid_request → 拒绝建任务（422，前端显示"未配置责任人，无法创建"）
     no_access → 403（创建者越权）
  2. 状态机（4 态）：pending → in_progress → completed；cancelled 分支。
     start：pending→in_progress，写 started_at；complete：in_progress→completed，写 completed_at+result。
  3. reassign：追加分派历史（is_current 翻转），历史任务保留原责任人。
  4. complete：status=completed 且 closure_status='pending'（completed ≠ verified）。
  5. 权限：ms_admin 全校 / grade_leader 本年级 / class_teacher 本班；owner 才能处理。
"""

import json
import logging
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User
from core.resolver import resolve_owner
from .models import (
    CLOSURE_PENDING,
    EV_CANCELLED,
    EV_COMMENT_ADDED,
    EV_COMPLETED,
    EV_CREATED,
    EV_EVIDENCE_ADDED,
    EV_REASSIGNED,
    EV_STARTED,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_PENDING,
    TASK_STATUS_TERMINAL,
    Task,
    TaskAssignment,
    TaskComment,
    TaskEvent,
    TaskEvidence,
)

logger = logging.getLogger(__name__)


def _json_dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _json_loads(raw) -> dict:
    if not raw:
        return {}
    try:
        if isinstance(raw, dict):
            return raw
        return json.loads(raw)
    except Exception:  # noqa: BLE001 — JSON 快照防御：形态分裂时返回空
        return {}


def _role(user: User) -> str:
    return (user.role.value if hasattr(user.role, "value") else str(user.role)).lower()


class TaskService:
    # ─────────────────────────────────────────────────────
    # 创建（Resolver 驱动，禁止猜人）
    # ─────────────────────────────────────────────────────
    @staticmethod
    async def create(db: AsyncSession, user: User, data) -> Task:
        school_id = user.school_id

        # 1) 责任解析（内部自带越权校验：no_access → 403）
        resolution = await resolve_owner(
            db, user,
            student_id=data.student_id,
            grade_id=data.grade_id,
            subject=data.subject,
        )
        if resolution.get("unresolved_reason") == "no_access":
            raise HTTPException(status_code=403, detail=resolution.get("reason_detail", "无权创建该范围任务"))

        # 2) 未解析（no_assignment / conflict / invalid_request）→ 拒绝建任务（禁智能兜底）
        if not resolution.get("resolved"):
            reason = resolution.get("unresolved_reason") or "unresolved"
            raise HTTPException(
                status_code=422,
                detail=f"无法创建任务：当前未配置责任人（{reason}），请先到「组织与责任配置」页配置后再创建。",
            )

        # 3) 来源关联派生（student → class → grade）
        source_type = getattr(data, "source_type", None)
        source_id = getattr(data, "source_id", None)
        student_id = data.student_id
        class_id = data.class_id if getattr(data, "class_id", None) else None
        grade_id = data.grade_id
        if student_id is not None and (class_id is None or grade_id is None):
            from core.models import Class as _Class, Student as _Student
            cls_id = await db.scalar(
                select(_Student.class_id).where(_Student.id == student_id, _Student.school_id == school_id)
            )
            if cls_id is not None:
                class_id = cls_id
                if grade_id is None:
                    grade_id = await db.scalar(
                        select(_Class.grade_id).where(_Class.id == cls_id, _Class.school_id == school_id)
                    )

        # 4) 写任务主表（责任快照 + 真实 assignment_id + 来源关联）
        now = datetime.now()
        task = Task(
            school_id=school_id,
            task_type="manual",
            title=data.title,
            description=data.description,
            status=TASK_STATUS_PENDING,
            priority=data.priority,
            due_at=data.due_at,
            owner_user_id=resolution.get("owner_user_id"),
            owner_name_snapshot=resolution.get("owner_name"),
            responsibility_role=resolution.get("role_type"),
            responsibility_scope_type=resolution.get("scope_type"),
            responsibility_scope_id=resolution.get("scope_id"),
            resolution_source=resolution.get("source"),
            resolution_confidence=resolution.get("confidence"),
            resolved_at=now,
            assignment_id=resolution.get("assignment_id"),
            unresolved_reason=None,
            source_type=source_type,
            source_id=source_id,
            student_id=student_id,
            class_id=class_id,
            grade_id=grade_id,
            created_by=user.id,
        )
        db.add(task)
        await db.flush()

        # 5) 分派历史（is_current=True，保留真实 assignment_id 证据）
        db.add(TaskAssignment(
            task_id=task.id,
            assignment_id=resolution.get("assignment_id"),
            owner_user_id=resolution.get("owner_user_id"),
            owner_name_snapshot=resolution.get("owner_name"),
            responsibility_role=resolution.get("role_type"),
            responsibility_scope_type=resolution.get("scope_type"),
            responsibility_scope_id=resolution.get("scope_id"),
            resolution_source=resolution.get("source"),
            resolution_confidence=resolution.get("confidence"),
            resolved_at=now,
            assigned_by=user.id,
            is_current=True,
        ))

        # 6) 事件流
        db.add(TaskEvent(
            task_id=task.id,
            event_type=EV_CREATED,
            actor_user_id=user.id,
            actor_name=getattr(user, "real_name", None) or user.username,
            detail=_json_dumps({
                "title": data.title,
                "resolution": resolution,
                "resolved": True,
                "assignment_id": resolution.get("assignment_id"),
            }),
        ))
        await db.commit()

        # 重载（commit 后关系过期）
        from sqlalchemy.orm import selectinload
        stmt = (
            select(Task)
            .options(
                selectinload(Task.assignments),
                selectinload(Task.events),
                selectinload(Task.evidence),
                selectinload(Task.comments),
            )
            .where(Task.id == task.id)
        )
        return (await db.execute(stmt)).scalar_one()

    # ─────────────────────────────────────────────────────
    # 查询（权限过滤）
    # ─────────────────────────────────────────────────────
    @staticmethod
    def _visible_filter(user: User, school_id: int):
        """返回可见条件（and_ 片段）。V1：创建者 / 负责人 / 本人管理 scope 内"""
        from sqlalchemy import or_

        role = _role(user)
        conds = [
            Task.school_id == school_id,
            or_(
                Task.created_by == user.id,
                Task.owner_user_id == user.id,
            ),
        ]
        if role == "ms_admin":
            return Task.school_id == school_id  # 全校
        if role == "grade_leader":
            grade_ids = {int(user.grade_id)} if user.grade_id else set()
            from sqlalchemy import and_
            conds = [Task.school_id == school_id, or_(
                Task.created_by == user.id,
                Task.owner_user_id == user.id,
                and_(
                    Task.responsibility_scope_type == "grade",
                    Task.responsibility_scope_id.in_(
                        list(grade_ids) if grade_ids else [-1]
                    ),
                ),
            )]
        if role == "class_teacher":
            from sqlalchemy import and_
            conds = [Task.school_id == school_id, or_(
                Task.created_by == user.id,
                Task.owner_user_id == user.id,
                and_(
                    Task.responsibility_scope_type == "class",
                    Task.responsibility_scope_id == (int(user.class_id) if user.class_id else -1),
                ),
            )]
        return conds

    @staticmethod
    async def list_tasks(db: AsyncSession, user: User, status: str | None = None,
                         limit: int = 50, offset: int = 0) -> dict:
        from sqlalchemy import select as _select

        conds = TaskService._visible_filter(user, user.school_id)
        if status:
            conds = list(conds) + [Task.status == status.lower()]
        stmt = (
            _select(Task)
            .where(*conds)
            .order_by(Task.created_at.desc())
            .limit(min(limit, 200))
            .offset(offset)
        )
        result = await db.execute(stmt)
        items = list(result.scalars().all())
        return {"total": len(items), "items": items}

    @staticmethod
    async def get_task(db: AsyncSession, user: User, task_id: int) -> Task:
        from sqlalchemy import and_
        from sqlalchemy.orm import selectinload

        stmt = (
            select(Task)
            .options(
                selectinload(Task.assignments),
                selectinload(Task.events),
                selectinload(Task.evidence),
                selectinload(Task.comments),
            )
            .where(Task.id == task_id, Task.school_id == user.school_id)
        )
        task = (await db.execute(stmt)).scalar_one_or_none()
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在或无权访问")
        if not TaskService._can_view(db, user, task):
            raise HTTPException(status_code=403, detail="无权访问该任务")
        return task

    @staticmethod
    def _can_view(db: AsyncSession, user: User, task: Task) -> bool:
        role = _role(user)
        if role == "ms_admin":
            return task.school_id == user.school_id
        if user.id == task.created_by or user.id == task.owner_user_id:
            return True
        # scope 匹配
        if role == "grade_leader" and task.responsibility_scope_type == "grade":
            grade_ids = {int(user.grade_id)} if user.grade_id else set()
            return task.responsibility_scope_id in grade_ids
        if role == "class_teacher" and task.responsibility_scope_type == "class":
            return task.responsibility_scope_id == (int(user.class_id) if user.class_id else None)
        return False

    @staticmethod
    def _can_act(db: AsyncSession, user: User, task: Task) -> bool:
        """处理操作：仅负责人本人（ms_admin 全校）"""
        role = _role(user)
        if role == "ms_admin":
            return True
        return user.id == task.owner_user_id

    # ─────────────────────────────────────────────────────
    # 状态机操作
    # ─────────────────────────────────────────────────────
    @staticmethod
    async def _transition(db: AsyncSession, user: User, task_id: int,
                          target: str, ev: str, note: str | None = None,
                          require_act: bool = True) -> Task:
        task = await TaskService.get_task(db, user, task_id)
        if require_act and not TaskService._can_act(db, user, task):
            raise HTTPException(status_code=403, detail="仅任务负责人可执行该操作")
        if task.status in TASK_STATUS_TERMINAL:
            raise HTTPException(status_code=400, detail=f"任务已终止（{task.status}），不可再流转")
        old_status = task.status
        task.status = target
        if target == TASK_STATUS_COMPLETED:
            task.closure_status = CLOSURE_PENDING  # completed ≠ verified
            task.closed_at = datetime.now()
        db.add(TaskEvent(
            task_id=task.id,
            event_type=ev,
            actor_user_id=user.id,
            actor_name=getattr(user, "real_name", None) or user.username,
            detail=_json_dumps({"note": note, "from_status": old_status, "to_status": target}),
        ))
        await db.commit()
        db.expire(task)  # identity map 里 selectinload 关系已加载不重查 -> 强制过期重载
        return await TaskService.get_task(db, user, task_id)

    @staticmethod
    async def start(db: AsyncSession, user: User, task_id: int) -> Task:
        """pending → in_progress（仅负责人；写 started_at）"""
        task = await TaskService.get_task(db, user, task_id)
        if not TaskService._can_act(db, user, task):
            raise HTTPException(status_code=403, detail="仅任务负责人可执行该操作")
        if task.status != TASK_STATUS_PENDING:
            raise HTTPException(status_code=400, detail=f"任务当前状态 {task.status}，仅 pending 可开始处理")
        old_status = task.status
        task.status = TASK_STATUS_IN_PROGRESS
        task.started_at = datetime.now()
        db.add(TaskEvent(
            task_id=task.id,
            event_type=EV_STARTED,
            actor_user_id=user.id,
            actor_name=getattr(user, "real_name", None) or user.username,
            detail=_json_dumps({"from_status": old_status, "to_status": TASK_STATUS_IN_PROGRESS}),
        ))
        await db.commit()
        db.expire(task)
        return await TaskService.get_task(db, user, task_id)

    @staticmethod
    async def complete(db: AsyncSession, user: User, task_id: int, note: str | None = None) -> Task:
        """in_progress → completed（仅负责人；写 completed_at + result + closure_status=pending）"""
        task = await TaskService.get_task(db, user, task_id)
        if not TaskService._can_act(db, user, task):
            raise HTTPException(status_code=403, detail="仅任务负责人可执行该操作")
        if task.status != TASK_STATUS_IN_PROGRESS:
            raise HTTPException(status_code=400, detail=f"任务当前状态 {task.status}，仅 in_progress 可完成")
        old_status = task.status
        task.status = TASK_STATUS_COMPLETED
        task.completed_at = datetime.now()
        task.result = note
        task.closure_status = CLOSURE_PENDING  # completed ≠ verified
        task.closed_at = task.completed_at
        db.add(TaskEvent(
            task_id=task.id,
            event_type=EV_COMPLETED,
            actor_user_id=user.id,
            actor_name=getattr(user, "real_name", None) or user.username,
            detail=_json_dumps({"note": note, "from_status": old_status, "to_status": TASK_STATUS_COMPLETED}),
        ))
        await db.commit()
        db.expire(task)
        return await TaskService.get_task(db, user, task_id)

    @staticmethod
    async def cancel(db: AsyncSession, user: User, task_id: int, note: str | None = None) -> Task:
        """创建者 / 负责人 / 管理员可取消"""
        task = await TaskService.get_task(db, user, task_id)
        role = _role(user)
        if not (role == "ms_admin" or user.id == task.created_by or user.id == task.owner_user_id):
            raise HTTPException(status_code=403, detail="仅创建者/负责人/管理员可取消")
        return await TaskService._transition(db, user, task_id, TASK_STATUS_CANCELLED, EV_CANCELLED, note, require_act=False)

    # ─────────────────────────────────────────────────────
    # 转交（规则 3：追加历史，保留原责任人）
    # ─────────────────────────────────────────────────────
    @staticmethod
    async def reassign(db: AsyncSession, user: User, task_id: int, new_owner_user_id: int,
                       reason: str | None = None) -> Task:
        task = await TaskService.get_task(db, user, task_id)
        role = _role(user)
        if not (role == "ms_admin" or user.id == task.created_by):
            raise HTTPException(status_code=403, detail="仅创建者/管理员可转交")
        if task.status in TASK_STATUS_TERMINAL:
            raise HTTPException(status_code=400, detail="任务已终止，不可转交")

        # 校验新负责人：同校且存在
        new_owner = (await db.execute(
            select(User).where(User.id == new_owner_user_id)
        )).scalar_one_or_none()
        if new_owner is None or new_owner.school_id != user.school_id:
            raise HTTPException(status_code=400, detail="新负责人不存在或不在本校")

        old_owner_id = task.owner_user_id
        # 旧分派置非当前
        old_rows = (await db.execute(
            select(TaskAssignment).where(TaskAssignment.task_id == task.id, TaskAssignment.is_current.is_(True))
        )).scalars().all()
        for r in old_rows:
            r.is_current = False

        # 新分派（继承原责任快照的角色/scope，仅换人）
        db.add(TaskAssignment(
            task_id=task.id,
            assignment_id=task.assignment_id,
            owner_user_id=new_owner.id,
            owner_name_snapshot=getattr(new_owner, "real_name", None) or new_owner.username,
            responsibility_role=task.responsibility_role,
            responsibility_scope_type=task.responsibility_scope_type,
            responsibility_scope_id=task.responsibility_scope_id,
            resolution_source=f"{task.resolution_source or 'manual'}+reassign",
            resolution_confidence=task.resolution_confidence or "medium",
            resolved_at=datetime.now(),
            reassigned_from_user_id=old_owner_id,
            assigned_by=user.id,
            is_current=True,
        ))
        # 主表快照更新（保留原 responsibility 语义，仅换 owner）
        task.owner_user_id = new_owner.id
        task.owner_name_snapshot = getattr(new_owner, "real_name", None) or new_owner.username
        db.add(TaskEvent(
            task_id=task.id,
            event_type=EV_REASSIGNED,
            actor_user_id=user.id,
            actor_name=getattr(user, "real_name", None) or user.username,
            detail=_json_dumps({
                "from_user_id": old_owner_id,
                "to_user_id": new_owner.id,
                "reason": reason,
            }),
        ))
        await db.commit()
        db.expire(task)
        return await TaskService.get_task(db, user, task_id)

    # ─────────────────────────────────────────────────────
    # 证据 / 评论
    # ─────────────────────────────────────────────────────
    @staticmethod
    async def add_evidence(db: AsyncSession, user: User, task_id: int, body) -> Task:
        task = await TaskService.get_task(db, user, task_id)
        if not TaskService._can_act(db, user, task):
            raise HTTPException(status_code=403, detail="仅负责人可提交证据")
        db.add(TaskEvidence(
            task_id=task.id,
            kind=body.kind,
            content=body.content,
            file_path=body.file_path,
            file_name=body.file_name,
            created_by=user.id,
        ))
        db.add(TaskEvent(
            task_id=task.id,
            event_type=EV_EVIDENCE_ADDED,
            actor_user_id=user.id,
            actor_name=getattr(user, "real_name", None) or user.username,
            detail=_json_dumps({"kind": body.kind}),
        ))
        await db.commit()
        db.expire(task)
        return await TaskService.get_task(db, user, task_id)

    @staticmethod
    async def add_comment(db: AsyncSession, user: User, task_id: int, body) -> Task:
        task = await TaskService.get_task(db, user, task_id)
        db.add(TaskComment(
            task_id=task.id,
            content=body.content,
            created_by=user.id,
        ))
        db.add(TaskEvent(
            task_id=task.id,
            event_type=EV_COMMENT_ADDED,
            actor_user_id=user.id,
            actor_name=getattr(user, "real_name", None) or user.username,
            detail=_json_dumps({"content_len": len(body.content)}),
        ))
        await db.commit()
        db.expire(task)
        return await TaskService.get_task(db, user, task_id)
