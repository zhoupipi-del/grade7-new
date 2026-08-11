"""
ai_native.governance.resource_scope — ResourceScope model + Resolver（Inv 2 / Inv 14 scope 侧）
===============================================================================================

核心不变量：
    RequestedScope ∩ AuthorizedScope = EffectiveScope

★ canonical representation 是 ResourceScope（dataclass），不是裸 dict。
  为兼容边界，resolve_scope 接受 dict 输入并在入口 normalize；内部一律
  ResourceScope，杜绝 Tool/Permission/Snapshot/API 各自解释字段导致的漂移。

ResourceScope 字段（Slice 1 最小集，不含 subject/teacher 维度——用不到不提前膨胀）：
    school_id:  int | None    租户。None = 未授权租户（fail-close，见下）
    grade_ids:  set | None    None = 当前租户内不限年级
    class_ids:  set | None    None = 当前租户内不限班级
    student_ids: set | None   None = 当前租户内全可见；[] = 零可见；{..} = 白名单
                              （语义严格复用 core/access.py student_id_scope）

★ tenant fail-close（杜绝 fail-open）：
    authorized.school_id 缺失或 None → DENY（全空）。student_ids 的 None 只表示
    "当前租户内全可见"，绝不能把 tenant 的 None 误解为"所有租户都可见"。
    将来若出现跨学校集团级角色，应显式设计 authorized_school_ids，不得拿 None
    表示所有租户。

★ 不得再造第二套 RBAC：authorized scope 的来源是 core/access.py
  （student_id_scope / get_student_or_403 / load_assignment_scopes），
  本层只做交集运算，不重新定义可见性语义。

对应测试：tests/ai_native/test_tenant_context.py（Inv 2 全量）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Set, Union


def _as_set(value):
    """边界 normalize：list/tuple → set；None 保留（None=不限制 ≠ 空集=零可见）。"""
    if value is None:
        return None
    return set(value)


@dataclass
class ResourceScope:
    """资源维度（请求 ∩ 授权）的 canonical 表示。"""

    school_id: Optional[int] = None
    grade_ids: Optional[Set[int]] = None
    class_ids: Optional[Set[int]] = None
    student_ids: Optional[Set[int]] = None

    @classmethod
    def from_dict(cls, data: dict) -> "ResourceScope":
        """边界 normalize：接受裸 dict 输入，内部转为 canonical ResourceScope。"""
        return cls(
            school_id=data.get("school_id"),
            grade_ids=_as_set(data.get("grade_ids")),
            class_ids=_as_set(data.get("class_ids")),
            student_ids=_as_set(data.get("student_ids")),
        )


def _to_scope(value: Union[ResourceScope, dict]) -> ResourceScope:
    if isinstance(value, ResourceScope):
        return value
    if isinstance(value, dict):
        return ResourceScope.from_dict(value)
    raise TypeError(f"期望 ResourceScope 或 dict，得到 {type(value).__name__}")


def _intersect(requested_ids, authorized_ids):
    """authorized 语义（core/access.py）：None=不限制；[]=零可见；{..}=白名单。"""
    if authorized_ids is None:
        # None → 不限制（当前租户内）：保持请求范围
        return set(requested_ids) if requested_ids is not None else None
    if not authorized_ids:
        # [] → 零可见：必须返回空集合（不是"不过滤"！）
        return set()
    if requested_ids is None:
        return set(authorized_ids)
    return set(requested_ids) & set(authorized_ids)


def _empty_scope() -> ResourceScope:
    """DENY 的 effective scope：零可见（空集，不是 None——None=不限制，语义相反）。"""
    return ResourceScope(
        school_id=None,
        grade_ids=set(),
        class_ids=set(),
        student_ids=set(),
    )


def resolve_scope(requested, authorized) -> ResourceScope:
    """
    requested ∩ authorized = effective（ResourceScope × ResourceScope → ResourceScope）。

    入参可为 ResourceScope 或 dict（边界 normalize，内部 canonical 为 ResourceScope）。
    """
    req = _to_scope(requested)
    auth = _to_scope(authorized)

    # tenant fail-close：authorized 未明确租户 → DENY（全空），禁止 fail-open
    if auth.school_id is None or req.school_id != auth.school_id:
        return _empty_scope()

    return ResourceScope(
        school_id=req.school_id,
        grade_ids=_intersect(req.grade_ids, auth.grade_ids),
        class_ids=_intersect(req.class_ids, auth.class_ids),
        student_ids=_intersect(req.student_ids, auth.student_ids),
    )


class ResourceScopeResolver:
    """Slice 1 正式组件（对象形态封装；resolve_scope 为纯函数主入口）。"""

    @staticmethod
    def resolve(requested, authorized) -> ResourceScope:
        return resolve_scope(requested, authorized)
