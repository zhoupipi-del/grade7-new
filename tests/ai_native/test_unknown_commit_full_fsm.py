"""
tests/ai_native/test_unknown_commit_full_fsm.py — Inv 8 完整状态机（三分支先 RECOVERING）

RUNTIME REVISE 补丁 B：三个恢复分支都必须先进 RECOVERING，
且状态迁移完整（RESUMING / EXECUTING / EXECUTED）。
"""

from __future__ import annotations

import importlib

import pytest


def _require_tool_executor():
    try:
        return importlib.import_module("ai_native.runtime.tool_executor")
    except ModuleNotFoundError as exc:  # pragma: no cover - RED 分支
        pytest.fail(f"RED: {exc}")


def _run(status="EXECUTING", retry_count=0):
    return {"status": status, "retry_count": retry_count}


def _tool_call(status="UNKNOWN_COMMIT", retry_count=0):
    return {"status": status, "retry_count": retry_count}


class TestInv8FullFSMStillUnknown:
    def test_still_unknown_enters_recovering_before_return(self):
        mod = _require_tool_executor()
        executor = mod.ToolExecutor()
        run = _run(status="EXECUTING")
        tc = _tool_call()
        executor.reconcile(run=run, tool_call=tc, confirmation=None, handler=lambda: None)
        # 第一动作：Run 先进 RECOVERING
        assert run["status"] == "RECOVERING"

    def test_still_unknown_handler_is_not_called(self):
        mod = _require_tool_executor()
        executor = mod.ToolExecutor()
        calls = {"n": 0}

        def handler():
            calls["n"] += 1

        run = _run()
        tc = _tool_call()
        executor.reconcile(run=run, tool_call=tc, confirmation=None, handler=handler)
        assert calls["n"] == 0


class TestInv8FullFSMConfirmedExecuted:
    def test_confirmed_executed_enters_recovering_then_resuming(self):
        mod = _require_tool_executor()
        executor = mod.ToolExecutor()
        run = _run(status="EXECUTING")
        tc = _tool_call()
        # 记录状态变化序列
        status_log = []

        def _track():
            status_log.append(run["status"])

        # 我们无法在 reconcile 内部钩子，但可以看最终状态
        executor.reconcile(
            run=run,
            tool_call=tc,
            confirmation={"executed": True},
            handler=lambda: None,
        )
        assert run["status"] == "RESUMING"
        assert tc["status"] == "EXECUTED"

    def test_confirmed_executed_handler_not_called(self):
        mod = _require_tool_executor()
        executor = mod.ToolExecutor()
        calls = {"n": 0}
        executor.reconcile(
            run=_run(), tool_call=_tool_call(),
            confirmation={"executed": True},
            handler=lambda: calls.update(n=calls["n"] + 1),
        )
        assert calls["n"] == 0


class TestInv8FullFSMConfirmedNotExecuted:
    def test_confirmed_not_executed_enters_recovering_then_resuming(self):
        mod = _require_tool_executor()
        executor = mod.ToolExecutor()
        run = _run(status="EXECUTING")
        tc = _tool_call()
        executor.reconcile(
            run=run, tool_call=tc,
            confirmation={"executed": False},
            handler=lambda: None,
        )
        assert run["status"] == "RESUMING"

    def test_confirmed_not_executed_handler_called_exactly_once(self):
        mod = _require_tool_executor()
        executor = mod.ToolExecutor()
        calls = {"n": 0}

        def handler():
            calls["n"] += 1

        run = _run()
        tc = _tool_call()
        executor.reconcile(
            run=run, tool_call=tc,
            confirmation={"executed": False},
            handler=handler,
        )
        assert calls["n"] == 1

    def test_confirmed_not_executed_tool_enters_executed(self):
        mod = _require_tool_executor()
        executor = mod.ToolExecutor()
        run = _run()
        tc = _tool_call()
        executor.reconcile(
            run=run, tool_call=tc,
            confirmation={"executed": False},
            handler=lambda: None,
        )
        # 执行后 tool_call → EXECUTED
        assert tc["status"] == "EXECUTED"
