"""
tests/ai_native/test_tool_descriptor_contract.py — Inv 13 (Monotonic Taint) + Inv 15 (ToolDescriptor)

RED GATE 测试（Phase E Slice 1）：
    - ai_native/governance/data_classification.py 尚未实现
    - ai_native/runtime/tool_descriptor.py 尚未实现
    - ai_native/runtime/tool_executor.py 尚未实现（pre/post-call 编排）
全部测试预期 FAIL（需求未实现导致的正确失败）。

契约：

Inv 15 — ToolDescriptor 15 字段全量：
    name / version / description / input_schema / output_schema / action /
    side_effect / required_scope / declared_output_classification /
    allowed_input_classification / approval_policy / idempotent /
    timeout_seconds / supported_roles / handler

    ToolRegistry.register(descriptor)：
        - 缺 action / side_effect / required_scope /
          declared_output_classification / allowed_input_classification 任一
          → 拒绝注册（ValueError）
        - approval_policy 仅 {none, always, policy_decides}；
          禁止第二套审批模型（requires_human / auto_approve_when_self）

Inv 13 — DataClassification 四级（小写，严格递增序）：
    public < internal < student_pii < psych_sensitive

    TaintLogic.classify(current, actual) -> effective：
        - 升级允许：public→internal→student_pii→psych_sensitive
        - 降级禁止：保持原级（不得降低）

    pre-call：Tool declared_output_classification > Run current
              → Run 先升级，Provider routing 后发生（provider 收到的 Run 已是升级后）
    post-call：actual > declared → Run 升级 + tool_descriptor_drift incident
    post-call：actual <= declared → Run 不降低
"""

from __future__ import annotations

import importlib

import pytest

TOOL_DESCRIPTOR_FIELDS = [
    "name", "version", "description", "input_schema", "output_schema",
    "action", "side_effect", "required_scope",
    "declared_output_classification", "allowed_input_classification",
    "approval_policy", "idempotent", "timeout_seconds", "supported_roles",
    "handler",
]

REQUIRED_ON_REGISTER = [
    "action", "side_effect", "required_scope",
    "declared_output_classification", "allowed_input_classification",
]

ALLOWED_APPROVAL_POLICIES = {"none", "always", "policy_decides"}

CLASSIFICATION_ORDER = [
    "public", "internal", "student_pii", "psych_sensitive",
]


def _require_classification():
    try:
        return importlib.import_module("ai_native.governance.data_classification")
    except ModuleNotFoundError as exc:  # pragma: no cover - RED 分支
        pytest.fail(
            f"RED: ai_native/governance/data_classification.py 尚未实现（Slice 1 需求未落地）: {exc}"
        )


def _require_tool_descriptor():
    try:
        return importlib.import_module("ai_native.runtime.tool_descriptor")
    except ModuleNotFoundError as exc:  # pragma: no cover - RED 分支
        pytest.fail(
            f"RED: ai_native/runtime/tool_descriptor.py 尚未实现（Slice 1 需求未落地）: {exc}"
        )


def _require_tool_executor():
    try:
        return importlib.import_module("ai_native.runtime.tool_executor")
    except ModuleNotFoundError as exc:  # pragma: no cover - RED 分支
        pytest.fail(
            f"RED: ai_native/runtime/tool_executor.py 尚未实现（Slice 1 需求未落地）: {exc}"
        )


def _full_descriptor():
    return {
        "name": "read_class_grade_summary",
        "version": "0.1.0",
        "description": "班级成绩摘要",
        "input_schema": {"class_id": "int", "exam_id": "int"},
        "output_schema": {"subjects": "list"},
        "action": "read",
        "side_effect": "none",
        "required_scope": "class",
        "declared_output_classification": "student_pii",
        "allowed_input_classification": "student_pii",
        "approval_policy": "none",
        "idempotent": True,
        "timeout_seconds": 60,
        "supported_roles": ["grade_leader", "class_teacher"],
        "handler": object(),
    }


class TestInv15DescriptorFields:
    def test_full_descriptor_registers_successfully(self):
        mod = _require_tool_descriptor()
        registry = mod.ToolRegistry()
        descriptor = mod.ToolDescriptor(**_full_descriptor())
        registry.register(descriptor)
        assert descriptor.name in registry.tool_names()

    def test_descriptor_requires_all_15_fields(self):
        mod = _require_tool_descriptor()
        descriptor = mod.ToolDescriptor(**_full_descriptor())
        missing = [
            field for field in TOOL_DESCRIPTOR_FIELDS
            if not hasattr(descriptor, field)
        ]
        assert missing == []

    def test_missing_action_rejected(self):
        mod = _require_tool_descriptor()
        data = _full_descriptor()
        data.pop("action")
        with pytest.raises(ValueError):
            mod.ToolRegistry().register(mod.ToolDescriptor(**data))

    def test_missing_side_effect_rejected(self):
        mod = _require_tool_descriptor()
        data = _full_descriptor()
        data.pop("side_effect")
        with pytest.raises(ValueError):
            mod.ToolRegistry().register(mod.ToolDescriptor(**data))

    def test_missing_required_scope_rejected(self):
        mod = _require_tool_descriptor()
        data = _full_descriptor()
        data.pop("required_scope")
        with pytest.raises(ValueError):
            mod.ToolRegistry().register(mod.ToolDescriptor(**data))

    def test_missing_declared_output_classification_rejected(self):
        mod = _require_tool_descriptor()
        data = _full_descriptor()
        data.pop("declared_output_classification")
        with pytest.raises(ValueError):
            mod.ToolRegistry().register(mod.ToolDescriptor(**data))

    def test_missing_allowed_input_classification_rejected(self):
        mod = _require_tool_descriptor()
        data = _full_descriptor()
        data.pop("allowed_input_classification")
        with pytest.raises(ValueError):
            mod.ToolRegistry().register(mod.ToolDescriptor(**data))


class TestInv15ApprovalPolicyWhitelist:
    def test_allowed_policies_registered(self):
        mod = _require_tool_descriptor()
        for policy in sorted(ALLOWED_APPROVAL_POLICIES):
            data = _full_descriptor()
            data["approval_policy"] = policy
            mod.ToolRegistry().register(mod.ToolDescriptor(**data))  # 不应抛

    def test_second_approval_model_forbidden(self):
        mod = _require_tool_descriptor()
        for bad_policy in ("requires_human", "auto_approve_when_self"):
            data = _full_descriptor()
            data["approval_policy"] = bad_policy
            with pytest.raises(ValueError):
                mod.ToolRegistry().register(mod.ToolDescriptor(**data))


class TestInv13MonotonicTaint:
    def _dc(self, mod):
        return mod.DataClassification

    def test_upgrade_public_to_internal_allowed(self):
        mod = _require_classification()
        dc = self._dc(mod)
        assert mod.TaintLogic.classify(dc.public, dc.internal) == dc.internal

    def test_upgrade_internal_to_student_pii_allowed(self):
        mod = _require_classification()
        dc = self._dc(mod)
        assert mod.TaintLogic.classify(dc.internal, dc.student_pii) == dc.student_pii

    def test_upgrade_student_pii_to_psych_sensitive_allowed(self):
        mod = _require_classification()
        dc = self._dc(mod)
        assert mod.TaintLogic.classify(dc.student_pii, dc.psych_sensitive) == dc.psych_sensitive

    def test_downgrade_psych_sensitive_to_student_pii_forbidden(self):
        mod = _require_classification()
        dc = self._dc(mod)
        # 保持不变，不得降级
        assert mod.TaintLogic.classify(dc.psych_sensitive, dc.student_pii) == dc.psych_sensitive

    def test_downgrade_student_pii_to_internal_forbidden(self):
        mod = _require_classification()
        dc = self._dc(mod)
        assert mod.TaintLogic.classify(dc.student_pii, dc.internal) == dc.student_pii

    def test_downgrade_internal_to_public_forbidden(self):
        mod = _require_classification()
        dc = self._dc(mod)
        assert mod.TaintLogic.classify(dc.internal, dc.public) == dc.internal

    def test_classification_order_is_fixed(self):
        mod = _require_classification()
        dc = self._dc(mod)
        values = [dc.public, dc.internal, dc.student_pii, dc.psych_sensitive]
        assert [v.value for v in values] == CLASSIFICATION_ORDER

    def test_enum_is_string_enum(self):
        mod = _require_classification()
        dc = self._dc(mod)
        # str, Enum：Runtime 可安全 `model.data_classification = dc.internal`
        assert isinstance(dc.internal, str)
        assert dc.internal == "internal"
        assert dc.public == "public"
        assert dc.student_pii == "student_pii"
        assert dc.psych_sensitive == "psych_sensitive"


class TestInv13PrePostCallOrdering:
    def test_precall_declared_upgrade_happens_before_provider_routing(self):
        exec_mod = _require_tool_executor()
        classif_mod = _require_classification()
        dc = classif_mod.DataClassification

        calls = []
        executor = exec_mod.ToolExecutor()

        def fake_provider(run, **_kwargs):
            # provider 看到的 Run 必须已是升级后的 classification
            calls.append(run["data_classification"])

        run = {"status": "ACTIVE", "data_classification": dc.internal}
        descriptor = {
            "declared_output_classification": dc.student_pii,
            "action": "read",
            "handler": _noop_handler,
        }
        executor.execute(run=run, descriptor=descriptor, provider=fake_provider)
        # Run 先升级到 declared，再 routing → provider 收到 student_pii
        assert calls == [dc.student_pii]
        assert run["data_classification"] == dc.student_pii

    def test_postcall_actual_higher_upgrades_run_and_creates_drift_incident(self):
        exec_mod = _require_tool_executor()
        classif_mod = _require_classification()
        dc = classif_mod.DataClassification

        incidents = []
        executor = exec_mod.ToolExecutor()

        def fake_handler(**_kwargs):
            return {"actual_classification": dc.psych_sensitive, "output": {}}

        run = {"status": "ACTIVE", "data_classification": dc.internal}
        descriptor = {
            "declared_output_classification": dc.internal,
            "action": "read",
            "handler": fake_handler,
        }
        executor.execute(
            run=run,
            descriptor=descriptor,
            incident_sink=incidents.append,
        )
        # actual > declared → Run 升级 + tool_descriptor_drift incident
        assert run["data_classification"] == dc.psych_sensitive
        assert any(
            isinstance(item, dict) and item.get("type") == "tool_descriptor_drift"
            for item in incidents
        )

    def test_postcall_actual_leq_declared_no_downgrade(self):
        exec_mod = _require_tool_executor()
        classif_mod = _require_classification()
        dc = classif_mod.DataClassification

        executor = exec_mod.ToolExecutor()

        def fake_handler(**_kwargs):
            return {"actual_classification": dc.internal, "output": {}}

        run = {"status": "ACTIVE", "data_classification": dc.student_pii}
        descriptor = {
            "declared_output_classification": dc.student_pii,
            "action": "read",
            "handler": fake_handler,
        }
        executor.execute(run=run, descriptor=descriptor)
        # actual <= declared → Run 不降低
        assert run["data_classification"] == dc.student_pii


def _noop_handler(**_kwargs):
    return {"output": {}}
