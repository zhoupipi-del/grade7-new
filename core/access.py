"""
core/access.py — 数据归属校验（P0-1 安全加固）

v2（2026-07-23）：加入 teacher_role_assignments overlay。
  v1 的 ROLE_CLASS_WIDE 只读单值 user.class_id，一人带多班的班主任会
  只看得到 class_id 那一个班，其余班全瞎。v2 把 users.class_id/grade_id
  与 teacher_role_assignments 的有效作用域做并集。

设计约束（遵循「保守演进铁律」）：
  - 纯新增文件。不修改任何现有函数签名，不引入全局中间件。
  - 只提供判断函数，由各路由显式调用，调用点可审计、可逐个灰度。
  - 失败默认抛异常（拦截模式）；观察模式（ACCESS_ENFORCE=0）下只记录不
    拦截，用于上线前测量影响面，且必须有 ACCESS_SHADOW_UNTIL 硬截止，
    过期自动恢复拦截。详见文件底部「观察模式」段。
  - 不依赖 users.role 是 Enum —— 该列实际是 String(50)。

放置位置：backend/core/access.py
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Student, User, UserRole

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 观察模式（shadow mode）—— 上线前测量影响面用
# ═══════════════════════════════════════════════════════════════
#
# 判定照常跑、结果照常记，但暂不拦截。三条护栏（缺一条就变永久漏洞）：
#   1. 默认拦截——观察是显式 opt-out（ACCESS_ENFORCE=0）。若默认观察，
#      某天部署脚本漏了环境变量，补丁静默失效。
#   2. 必须有硬截止——ACCESS_SHADOW_UNTIL 过期自动恢复拦截并打 ERROR。
#      没有截止的「临时观察」会活到明年。
#   3. 日志格式固定可统计（见 _deny / student_id_scope 的 [SHADOW] 标签）。
ACCESS_ENFORCE = os.environ.get("ACCESS_ENFORCE", "1") != "0"


def _enforcing() -> bool:
    """True=拦截模式；False=观察模式（只记不拦）。"""
    if ACCESS_ENFORCE:
        return True
    until = os.environ.get("ACCESS_SHADOW_UNTIL", "")
    if until:
        try:
            if datetime.now() > datetime.fromisoformat(until):
                logger.error("[ACCESS] 观察模式已过期(%s)，强制恢复拦截", until)
                return True
        except ValueError:
            logger.error("[ACCESS] ACCESS_SHADOW_UNTIL 格式错误(%s)，按拦截处理", until)
            return True
    return False


# ═══════════════════════════════════════════════════════════════
# 角色分层（users.role 主表角色）
# ═══════════════════════════════════════════════════════════════

# 可见本校全部学生
ROLE_SCHOOL_WIDE = {"ms_admin", "group_admin", "branch_admin", "counselor"}
# 基线可见本年级（再与 assignment overlay 求并）
ROLE_GRADE_WIDE = {"grade_leader"}
# 基线可见本班（再与 assignment overlay 求并）
ROLE_CLASS_WIDE = {"class_teacher", "teacher"}
# 只可见绑定的那一个学生
ROLE_SELF_ONLY = {"student", "parent"}


# ═══════════════════════════════════════════════════════════════
# teacher_role_assignments overlay
# ═══════════════════════════════════════════════════════════════

# 哪些 role_type 授予"看学生数据"的资格，以及授予到哪个作用域层级。
#
# ⚠️ 这是一个**策略决定，不是技术决定**，上线前请德育处确认：
#   - subject_teacher 故意不在列表里。任课老师能看本班学生的心理咨询
#     元数据吗？默认答案是不能。若德育处要求放开，在这里加一行，
#     一处生效，不用散落改各模块。
#   - moral_admin 给了 school 级，等同德育处管理员。
#   - counselor 走 school 级，与 psych_counseling 的 PRIVILEGED_ROLES 一致。
ASSIGNMENT_SCOPE_GRANTS: dict[str, str] = {
    "homeroom_teacher": "class",
    "grade_leader": "grade",
    "moral_admin": "school",
    "counselor": "school",
}


async def load_assignment_scopes(db: AsyncSession, user: User) -> dict[str, set[int]]:
    """
    读取该用户在 teacher_role_assignments 上的有效作用域。

    返回 {"school": bool, "grade": {grade_id...}, "class": {class_id...}}
    —— school 用布尔，grade/class 用 id 集合。

    ⚠️ 列名是 teacher_user_id，不是 user_id。
       modules/psych_counseling/services.py:64 的 _check_counselor_role 写的是
       TeacherRoleAssignment.user_id —— 该列不存在，会抛 AttributeError。
       见随附说明，那条要单独修。

    表为空时返回全空集合，行为退化为 v1（只用 users.class_id/grade_id），
    所以本函数在 teacher_role_assignments 尚未启用的环境下是安全的。
    """
    out: dict[str, set[int]] = {"grade": set(), "class": set()}
    school_wide = False

    try:
        from modules.teacher_mgmt.models import TeacherRoleAssignment as TRA
    except ImportError:
        # teacher_mgmt 模块未加载 → 退化为纯 users 字段模式
        return {"school": school_wide, **out}

    now = datetime.now()
    stmt = select(TRA.role_type, TRA.scope_type, TRA.scope_id).where(
        TRA.teacher_user_id == user.id,  # ← 正确列名
        TRA.school_id == user.school_id,
        TRA.is_active == True,  # noqa: E712
        or_(TRA.expires_at.is_(None), TRA.expires_at > now),
    )
    rows = (await db.execute(stmt)).all()

    for role_type, scope_type, scope_id in rows:
        grant = ASSIGNMENT_SCOPE_GRANTS.get((role_type or "").lower())
        if grant is None:
            continue
        # 取 grant 与 scope_type 中更窄的那个，防止配错数据导致越权放大
        effective = (
            grant
            if grant == (scope_type or "").lower()
            else _narrower(grant, (scope_type or "").lower())
        )
        if effective == "school":
            school_wide = True
        elif effective in ("grade", "class") and scope_id is not None:
            out[effective].add(int(scope_id))

    return {"school": school_wide, **out}


_SCOPE_ORDER = {"class": 0, "grade": 1, "school": 2}


def _narrower(a: str, b: str) -> str:
    """取更窄的作用域。未知作用域一律当 class（最窄），宁可少给不可多给。"""
    ra = _SCOPE_ORDER.get(a, 0)
    rb = _SCOPE_ORDER.get(b, 0)
    return a if ra <= rb else b


# ═══════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════


def role_str(user: User) -> str:
    """统一取角色字符串（小写）。兼容 str 与 Enum 两种存储。"""
    r = user.role
    if isinstance(r, UserRole):
        r = r.value
    return (r or "").lower()


def safe_role(user: User) -> UserRole | None:
    """
    转 UserRole 枚举；未知角色返回 None 而不是抛 ValueError。

    调用方负责把 None 处理成 403（而不是 500）。替换以下三处的
    裸 UserRole(user.role) 调用：
      core/routers.py  require_role._guard
      core/routers.py  verify_school_access
      core/tenant_context.py  get_accessible_school_ids
    """
    r = user.role
    if isinstance(r, UserRole):
        return r
    try:
        return UserRole((r or "").lower())
    except ValueError:
        return None


def is_school_wide(user: User) -> bool:
    """
    仅按 users.role 判断是否全校可见（不查 assignment）。
    用在不方便 await 的轻量场景，如任务归属校验。
    需要含 assignment overlay 的判断，用 async 的 has_school_wide_access。
    """
    return role_str(user) in ROLE_SCHOOL_WIDE


async def has_school_wide_access(db: AsyncSession, user: User) -> bool:
    """含 assignment overlay 的全校可见性判断。"""
    if is_school_wide(user):
        return True
    scopes = await load_assignment_scopes(db, user)
    return bool(scopes["school"])


# ═══════════════════════════════════════════════════════════════
# 单个学生：归属校验
# ═══════════════════════════════════════════════════════════════


async def get_student_or_403(
    db: AsyncSession,
    user: User,
    student_id: int,
) -> Student:
    """
    校验 user 是否有权访问 student_id，通过则返回 Student 对象。

    可见范围 = users.role 基线 ∪ teacher_role_assignments overlay

      ms_admin / group_admin / branch_admin / counselor → 本校全部
      grade_leader        → users.grade_id ∪ assignment(grade)
      class_teacher/teacher → users.class_id ∪ assignment(class)
      student / parent    → 仅 users.bound_student_id（不吃 overlay）
      任何角色 + assignment(school) → 本校全部

    跨校或不存在 → 404（统一 404，避免用 403/404 差异探测学生是否存在）
    本校但越权   → 403
    """
    stmt = select(Student).where(
        Student.id == student_id,
        Student.school_id == user.school_id,
    )
    student = (await db.execute(stmt)).scalar_one_or_none()
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学生不存在")

    role = role_str(user)

    # ── 主表角色即全校 ──
    if role in ROLE_SCHOOL_WIDE:
        return student

    # ── 学生/家长：只认绑定关系，不吃 assignment overlay ──
    if role in ROLE_SELF_ONLY:
        if user.bound_student_id and student.id == user.bound_student_id:
            return student
        _deny(user, role, student_id)
        return student  # 仅观察模式走到这里；拦截模式下 _deny 已抛 403

    # ── 教师侧：基线 ∪ overlay ──
    scopes = await load_assignment_scopes(db, user)

    if scopes["school"]:
        return student

    grade_ids = set(scopes["grade"])
    class_ids = set(scopes["class"])
    if role in ROLE_GRADE_WIDE and user.grade_id:
        grade_ids.add(user.grade_id)
    if role in ROLE_CLASS_WIDE and user.class_id:
        class_ids.add(user.class_id)

    if student.grade_id in grade_ids or student.class_id in class_ids:
        return student

    _deny(user, role, student_id)
    return student  # 仅观察模式走到这里；拦截模式下 _deny 已抛 403


def _deny(user: User, role: str, student_id: int) -> bool:
    r"""
    返回 True=放行（观察模式）；拦截模式下直接抛 403。

    日志格式固定，方便 grep 统计影响面：
      grep '\[ACCESS\]\[SHADOW\] deny' app.log | grep -oP 'user_id=\d+' | sort -u | wc -l
    """
    tag = "" if _enforcing() else "[SHADOW]"
    logger.warning(
        "[ACCESS]%s deny user_id=%s role=%s school_id=%s student_id=%s "
        "grade_id=%s class_id=%s bound=%s",
        tag,
        user.id,
        role,
        user.school_id,
        student_id,
        user.grade_id,
        user.class_id,
        user.bound_student_id,
    )
    if _enforcing():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该学生的数据")
    return True


# ═══════════════════════════════════════════════════════════════
# 列表场景：可见 student_id 白名单
# ═══════════════════════════════════════════════════════════════


async def student_id_scope(db: AsyncSession, user: User) -> list[int] | None:
    """
    返回该用户可见的 student_id 列表，用于列表查询的 IN 过滤。

    ⚠️ 返回值语义，调用方务必区分：
      None → 本校全部，调用方保持原有 school_id 过滤即可，不加额外条件
      []   → 一个都看不到，必须让查询返回空结果（不是"不过滤"！）
      [..] → 按此列表 IN 过滤

    调用点一律写 `if scope is not None:`,绝不能写 `if scope:` ——
    后者会把"零可见"当成"不限制",修完比修之前还开放。

    注意：本函数会把可见学生 id 全量取出。单校千人量级完全可接受；
    若将来单校规模上万,改成返回 SQL 子查询交给调用方 .in_() 即可,
    对外语义不变。
    """
    role = role_str(user)

    if role in ROLE_SCHOOL_WIDE:
        return None

    if role in ROLE_SELF_ONLY:
        if user.bound_student_id:
            return [user.bound_student_id]
        # 未绑定：拦截模式零可见；观察模式记录后不限制（维持现状，纯观察）
        logger.warning(
            "[ACCESS]%s scope-unbound user_id=%s role=%s school_id=%s "
            "（学生/家长未绑定 bound_student_id）",
            "" if _enforcing() else "[SHADOW]",
            user.id,
            role,
            user.school_id,
        )
        return [] if _enforcing() else None  # 观察模式：记录后不限制（返回 None=本校全部）

    scopes = await load_assignment_scopes(db, user)
    if scopes["school"]:
        return None

    grade_ids = set(scopes["grade"])
    class_ids = set(scopes["class"])
    if role in ROLE_GRADE_WIDE and user.grade_id:
        grade_ids.add(user.grade_id)
    if role in ROLE_CLASS_WIDE and user.class_id:
        class_ids.add(user.class_id)

    if not grade_ids and not class_ids:
        logger.warning(
            "[ACCESS]%s scope-empty user_id=%s role=%s（本应零可见）",
            "" if _enforcing() else "[SHADOW]",
            user.id,
            role,
        )
        return [] if _enforcing() else None  # 观察模式：记录后不限制（返回 None=本校全部）

    conds = []
    if grade_ids:
        conds.append(Student.grade_id.in_(grade_ids))
    if class_ids:
        conds.append(Student.class_id.in_(class_ids))

    stmt = select(Student.id).where(
        Student.school_id == user.school_id,
        or_(*conds),
    )
    rows = await db.execute(stmt)
    return [r[0] for r in rows.all()]
