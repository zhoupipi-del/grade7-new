"""
tests/ai_native/test_tenant_context.py — Inv 2: ResourceScopeResolver tenant 契约

Slice 1 RED→GREEN 测试（GOVERNANCE GATE）：组件 `ai_native.governance.resource_scope`
已实现，本文件锁定 Inv 2 全量契约（含 REVISE 轮的 fail-close 与 ResourceScope model）。

契约（canonical）：
    ResourceScope（dataclass）字段：
        school_id / grade_ids / class_ids / student_ids

    resolve_scope(requested, authorized) -> ResourceScope
        入参可为 ResourceScope 或 dict（边界 normalize，内部 canonical 为 ResourceScope）。
        RequestedScope ∩ AuthorizedScope = EffectiveScope。

    authorized 的 student_ids 语义严格复用 core/access.py student_id_scope：
        None  → 不限制（当前租户内全可见，等于放行请求）
        []    → 零可见（effective 必须为空集合，不是"不过滤"）
        {..}  → 白名单（effective = requested ∩ authorized）

    ★ tenant fail-close：authorized.school_id 缺失或 None → DENY（全空），
       绝不允许拿 None 代表"所有租户可见"（fail-open 禁止）。

    安全约束：即使 LLM 参数自带 school_id / student_id，effective scope 由
    authorized 决定，越权 id 一律裁剪。不得 mock 出与 core/access.py 无关的
    第二套 RBAC。
"""

from __future__ import annotations

import importlib

import pytest


def _require_resource_scope():
    """加载目标组件；未实现 → 明确 FAIL（正确 RED，而非 collection error）。"""
    try:
        return importlib.import_module("ai_native.governance.resource_scope")
    except ModuleNotFoundError as exc:  # pragma: no cover - RED 分支
        pytest.fail(
            f"RED: ai_native/governance/resource_scope.py 尚未实现（Slice 1 需求未落地）: {exc}"
        )


def _scope(school_id=None, grade_ids=None, class_ids=None, student_ids=None):
    return {
        "school_id": school_id,
        "grade_ids": None if grade_ids is None else set(grade_ids),
        "class_ids": None if class_ids is None else set(class_ids),
        "student_ids": None if student_ids is None else set(student_ids),
    }


class TestResourceScopeCanonicalModel:
    def test_model_has_four_fields(self):
        mod = _require_resource_scope()
        scope = mod.ResourceScope(school_id=1, student_ids={1, 2})
        assert scope.school_id == 1
        assert scope.grade_ids is None
        assert scope.class_ids is None
        assert scope.student_ids == {1, 2}

    def test_from_dict_normalizes_boundary(self):
        mod = _require_resource_scope()
        scope = mod.ResourceScope.from_dict(
            {"school_id": 1, "grade_ids": {7}, "class_ids": None, "student_ids": []}
        )
        assert scope.school_id == 1
        assert scope.grade_ids == {7}
        assert scope.student_ids == set()

    def test_resolver_accepts_model_and_dict(self):
        mod = _require_resource_scope()
        requested = mod.ResourceScope(school_id=1, student_ids={1, 2, 3})
        authorized = _scope(school_id=1, student_ids={2, 3})
        effective = mod.resolve_scope(requested, authorized)
        assert isinstance(effective, mod.ResourceScope)
        assert effective.student_ids == {2, 3}


class TestInv2RequestedSchoolWithinAuthorized:
    def test_requested_school_match_authorized_allows(self):
        mod = _require_resource_scope()
        requested = _scope(school_id=1, student_ids={101, 102})
        authorized = _scope(school_id=1)  # school 级授权，student_ids=None=全校
        effective = mod.resolve_scope(requested, authorized)
        assert isinstance(effective, mod.ResourceScope)
        assert effective.school_id == 1
        # authorized None 语义（复用 core/access）：不额外裁剪
        assert effective.student_ids == {101, 102}

    def test_requested_school_outside_authorized_yields_empty(self):
        mod = _require_resource_scope()
        requested = _scope(school_id=2, student_ids={201})
        authorized = _scope(school_id=1)  # 只授权 school 1
        effective = mod.resolve_scope(requested, authorized)
        # 跨校 → 零可见，绝不能保留 school=2 的任何 id
        assert effective.student_ids == set()


class TestInv2StudentIntersection:
    def test_students_scope_is_intersection(self):
        mod = _require_resource_scope()
        requested = _scope(school_id=1, student_ids={1, 2, 3, 4})
        authorized = _scope(school_id=1, student_ids={2, 3})
        effective = mod.resolve_scope(requested, authorized)
        assert effective.student_ids == {2, 3}

    def test_authorized_empty_list_means_zero_visibility(self):
        mod = _require_resource_scope()
        requested = _scope(school_id=1, student_ids={1, 2})
        authorized = _scope(school_id=1, student_ids=[])  # 零可见
        effective = mod.resolve_scope(requested, authorized)
        assert effective.student_ids == set()

    def test_authorized_none_means_no_student_restriction(self):
        mod = _require_resource_scope()
        requested = _scope(school_id=1, student_ids={7, 8})
        authorized = _scope(school_id=1, student_ids=None)  # 全校（core/access 语义）
        effective = mod.resolve_scope(requested, authorized)
        assert effective.student_ids == {7, 8}


class TestInv2TenantFailClosed:
    def test_authorized_school_id_none_denies(self):
        mod = _require_resource_scope()
        requested = _scope(school_id=2, student_ids={201})
        authorized = _scope(school_id=None)  # tenant 未指定 → fail-close
        effective = mod.resolve_scope(requested, authorized)
        assert effective.student_ids == set()

    def test_authorized_school_id_missing_denies(self):
        mod = _require_resource_scope()
        requested = _scope(school_id=2, student_ids={201})
        authorized = _scope()  # school_id 缺失（None）
        effective = mod.resolve_scope(requested, authorized)
        assert effective.student_ids == set()

    def test_requested_school_id_none_denies(self):
        mod = _require_resource_scope()
        requested = _scope(school_id=None, student_ids={201})
        authorized = _scope(school_id=1)
        effective = mod.resolve_scope(requested, authorized)
        assert effective.student_ids == set()


class TestInv2NoBypassViaArgs:
    def test_llm_args_cannot_bypass_authorized_scope(self):
        mod = _require_resource_scope()
        # 模拟 LLM 参数里自带的越权 id：请求 999（不在授权白名单）
        requested = _scope(school_id=1, student_ids={999})
        authorized = _scope(school_id=1, student_ids={1, 2})
        effective = mod.resolve_scope(requested, authorized)
        assert 999 not in effective.student_ids

    def test_school_id_in_args_cannot_extend_scope(self):
        mod = _require_resource_scope()
        requested = _scope(school_id=99, student_ids={1})
        authorized = _scope(school_id=1)
        effective = mod.resolve_scope(requested, authorized)
        # 越权 school 被拒绝：不得保留 school=99 的可见性
        assert effective.student_ids == set()
