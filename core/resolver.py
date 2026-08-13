"""
core/resolver.py — ResponsibleOwnerResolver V1（责任归属解析）

周主任拍板（2026-08-13）：Resolver 解决的是"这件事究竟应该由谁负责"，
把 WINGS 从"按角色看数据"推到"按责任驱动动作"。

铁律（三条纪律）：
  1. Assignment 是唯一责任事实源——绝不从 teacher.class_id / 历史字段 /
     姓名匹配 / 角色猜测责任人；没有 Assignment 就返回 unresolved。
  2. Resolver 只解析责任，不制造任务——输出 owner/scope/source/confidence/
     unresolved_reason；Task Center 才负责生成/分派/状态流转。
  3. 越权用户不能借 Resolver 枚举其他年级/班级责任人——解析前先验 scope。

解析能力（V1）：
  student_id            → homeroom_teacher@class（该生班级的班主任）
  student_id + subject  → 任课教师（teacher_subjects 学科+班级粒度优先，
                          assignment subject_teacher@class 兜底）
  grade_id              → grade_leader@grade（年级组长）

输出约定：
  resolved: true/false
  owner/owner_name/owner_role   （resolved=true 时）
  role_type/scope_type/scope_id （责任岗位）
  source: assignment_* | teacher_subjects | unresolved
  confidence: high/medium/low
  unresolved_reason             （resolved=false 时: no_assignment / conflict / no_access）
  conflict: [owner 列表]        （同一 Assignment 多条 → 显式冲突）
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select

logger = logging.getLogger(__name__)


async def _get_student_class(db, school_id: int, student_id: int):
    """查学生所在班（仅本校）"""
    from core.models import Student

    return await db.scalar(
        select(Student.class_id).where(
            Student.id == student_id, Student.school_id == school_id
        )
    )


async def _homeroom_of_class(db, school_id: int, class_id: int) -> list[dict]:
    """class 的班主任（Assignment 事实源，is_active + 未过期）"""
    from modules.teacher_mgmt.models import TeacherRoleAssignment as TRA

    now = datetime.now()
    rows = (
        await db.execute(
            select(TRA.teacher_user_id)
            .where(
                TRA.school_id == school_id,
                TRA.role_type == "homeroom_teacher",
                TRA.scope_type == "class",
                TRA.scope_id == class_id,
                TRA.is_active.is_(True),
                TRA.expires_at.is_(None) | (TRA.expires_at > now),
            )
        )
    ).all()
    return [int(r[0]) for r in rows]


async def _grade_leader_of_grade(db, school_id: int, grade_id: int) -> list[dict]:
    """grade 的年级组长（Assignment 事实源）"""
    from modules.teacher_mgmt.models import TeacherRoleAssignment as TRA

    now = datetime.now()
    rows = (
        await db.execute(
            select(TRA.teacher_user_id)
            .where(
                TRA.school_id == school_id,
                TRA.role_type == "grade_leader",
                TRA.scope_type == "grade",
                TRA.scope_id == grade_id,
                TRA.is_active.is_(True),
                TRA.expires_at.is_(None) | (TRA.expires_at > now),
            )
        )
    ).all()
    return [int(r[0]) for r in rows]


async def _subject_teacher(db, school_id: int, class_id: int, subject: str) -> list[dict]:
    """任课教师（teacher_subjects 学科+班级粒度；is_active）"""
    from modules.teacher_mgmt.models import TeacherSubject

    now = datetime.now()
    rows = (
        await db.execute(
            select(TeacherSubject.teacher_user_id)
            .where(
                TeacherSubject.school_id == school_id,
                TeacherSubject.class_id == class_id,
                TeacherSubject.subject_code == subject,
                TeacherSubject.is_active.is_(True),
                TeacherSubject.expires_at.is_(None) | (TeacherSubject.expires_at > now),
            )
        )
    ).all()
    return [int(r[0]) for r in rows]


async def _assignment_subject_teacher(db, school_id: int, class_id: int) -> list[dict]:
    """兜底：assignment subject_teacher@class（无学科维度，只能到班级级）"""
    from modules.teacher_mgmt.models import TeacherRoleAssignment as TRA

    now = datetime.now()
    rows = (
        await db.execute(
            select(TRA.teacher_user_id)
            .where(
                TRA.school_id == school_id,
                TRA.role_type == "subject_teacher",
                TRA.scope_type == "class",
                TRA.scope_id == class_id,
                TRA.is_active.is_(True),
                TRA.expires_at.is_(None) | (TRA.expires_at > now),
            )
        )
    ).all()
    return [int(r[0]) for r in rows]


async def _user_names(db, user_ids: list[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    from core.models import User

    rows = (
        await db.execute(select(User.id, User.username).where(User.id.in_(user_ids)))
    ).all()
    return {int(r[0]): r[1] for r in rows}


def _unresolved(reason: str, **extra) -> dict:
    return {
        "resolved": False,
        "owner": None,
        "owner_name": None,
        "owner_role": None,
        "role_type": None,
        "scope_type": None,
        "scope_id": None,
        "source": "unresolved",
        "confidence": None,
        "unresolved_reason": reason,
        "conflict": [],
        **extra,
    }


def _resolved(owner_id: int, owner_name: str, role: str, scope_type: str,
              scope_id, source: str, confidence: str, conflict: list = None) -> dict:
    return {
        "resolved": True,
        "owner": owner_id,
        "owner_name": owner_name,
        "owner_role": role,
        "role_type": role,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "source": source,
        "confidence": confidence,
        "unresolved_reason": None,
        "conflict": conflict or [],
    }


async def resolve_owner(db, user, *, student_id=None, grade_id=None, subject=None):
    """
    责任解析入口（Assignment 唯一事实源，不猜人，不造任务）。

    越权规则：
      ms_admin → 全校可解析
      grade_leader → 仅本年级（grade_id 匹配 或 学生属本年级）
      class_teacher → 仅本班（学生属本班）
      其余角色 → 403 no_access
    """
    school_id = user.school_id
    user_role = (user.role.value if hasattr(user.role, "value") else str(user.role)).lower()

    # ── 1) 确定目标 scope 并校验解析者权限 ──
    target_class_id = None
    target_grade_id = grade_id
    if student_id is not None:
        target_class_id = await _get_student_class(db, school_id, student_id)
        if target_class_id is None:
            return _unresolved("no_assignment", reason_detail="学生不存在或不在本校")
        from core.models import Class

        target_grade_id = await db.scalar(
            select(Class.grade_id).where(Class.id == target_class_id, Class.school_id == school_id)
        )

    if user_role == "ms_admin":
        pass  # 全校
    elif user_role == "grade_leader":
        # 仅本年级（users.grade_id 或 assignment grade_leader@grade）
        from core.access import load_assignment_scopes

        scopes = await load_assignment_scopes(db, user)
        grade_ids = set(scopes.get("grade", set()))
        if user.grade_id:
            grade_ids.add(int(user.grade_id))
        if target_grade_id is None or int(target_grade_id) not in grade_ids:
            return _unresolved("no_access", reason_detail="越权：只能解析本年级责任人")
    elif user_role == "class_teacher":
        from core.access import load_assignment_scopes

        scopes = await load_assignment_scopes(db, user)
        class_ids = set(scopes.get("class", set()))
        if user.class_id:
            class_ids.add(int(user.class_id))
        if target_class_id is None or int(target_class_id) not in class_ids:
            return _unresolved("no_access", reason_detail="越权：只能解析本班责任人")
    else:
        return _unresolved("no_access", reason_detail="当前角色无权解析责任")

    # ── 2) 按请求类型解析 ──
    # 2a) student_id → 班主任
    if student_id is not None and subject is None:
        owners = await _homeroom_of_class(db, school_id, target_class_id)
        if not owners:
            return _unresolved("no_assignment", reason_detail="该班无班主任 Assignment（不猜人）")
        if len(owners) > 1:
            names = await _user_names(db, owners)
            return {
                **_unresolved("conflict", reason_detail=f"该班存在 {len(owners)} 个班主任 Assignment"),
                "conflict": [{"user_id": o, "username": names.get(o, str(o))} for o in owners],
            }
        names = await _user_names(db, owners)
        return _resolved(owners[0], names.get(owners[0], str(owners[0])),
                         "homeroom_teacher", "class", target_class_id,
                         "assignment_homeroom_teacher", "high")

    # 2b) student_id + subject → 任课教师
    if student_id is not None and subject:
        owners = await _subject_teacher(db, school_id, target_class_id, subject)
        source = "teacher_subjects"
        confidence = "high"
        if not owners:
            owners = await _assignment_subject_teacher(db, school_id, target_class_id)
            source = "assignment_subject_teacher"
            confidence = "medium"
        if not owners:
            return _unresolved("no_assignment",
                               reason_detail=f"该班无「{subject}」任课教师 Assignment（不猜人）")
        if len(owners) > 1:
            names = await _user_names(db, owners)
            return {
                **_unresolved("conflict", reason_detail=f"该班「{subject}」存在 {len(owners)} 个任课教师"),
                "conflict": [{"user_id": o, "username": names.get(o, str(o))} for o in owners],
            }
        names = await _user_names(db, owners)
        return _resolved(owners[0], names.get(owners[0], str(owners[0])),
                         "subject_teacher", "class", target_class_id,
                         source, confidence)

    # 2c) grade_id → 年级组长
    if grade_id is not None:
        owners = await _grade_leader_of_grade(db, school_id, int(grade_id))
        if not owners:
            return _unresolved("no_assignment", reason_detail="该年级无年级组长 Assignment（不猜人）")
        if len(owners) > 1:
            names = await _user_names(db, owners)
            return {
                **_unresolved("conflict", reason_detail=f"该年级存在 {len(owners)} 个年级组长"),
                "conflict": [{"user_id": o, "username": names.get(o, str(o))} for o in owners],
            }
        names = await _user_names(db, owners)
        return _resolved(owners[0], names.get(owners[0], str(owners[0])),
                         "grade_leader", "grade", int(grade_id),
                         "assignment_grade_leader", "high")

    return _unresolved("invalid_request", reason_detail="必须提供 student_id 或 grade_id")
