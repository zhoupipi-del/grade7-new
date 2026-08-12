"""
tests/ai_native/test_descriptor_to_executor.py — Inv 13/15 组件串联

RUNTIME REVISE 补丁 D：ToolRegistry.get() 返回 ToolDescriptor 对象
→ 直接交给 ToolExecutor.execute() → 不做 dict 转换也能正常执行。

证明 Runtime 主链是通的：Registry → ToolDescriptor → ToolExecutor
"""

from __future__ import annotations

import importlib

import pytest


def _require_modules():
    td = importlib.import_module("ai_native.runtime.tool_descriptor")
    te = importlib.import_module("ai_native.runtime.tool_executor")
    return td, te


class TestDescriptorToExecutorDirect:
    def test_registry_get_returns_tool_descriptor(self):
        td, _te = _require_modules()
        registry = td.ToolRegistry()
        descriptor = td.ToolDescriptor(
            name="test_tool", version="1.0", description="x",
            input_schema={}, output_schema={},
            action="read", side_effect="none", required_scope="class",
            declared_output_classification="internal",
            allowed_input_classification="internal",
            approval_policy="none", idempotent=True,
            timeout_seconds=10, supported_roles=["grade_leader"],
            handler=object(),
        )
        registry.register(descriptor)
        fetched = registry.get("test_tool")
        assert isinstance(fetched, td.ToolDescriptor)

    def test_executor_execute_with_descriptor_object_not_dict(self):
        td, te = _require_modules()
        classification = importlib.import_module(
            "ai_native.governance.data_classification"
        )
        dc = classification.DataClassification

        calls = {"handler": 0}

        def handler(run=None, **_kwargs):
            calls["handler"] += 1
            return {"actual_classification": dc.student_pii, "output": {}}

        descriptor = td.ToolDescriptor(
            name="direct_test", version="1.0", description="",
            input_schema={}, output_schema={},
            action="read", side_effect="none", required_scope="class",
            declared_output_classification=dc.internal,
            allowed_input_classification=dc.internal,
            approval_policy="none", idempotent=True,
            timeout_seconds=10, supported_roles=["grade_leader"],
            handler=handler,
        )

        executor = te.ToolExecutor()
        incidents = []

        run = {"status": "EXECUTING", "data_classification": dc.internal}
        result = executor.execute(
            run=run,
            descriptor=descriptor,  # ← ToolDescriptor 对象，非 dict
            incident_sink=incidents.append,
        )
        assert calls["handler"] == 1
        assert run["data_classification"] == dc.student_pii
        # drift: actual (student_pii) > declared (internal)
        assert any(
            i["type"] == "tool_descriptor_drift" for i in incidents
        )
