"""
tests/ai_native/test_approval_policy.py — ApprovalPolicy (str, Enum) + PolicyAdapter 契约

Slice 1 RED→GREEN 测试（GOVERNANCE REVISE 轮）：锁定
    - ApprovalPolicy 必须是 string enum（后续 Pydantic/JSON/ToolDescriptor/DB
      binding 按字符串持久化，禁止序列化差异）
    - 值集合严格 {none, always, policy_decides}；禁止第二套审批模型
    - PolicyAdapter 最小接口存在，且可被极薄实现满足（本 gate 不实现
      ai_approvals workflow / CommandEnvelope / human approval API）
"""

from __future__ import annotations

import importlib

import pytest


def _require_approval_policy():
    try:
        return importlib.import_module("ai_native.governance.approval_policy")
    except ModuleNotFoundError as exc:  # pragma: no cover - RED 分支
        pytest.fail(
            f"RED: ai_native/governance/approval_policy.py 尚未实现（Slice 1 需求未落地）: {exc}"
        )


class TestApprovalPolicyStringEnum:
    def test_members_are_str_instances(self):
        mod = _require_approval_policy()
        assert isinstance(mod.ApprovalPolicy.NONE, str)
        assert isinstance(mod.ApprovalPolicy.ALWAYS, str)
        assert isinstance(mod.ApprovalPolicy.POLICY_DECIDES, str)

    def test_values_equal_plain_strings(self):
        mod = _require_approval_policy()
        assert mod.ApprovalPolicy.NONE == "none"
        assert mod.ApprovalPolicy.ALWAYS == "always"
        assert mod.ApprovalPolicy.POLICY_DECIDES == "policy_decides"

    def test_value_set_exact(self):
        mod = _require_approval_policy()
        assert {x.value for x in mod.ApprovalPolicy} == {
            "none",
            "always",
            "policy_decides",
        }

    def test_no_second_approval_model(self):
        mod = _require_approval_policy()
        assert not hasattr(mod.ApprovalPolicy, "REQUIRES_HUMAN")
        assert not hasattr(mod.ApprovalPolicy, "AUTO_APPROVE_WHEN_SELF")


class TestPolicyAdapterInterface:
    def test_interface_declares_decide(self):
        mod = _require_approval_policy()
        assert callable(getattr(mod.PolicyAdapter, "decide", None))

    def test_thin_adapter_satisfies_protocol(self):
        mod = _require_approval_policy()

        class NoOpAdapter:
            def decide(
                self,
                *,
                policy,
                user=None,
                agent=None,
                tool=None,
                resource_scope=None,
                action="",
            ):
                return True

        # runtime_checkable Protocol：极薄实现即可满足，无需继承
        assert isinstance(NoOpAdapter(), mod.PolicyAdapter)

    def test_decide_signature_accepts_frozen_policy(self):
        mod = _require_approval_policy()

        class NoOpAdapter:
            def decide(self, **kwargs):
                return kwargs.get("policy") == mod.ApprovalPolicy.NONE

        adapter = NoOpAdapter()
        # 接口消费的 policy 必须是 frozen ApprovalPolicy（string enum）
        assert adapter.decide(policy=mod.ApprovalPolicy.NONE) is True
