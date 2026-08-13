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


# ── 工作台摘要（Workspace Summary，2026-08-13 班主任工作台 V1）──
# 统一接口：前端负责"显示什么"，后端负责"这个角色到底有权看到什么"。
# 绝不把业务权限逻辑堆进 Vue；无真实数据就诚实显示"暂无可信数据"，
# 不拿预警数量冒充待办。

_SUMMARY_DATA_QUALITY_READY = "ready_but_no_real_data"
_SUMMARY_DATA_QUALITY_TRUSTED = "trusted"
_SUMMARY_DATA_QUALITY_UNVERIFIED = "source_unverified"


async def _verify_workspace_scope(db, user, identity: str, scope_type: str, scope_id) -> bool:
    """
    验证当前用户是否确实拥有该 (identity, scope_type, scope_id) 工作台。
    返回 False 时调用方必须 403——绝不信任前端传的 scope 参数。
    """
    resolved = await resolve_workstations(db, user)
    for ws in resolved.get("workstations", []):
        if (
            ws.get("identity") == identity
            and ws.get("scope_type") == scope_type
            and (ws.get("scope_id") or None) == (int(scope_id) if scope_id else None)
        ):
            return True
    return False


async def build_workspace_summary(db, user, identity: str, scope_type: str, scope_id) -> dict:
    """
    按工作身份组装首页 ViewModel。

    第一版只实现班主任（homeroom_teacher）+ 年级组长（grade_leader）：
      - 班主任: 本班学生数 / 可信行为数 / 可信表扬数 / open_tasks=null（Task Center 未建）
      - 年级组长: 本年级各班汇总（V1 简化：年级学生数 + 可信行为/表扬总数）
    其余身份返回通用骨架（cards 全 null + data_quality 全 unverified），
    待各身份工作台 V1 逐步填充。

    data_quality 语义：
      behavior/praise: ready_but_no_real_data（功能就绪但无真实可信数据）
                       → 一旦 teacher_manual>0 变 trusted
      attendance:     source_unverified（考勤表无 source 列，来源未核验，诚实标注）
    """
    school_id = user.school_id
    scope_id_i = int(scope_id) if scope_id else None

    if identity == IDENTITY_HOMEROOM and scope_type == "class" and scope_id_i:
        # ── 班主任：本班数据 ──
        from sqlalchemy import func, select

        from core.models import Student

        student_count = await db.scalar(
            select(func.count()).select_from(Student).where(
                Student.school_id == school_id, Student.class_id == scope_id_i
            )
        ) or 0

        # 可信行为/表扬（source=teacher_manual 是唯一可信口径）
        from modules.behavior.models import DisciplineRecord

        trusted_behavior = await db.scalar(
            select(func.count()).select_from(DisciplineRecord).where(
                DisciplineRecord.school_id == school_id,
                DisciplineRecord.class_id == scope_id_i,
                DisciplineRecord.source == "teacher_manual",
            )
        ) or 0
        from modules.evaluation.models import EvaluationScore

        trusted_praise = await db.scalar(
            select(func.count()).select_from(EvaluationScore).where(
                EvaluationScore.school_id == school_id,
                EvaluationScore.class_id == scope_id_i,
                EvaluationScore.source == "teacher_manual",
            )
        ) or 0

        # attention：只在有真实可信数据时填充；无数据 → []（前端显示"暂无可信数据"）
        attention = []
        if trusted_behavior > 0:
            attention.append({
                "type": "behavior",
                "level": "info",
                "title": f"本班近月 {trusted_behavior} 条可信行为记录",
                "hint": "来源为老师真实登记（teacher_manual）",
            })
        if trusted_praise > 0:
            attention.append({
                "type": "praise",
                "level": "success",
                "title": f"本班近月 {trusted_praise} 条正向表扬",
                "hint": "来源为老师真实登记（teacher_manual）",
            })

        class_name = None
        try:
            from core.models import Class

            class_name = await db.scalar(
                select(Class.name).where(Class.id == scope_id_i, Class.school_id == school_id)
            )
        except Exception:  # noqa: BLE001
            class_name = None

        return {
            "workspace": identity,
            "scope": {
                "type": "class",
                "id": scope_id_i,
                "name": class_name or f"班{scope_id_i}",
            },
            "cards": {
                "student_count": int(student_count),
                "trusted_behavior_count": int(trusted_behavior),
                "trusted_praise_count": int(trusted_praise),
                "open_tasks": None,  # Task Center 未建 → 不假造待办
            },
            "attention": attention,
            "data_quality": {
                "behavior": _SUMMARY_DATA_QUALITY_TRUSTED if trusted_behavior > 0 else _SUMMARY_DATA_QUALITY_READY,
                "praise": _SUMMARY_DATA_QUALITY_TRUSTED if trusted_praise > 0 else _SUMMARY_DATA_QUALITY_READY,
                "attendance": _SUMMARY_DATA_QUALITY_UNVERIFIED,
            },
        }

    if identity == IDENTITY_GRADE_LEADER and scope_type == "grade" and scope_id_i:
        # ── 年级组长（V1 简化）：年级级可信汇总 ──
        from sqlalchemy import func, select

        from modules.behavior.models import DisciplineRecord
        from modules.evaluation.models import EvaluationScore

        trusted_behavior = await db.scalar(
            select(func.count()).select_from(DisciplineRecord).where(
                DisciplineRecord.school_id == school_id,
                DisciplineRecord.grade_id == scope_id_i,
                DisciplineRecord.source == "teacher_manual",
            )
        ) or 0
        trusted_praise = await db.scalar(
            select(func.count()).select_from(EvaluationScore).where(
                EvaluationScore.school_id == school_id,
                EvaluationScore.grade_id == scope_id_i,
                EvaluationScore.source == "teacher_manual",
            )
        ) or 0

        grade_name = None
        try:
            from core.models import Grade

            grade_name = await db.scalar(
                select(Grade.name).where(Grade.id == scope_id_i, Grade.school_id == school_id)
            )
        except Exception:  # noqa: BLE001
            grade_name = None

        attention = []
        if trusted_behavior > 0:
            attention.append({
                "type": "behavior", "level": "info",
                "title": f"本年级 {trusted_behavior} 条可信行为记录",
                "hint": "来源为老师真实登记（teacher_manual）",
            })
        if trusted_praise > 0:
            attention.append({
                "type": "praise", "level": "success",
                "title": f"本年级 {trusted_praise} 条正向表扬",
                "hint": "来源为老师真实登记（teacher_manual）",
            })

        return {
            "workspace": identity,
            "scope": {
                "type": "grade",
                "id": scope_id_i,
                "name": grade_name or f"年级{scope_id_i}",
            },
            "cards": {
                "student_count": None,
                "trusted_behavior_count": int(trusted_behavior),
                "trusted_praise_count": int(trusted_praise),
                "open_tasks": None,
            },
            "attention": attention,
            "data_quality": {
                "behavior": _SUMMARY_DATA_QUALITY_TRUSTED if trusted_behavior > 0 else _SUMMARY_DATA_QUALITY_READY,
                "praise": _SUMMARY_DATA_QUALITY_TRUSTED if trusted_praise > 0 else _SUMMARY_DATA_QUALITY_READY,
                "attendance": _SUMMARY_DATA_QUALITY_UNVERIFIED,
            },
        }

    # ── 其余身份：通用骨架（不造假，逐步填充）──
    return {
        "workspace": identity,
        "scope": {
            "type": scope_type,
            "id": scope_id_i,
            "name": scope_name_of(scope_type, scope_id_i) or "",
        },
        "cards": {
            "student_count": None,
            "trusted_behavior_count": None,
            "trusted_praise_count": None,
            "open_tasks": None,
        },
        "attention": [],
        "data_quality": {
            "behavior": _SUMMARY_DATA_QUALITY_UNVERIFIED,
            "praise": _SUMMARY_DATA_QUALITY_UNVERIFIED,
            "attendance": _SUMMARY_DATA_QUALITY_UNVERIFIED,
        },
    }


def scope_name_of(scope_type: str, scope_id) -> str:
    """兜底 scope 名（无查询时用）"""
    if scope_type == "class":
        return f"班{scope_id}"
    if scope_type == "grade":
        return f"年级{scope_id}"
    return "全校"
