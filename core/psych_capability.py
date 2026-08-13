"""
core/psych_capability.py — 心理数据专业授权（CF-01, ⑤.5 Compliance Foundation V1）

核心口径（周主任 2026-08-13 冻结）：

  psych_authorized
    = 存在 active TeacherRoleAssignment
      AND role_type = counselor
      AND school_id 匹配
      AND assignment scope 覆盖目标学生

  绝不根据 user.role（含 ms_admin / counselor 主表角色）、姓名、教师身份、
  年级组长身份、管理员身份进行推断。ms_admin 默认 NO psych detail。

三层访问级别（resolve_psych_access 返回）：
  detail      → 仅 active counselor assignment 覆盖学生（完整详情）
  attention   → class_teacher(本班) / grade_leader(本年级)，仅「专业跟进标记」
  deny        → 其余（任课教师 / ms_admin / 跨 scope / parent / student）
  not_found   → 跨校或学生不存在（由调用方映射 404，防存在性探测）

Capability ≠ Responsibility：
  本模块只管「能不能看心理数据」(Capability)。
  「这件心理工作归谁负责」(Responsibility) 由 ResponsibleOwnerResolver 管理，
  两者数据源可同为 TeacherRoleAssignment，但代码语义必须分开——
  绝不写成一个函数。未来某校 3 名心理老师都可查看全校心理档案，
  不代表某个危机学生三人同时都是负责人。

用法（三模块详情端点统一入口）：
  level = await resolve_psych_access(db, current_user, student_id)
  if level == "detail":       return 完整详情
  if level == "attention":    return attention_payload(...)
  # deny / not_found → require_psych_access 已抛 403/404 并写审计
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Student, User
from core.access import role_str

logger = logging.getLogger("wings.psych_capability")


# ─────────────────────────────────────────────────────────────
# 访问级别常量
# ─────────────────────────────────────────────────────────────
PSY_DETAIL = "detail"          # 完整详情（仅 counselor assignment）
PSY_ATTENTION = "attention"    # 专业跟进标记（class_teacher/grade_leader）
PSY_DENY = "deny"              # 拒绝（存在但无心理授权）
PSY_NOT_FOUND = "not_found"    # 跨校/不存在（防存在性探测 → 404）


def attention_payload(professional_followup_required: bool) -> dict:
    """class_teacher / grade_leader 能拿到的最小「专业跟进信号」。

    刻意不返回任何原因、分数、风险因子、咨询/危机内容，避免贴「心理标签」。
    """
    return {
        "professional_followup_required": bool(professional_followup_required),
        "detail_access": False,
        "recommended_action": "refer_to_psych_staff",
    }


# ─────────────────────────────────────────────────────────────
# 内部：counselor assignment 判定
# ─────────────────────────────────────────────────────────────


async def _counselor_scope_covers(
    db: AsyncSession,
    user: User,
    student: Student,
) -> bool:
    """是否存在 active counselor TeacherRoleAssignment 覆盖该学生。

    只认 role_type=counselor 的 assignment，绝不回退到 user.role 或 ms_admin。
    scope 覆盖规则：
      school → 覆盖全校
      grade  → 覆盖该年级（scope_id == student.grade_id）
      class  → 覆盖该班（scope_id == student.class_id）
    """
    try:
        from modules.teacher_mgmt.models import TeacherRoleAssignment as TRA
    except ImportError:
        return False

    now = datetime.now()
    stmt = select(TRA.scope_type, TRA.scope_id).where(
        TRA.teacher_user_id == user.id,
        TRA.school_id == user.school_id,
        TRA.role_type == "counselor",
        TRA.is_active == True,  # noqa: E712
        or_(TRA.expires_at.is_(None), TRA.expires_at > now),
    )
    rows = (await db.execute(stmt)).all()

    for scope_type, scope_id in rows:
        st = (scope_type or "").lower()
        if st == "school":
            return True
        if st == "grade" and student.grade_id is not None and scope_id == student.grade_id:
            return True
        if st == "class" and student.class_id is not None and scope_id == student.class_id:
            return True
    return False


# ─────────────────────────────────────────────────────────────
# 对外 API：访问级别判定
# ─────────────────────────────────────────────────────────────


async def resolve_psych_access(
    db: AsyncSession,
    user: User,
    student_id: int,
) -> str:
    """判定当前用户对目标学生的心理访问级别（不写审计、不抛异常）。

    返回 PSY_DETAIL / PSY_ATTENTION / PSY_DENY / PSY_NOT_FOUND。
    调用方负责把 PSY_DENY→403、PSY_NOT_FOUND→404，并写审计。
    """
    stmt = select(Student).where(
        Student.id == student_id,
        Student.school_id == user.school_id,
    )
    student = (await db.execute(stmt)).scalar_one_or_none()
    if student is None:
        return PSY_NOT_FOUND

    # 1) 专业授权：counselor assignment
    if await _counselor_scope_covers(db, user, student):
        return PSY_DETAIL

    # 2) 关注标记：class_teacher(本班) / grade_leader(本年级)
    role = role_str(user)
    if role == "class_teacher" and user.class_id and student.class_id == user.class_id:
        return PSY_ATTENTION
    if role == "grade_leader" and user.grade_id and student.grade_id == user.grade_id:
        return PSY_ATTENTION

    # 3) 其余一律拒绝（含 ms_admin / teacher / 跨 scope / parent / student）
    return PSY_DENY


# ─────────────────────────────────────────────────────────────
# 对外 API：统一授权入口（判定 + 审计 + 抛 403/404）
# ─────────────────────────────────────────────────────────────


async def require_psych_access(
    db: AsyncSession,
    user: User,
    student_id: int,
    *,
    resource_type: str,
    action: str,
    purpose: str,
) -> str:
    """三模块详情端点统一授权入口。

    做三件事：
      1. resolve_psych_access 判定访问级别
      2. 写 sensitive_data_access_logs（deny/not_found → denied，detail/attention → allowed）
      3. deny → 403、not_found → 404（防存在性探测）

    返回 "detail" | "attention"，调用方据此返回完整详情或关注标记。
    绝不在本函数内做 ms_admin / user.role 兜底。
    """
    from fastapi import HTTPException
    from core.privacy_audit import (
        log_access, ACCESS_ALLOWED, ACCESS_DENIED, _derive_scope,
    )

    level = await resolve_psych_access(db, user, student_id)
    scope_type, scope_id = _derive_scope(user)
    rid = str(student_id)

    if level == PSY_NOT_FOUND:
        await log_access(
            db,
            user_id=user.id,
            school_id=user.school_id,
            student_id=student_id,
            resource_type=resource_type,
            resource_id=rid,
            action=action,
            purpose=purpose,
            scope_type=scope_type,
            scope_id=scope_id,
            result=ACCESS_DENIED,
            detail="学生不存在或跨校",
        )
        raise HTTPException(status_code=404, detail="学生不存在")

    if level == PSY_DENY:
        await log_access(
            db,
            user_id=user.id,
            school_id=user.school_id,
            student_id=student_id,
            resource_type=resource_type,
            resource_id=rid,
            action=action,
            purpose=purpose,
            scope_type=scope_type,
            scope_id=scope_id,
            result=ACCESS_DENIED,
            detail="无心理专业授权(counselor assignment)",
        )
        raise HTTPException(status_code=403, detail="无权访问心理详情数据")

    # detail / attention 均放行，写 allowed
    await log_access(
        db,
        user_id=user.id,
        school_id=user.school_id,
        student_id=student_id,
        resource_type=resource_type,
        resource_id=rid,
        action=action,
        purpose=purpose,
        scope_type=scope_type,
        scope_id=scope_id,
        result=ACCESS_ALLOWED,
    )
    return level
