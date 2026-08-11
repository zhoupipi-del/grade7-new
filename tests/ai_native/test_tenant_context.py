"""
tests/ai_native/test_tenant_context.py — Inv 2: ResourceScopeResolver tenant 契约

RED GATE 测试（Phase E Slice 1）：组件 `ai_native.governance.resource_scope`
尚未实现，全部测试预期 FAIL（需求未实现导致的正确失败，非 collection error）。

契约（未来实现必须满足）：
    resource_scope.resolve_scope(requested, authorized) -> effective

    requested / authorized / effective 均为 dict：
        {"school_id": int | None,
         "grade_ids": set[int] | None,
         "class_ids": set[int] | None,
         "student_ids": set[int] | None}

    authorized 的 student_ids 语义严格复用 core/access.py student_id_scope：
        None  → 不限制（该校全部可见，等于放行请求）
        []    → 零可见（effective 必须为空集合，不是"不过滤"）
        {..}  → 白名单（effective = requested ∩ authorized）

    school 维度：
        requested.school_id 不在 authorized 授权范围 → effective 全空（deny）

    安全约束：即使 LLM 参数自带 school_id / student_id，effective scope
    必须由 authorized 决定，越权 id 一律裁剪，不得绕过 AuthorizedScope。
    不得 mock 出与 core/access.py 无关的第二套 RBAC。
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


class TestInv2RequestedSchoolWithinAuthorized:
    def test_requested_school_match_authorized_allows(self):
        mod = _require_resource_scope()
        requested = _scope(school_id=1, student_ids={101, 102})
        authorized = _scope(school_id=1)  # school 级授权，student_ids=None=全校
        effective = mod.resolve_scope(requested, authorized)
        assert effective["school_id"] == 1
        # authorized None 语义（复用 core/access）：不额外裁剪
        assert effective["student_ids"] == {101, 102}

    def test_requested_school_outside_authorized_yields_empty(self):
        mod = _require_resource_scope()
        requested = _scope(school_id=2, student_ids={201})
        authorized = _scope(school_id=1)  # 只授权 school 1
        effective = mod.resolve_scope(requested, authorized)
        # 跨校 → 零可见，绝不能保留 school=2 的任何 id
        assert effective["student_ids"] == set()


class TestInv2StudentIntersection:
    def test_students_scope_is_intersection(self):
        mod = _require_resource_scope()
        requested = _scope(school_id=1, student_ids={1, 2, 3, 4})
        authorized = _scope(school_id=1, student_ids={2, 3})
        effective = mod.resolve_scope(requested, authorized)
        assert effective["student_ids"] == {2, 3}

    def test_authorized_empty_list_means_zero_visibility(self):
        mod = _require_resource_scope()
        requested = _scope(school_id=1, student_ids={1, 2})
        authorized = _scope(school_id=1, student_ids=[])  # 零可见
        effective = mod.resolve_scope(requested, authorized)
        assert effective["student_ids"] == set()

    def test_authorized_none_means_no_student_restriction(self):
        mod = _require_resource_scope()
        requested = _scope(school_id=1, student_ids={7, 8})
        authorized = _scope(school_id=1, student_ids=None)  # 全校（core/access 语义）
        effective = mod.resolve_scope(requested, authorized)
        assert effective["student_ids"] == {7, 8}


class TestInv2NoBypassViaArgs:
    def test_llm_args_cannot_bypass_authorized_scope(self):
        mod = _require_resource_scope()
        # 模拟 LLM 参数里自带的越权 id：请求 999（不在授权白名单）
        requested = _scope(school_id=1, student_ids={999})
        authorized = _scope(school_id=1, student_ids={1, 2})
        effective = mod.resolve_scope(requested, authorized)
        assert 999 not in effective["student_ids"]

    def test_school_id_in_args_cannot_extend_scope(self):
        mod = _require_resource_scope()
        requested = _scope(school_id=99, student_ids={1})
        authorized = _scope(school_id=1)
        effective = mod.resolve_scope(requested, authorized)
        # 越权 school 被拒绝：不得保留 school=99 的可见性
        assert effective["student_ids"] == set()
