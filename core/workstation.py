"""
core/workstation.py — 工作身份解析（Workstation）

周主任拍板（2026-08-13）：不同的人看到不同的 WINGS。
老师登录后不再面对 30+ 菜单，而是系统先知道"他是谁、负责谁"，
给出 ≤5 个一级入口的工作台，按身份切换。

身份来源优先级（不重造权限系统）：
  1. teacher_role_assignments（岗位分配，已启用：8 班主任 + 年级组长 + 任课教师）
  2. users.role（旧字段，仅 fallback）

⚠️ 本模块只负责"身份/菜单"识别，不负责权限放权——
    后端 Scope/Policy（get_student_or_403 / student_id_scope 等）保持不动，
    前端隐藏菜单绝不等于后端放权。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select

logger = logging.getLogger(__name__)


# ── 身份常量 ────────────────────────────────────────────────
# identity: 前端 WORKSPACE_MENUS 的 key，也是后端菜单分组的 key

IDENTITY_HOMEROOM = "homeroom_teacher"   # 班主任
IDENTITY_SUBJECT = "subject_teacher"     # 任课教师
IDENTITY_GRADE_LEADER = "grade_leader"   # 年级组长
IDENTITY_MORAL_ADMIN = "moral_admin"     # 德育主任
IDENTITY_PRINCIPAL = "principal"         # 校长
IDENTITY_COUNSELOR = "counselor"         # 心理教师
IDENTITY_PARENT = "parent"               # 家长
IDENTITY_STUDENT = "student"             # 学生

# assignment role_type → identity（scope_type/scope_id 原样透传）
_ASSIGNMENT_TO_IDENTITY = {
    "homeroom_teacher": IDENTITY_HOMEROOM,
    "grade_leader": IDENTITY_GRADE_LEADER,
    "subject_teacher": IDENTITY_SUBJECT,
    "moral_admin": IDENTITY_MORAL_ADMIN,
    "principal": IDENTITY_PRINCIPAL,
    "counselor": IDENTITY_COUNSELOR,
    "research_leader": IDENTITY_SUBJECT,  # 教研组长暂归任课教师工作台
}

# users.role → identity（fallback，仅当 assignment 未覆盖该身份时）
_ROLE_TO_IDENTITY = {
    "ms_admin": IDENTITY_MORAL_ADMIN,
    "group_admin": IDENTITY_PRINCIPAL,
    "branch_admin": IDENTITY_PRINCIPAL,
    "grade_leader": IDENTITY_GRADE_LEADER,
    "class_teacher": IDENTITY_HOMEROOM,
    "teacher": IDENTITY_SUBJECT,
    "counselor": IDENTITY_COUNSELOR,
    "parent": IDENTITY_PARENT,
    "student": IDENTITY_STUDENT,
}

# 身份默认排序（default 优先顺序：班主任 > 年级组长 > 任课教师 > 德育主任 > ...）
_IDENTITY_ORDER = {
    IDENTITY_HOMEROOM: 0,
    IDENTITY_GRADE_LEADER: 1,
    IDENTITY_SUBJECT: 2,
    IDENTITY_MORAL_ADMIN: 3,
    IDENTITY_PRINCIPAL: 4,
    IDENTITY_COUNSELOR: 5,
    IDENTITY_PARENT: 6,
    IDENTITY_STUDENT: 7,
}

# 身份中文标签
_IDENTITY_LABEL = {
    IDENTITY_HOMEROOM: "班主任",
    IDENTITY_SUBJECT: "任课教师",
    IDENTITY_GRADE_LEADER: "年级组长",
    IDENTITY_MORAL_ADMIN: "德育主任",
    IDENTITY_PRINCIPAL: "校长",
    IDENTITY_COUNSELOR: "心理教师",
    IDENTITY_PARENT: "家长",
    IDENTITY_STUDENT: "学生",
}


def identity_label(identity: str) -> str:
    return _IDENTITY_LABEL.get(identity, identity)


async def resolve_workstations(db, user) -> dict:
    """
    解析当前用户的工作身份列表。

    返回：
      {
        "workstations": [
          {"identity": "homeroom_teacher", "label": "班主任",
           "scope_type": "class", "scope_id": 1, "scope_name": "2501班",
           "title": "2501班班主任", "is_default": bool},
          ...
        ],
        "default_identity": "homeroom_teacher",
      }

    规则：
      - 先读 teacher_role_assignments（is_active + 未过期），按 role_type 映射身份
      - 未出现的身份用 users.role fallback 补一个（保证任何用户至少有一个工作台）
      - scope_name 查询 classes/grades 表；查不到用 scope_id 兜底
      - default = 排序最靠前的身份（班主任 > 年级组长 > 任课教师 > ...）
      - parent/student 只有 users.role 身份（无 assignment）
    """
    user_role = (user.role.value if hasattr(user.role, "value") else str(user.role)).lower()

    # 1) 岗位身份（assignment 优先）
    identities: dict[str, dict] = {}
    try:
        from modules.teacher_mgmt.models import TeacherRoleAssignment as TRA

        now = datetime.now()
        stmt = select(TRA.role_type, TRA.scope_type, TRA.scope_id).where(
            TRA.teacher_user_id == user.id,
            TRA.school_id == user.school_id,
            TRA.is_active.is_(True),
            TRA.expires_at.is_(None) | (TRA.expires_at > now),
        )
        rows = (await db.execute(stmt)).all()
        for role_type, scope_type, scope_id in rows:
            identity = _ASSIGNMENT_TO_IDENTITY.get((role_type or "").lower())
            if not identity:
                continue
            key = f"{identity}:{(scope_type or '').lower()}:{scope_id or 0}"
            identities[key] = {
                "identity": identity,
                "label": identity_label(identity),
                "scope_type": (scope_type or "").lower(),
                "scope_id": int(scope_id) if scope_id is not None else None,
                "_sort": _IDENTITY_ORDER.get(identity, 99),
            }
    except ImportError:
        pass  # teacher_mgmt 未加载 → 纯 users.role fallback
    except Exception as e:  # noqa: BLE001 — 身份解析失败不阻断登录
        logger.warning("workstation assignment 解析失败(降级 users.role): %s", e)

    # 2) users.role fallback（该身份未出现时才补）
    fallback_identity = _ROLE_TO_IDENTITY.get(user_role)
    if fallback_identity and not any(v["identity"] == fallback_identity for v in identities.values()):
        # 按用户 role 自带 scope
        if fallback_identity == IDENTITY_HOMEROOM and user.class_id:
            scope_type, scope_id = "class", user.class_id
        elif fallback_identity == IDENTITY_GRADE_LEADER and user.grade_id:
            scope_type, scope_id = "grade", user.grade_id
        elif fallback_identity in (IDENTITY_MORAL_ADMIN, IDENTITY_PRINCIPAL, IDENTITY_COUNSELOR):
            scope_type, scope_id = "school", None
        elif fallback_identity == IDENTITY_PARENT:
            scope_type, scope_id = "school", None
        else:
            scope_type, scope_id = "school", None
        identities[f"{fallback_identity}:{scope_type}:{scope_id or 0}"] = {
            "identity": fallback_identity,
            "label": identity_label(fallback_identity),
            "scope_type": scope_type,
            "scope_id": scope_id,
            "_sort": _IDENTITY_ORDER.get(fallback_identity, 99),
        }

    if not identities:
        return {"workstations": [], "default_identity": None}

    # 3) 补 scope_name + title
    class_ids = {v["scope_id"] for v in identities.values() if v["scope_type"] == "class" and v["scope_id"]}
    grade_ids = {v["scope_id"] for v in identities.values() if v["scope_type"] == "grade" and v["scope_id"]}
    class_names: dict[int, str] = {}
    grade_names: dict[int, str] = {}
    try:
        from core.models import Class, Grade

        if class_ids:
            rows = (await db.execute(select(Class.id, Class.name).where(Class.id.in_(class_ids)))).all()
            class_names = {int(r[0]): r[1] for r in rows}
        if grade_ids:
            rows = (await db.execute(select(Grade.id, Grade.name).where(Grade.id.in_(grade_ids)))).all()
            grade_names = {int(r[0]): r[1] for r in rows}
    except Exception as e:  # noqa: BLE001
        logger.warning("workstation scope_name 查询失败: %s", e)

    workstations = []
    for v in identities.values():
        if v["scope_type"] == "class" and v["scope_id"]:
            scope_name = class_names.get(v["scope_id"], f"班{v['scope_id']}")
        elif v["scope_type"] == "grade" and v["scope_id"]:
            scope_name = grade_names.get(v["scope_id"], f"年级{v['scope_id']}")
        else:
            scope_name = "全校"
        v["scope_name"] = scope_name
        v["title"] = f"{scope_name}{v['label']}"
        v.pop("_sort", None)
        workstations.append(v)

    # 4) 排序 + default
    workstations.sort(key=lambda w: _IDENTITY_ORDER.get(w["identity"], 99))
    workstations[0]["is_default"] = True
    for w in workstations[1:]:
        w["is_default"] = False

    return {
        "workstations": workstations,
        "default_identity": workstations[0]["identity"],
    }
