"""
tests/ai_native/test_drift_independent_of_peak.py — Inv 13 drift 独立判断

RUNTIME REVISE 补丁 C：tool_descriptor_drift 判定 = actual > declared，
与 Run 当前 peak 无关。两个独立判断：
    - Run taint：取峰值 max(run_current, actual)
    - drift：actual > declared → incident

关键场景：Run peak=psych_sensitive, declared=internal, actual=student_pii
    → Run 保持 psych_sensitive（不降）
    → drift 必须产生（actual=student_pii > declared=internal）
"""

from __future__ import annotations

import importlib

import pytest


def _require_tool_executor():
    try:
        return importlib.import_module("ai_native.runtime.tool_executor")
    except ModuleNotFoundError as exc:  # pragma: no cover - RED 分支
        pytest.fail(f"RED: {exc}")


def _require_classification():
    try:
        return importlib.import_module("ai_native.governance.data_classification")
    except ModuleNotFoundError as exc:
        pytest.fail(f"RED: {exc}")


class TestDriftIndependentOfRunPeak:
    def _dc_vals(self):
        mod = _require_classification()
        return mod.DataClassification

    def test_peak_above_actual_above_declared_produces_drift(self):
        """Run peak=psych_sensitive, declared=internal, actual=student_pii → drift。"""
        exec_mod = _require_tool_executor()
        dc = self._dc_vals()

        incidents = []
        executor = exec_mod.ToolExecutor()

        def fake_handler(**_kwargs):
            return {"actual_classification": dc.student_pii, "output": {}}

        run = {
            "status": "EXECUTING",
            "data_classification": dc.psych_sensitive,  # Run peak 已最高
        }
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
        # Run taint：保持峰值，不降
        assert run["data_classification"] == dc.psych_sensitive
        # Descriptor drift：actual (student_pii) > declared (internal) → drift
        assert any(
            item["type"] == "tool_descriptor_drift"
            and item["declared"] == dc.internal
            and item["actual"] == dc.student_pii
            for item in incidents
        )

    def test_peak_equal_actual_equal_declared_no_drift(self):
        """all=internal → 无 drift。"""
        exec_mod = _require_tool_executor()
        dc = self._dc_vals()

        incidents = []
        executor = exec_mod.ToolExecutor()

        def fake_handler(**_kwargs):
            return {"actual_classification": dc.internal, "output": {}}

        run = {"status": "EXECUTING", "data_classification": dc.internal}
        descriptor = {
            "declared_output_classification": dc.internal,
            "action": "read",
            "handler": fake_handler,
        }
        executor.execute(
            run=run, descriptor=descriptor, incident_sink=incidents.append,
        )
        assert run["data_classification"] == dc.internal
        assert not any(
            item["type"] == "tool_descriptor_drift" for item in incidents
        )

    def test_actual_below_declared_no_drift_run_not_downgraded(self):
        """actual < declared → Run 不降，不产生 drift。"""
        exec_mod = _require_tool_executor()
        dc = self._dc_vals()

        incidents = []
        executor = exec_mod.ToolExecutor()

        def fake_handler(**_kwargs):
            return {"actual_classification": dc.internal, "output": {}}

        run = {"status": "EXECUTING", "data_classification": dc.student_pii}
        descriptor = {
            "declared_output_classification": dc.student_pii,
            "action": "read",
            "handler": fake_handler,
        }
        executor.execute(
            run=run, descriptor=descriptor, incident_sink=incidents.append,
        )
        assert run["data_classification"] == dc.student_pii  # 不降
        assert not any(
            item["type"] == "tool_descriptor_drift" for item in incidents
        )
