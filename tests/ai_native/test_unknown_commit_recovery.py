"""
tests/ai_native/test_unknown_commit_recovery.py — Inv 8: UNKNOWN_COMMIT ≠ retry

RED GATE 测试（Phase E Slice 1）：组件 `ai_native.runtime.tool_executor` 尚未实现，
全部测试预期 FAIL（需求未实现导致的正确失败）。

契约（未来实现必须满足）：
    ToolExecutor.reconcile(run, tool_call, confirmation, handler)

    - tool_call.status == UNKNOWN_COMMIT 时，绝不自动 retry：
      * retry_count 不得 +1
      * 不得重新调用 tool handler
    - confirmation 语义：
      * {"executed": True}   → tool_call.status → EXECUTED
      * {"executed": False}  → 允许重新执行（handler 可再次被调用）
      * None（仍未知）      → run.status 保持 RECOVERING，走人工/恢复路径
    - 禁止只断言枚举值存在：必须证明行为（handler 调用次数 / 状态迁移 / retry_count）。

    测试使用 dict 形态的 run/tool_call 与注入的 fake handler（记录调用次数），
    不依赖数据库。
"""

from __future__ import annotations

import importlib

import pytest


def _require_tool_executor():
    try:
        return importlib.import_module("ai_native.runtime.tool_executor")
    except ModuleNotFoundError as exc:  # pragma: no cover - RED 分支
        pytest.fail(
            f"RED: ai_native/runtime/tool_executor.py 尚未实现（Slice 1 需求未落地）: {exc}"
        )


def _run(status="RECOVERING", retry_count=0):
    return {"status": status, "retry_count": retry_count}


def _tool_call(status="UNKNOWN_COMMIT", retry_count=0):
    return {"status": status, "retry_count": retry_count}


def _noop_handler(**kwargs):
    return None


class TestInv8UnknownCommitNotRetry:
    def test_unknown_commit_does_not_reinvoke_handler(self):
        mod = _require_tool_executor()
        executor = mod.ToolExecutor()
        calls = {"n": 0}

        def handler(**kwargs):  # noqa: ARG001
            calls["n"] += 1

        run = _run()
        tc = _tool_call()
        executor.reconcile(
            run=run, tool_call=tc, confirmation=None, handler=handler
        )
        # UNKNOWN_COMMIT 后 executor 不再次调用 Tool handler
        assert calls["n"] == 0

    def test_retry_count_not_incremented_on_unknown_commit(self):
        mod = _require_tool_executor()
        executor = mod.ToolExecutor()
        run = _run(retry_count=0)
        tc = _tool_call(retry_count=0)
        executor.reconcile(
            run=run, tool_call=tc, confirmation=None, handler=_noop_handler
        )
        # retry_count 不得因为 UNKNOWN_COMMIT 自动 +1 并重发
        assert tc["retry_count"] == 0
        assert run["retry_count"] == 0

    def test_still_unknown_keeps_recovering(self):
        mod = _require_tool_executor()
        executor = mod.ToolExecutor()
        run = _run(status="ACTIVE")
        tc = _tool_call()
        executor.reconcile(
            run=run, tool_call=tc, confirmation=None, handler=_noop_handler
        )
        # 仍未知 → 保持恢复/人工处理路径，run 进入 RECOVERING
        assert run["status"] == "RECOVERING"


class TestInv8ConfirmedRecovery:
    def test_confirmed_executed_transitions_to_executed(self):
        mod = _require_tool_executor()
        executor = mod.ToolExecutor()
        run = _run()
        tc = _tool_call()
        executor.reconcile(
            run=run,
            tool_call=tc,
            confirmation={"executed": True},
            handler=_noop_handler,
        )
        # confirmed executed → EXECUTED
        assert tc["status"] == "EXECUTED"

    def test_confirmed_not_executed_allows_reexecution(self):
        mod = _require_tool_executor()
        executor = mod.ToolExecutor()
        calls = {"n": 0}

        def handler(**kwargs):  # noqa: ARG001
            calls["n"] += 1

        run = _run()
        tc = _tool_call()
        executor.reconcile(
            run=run,
            tool_call=tc,
            confirmation={"executed": False},
            handler=handler,
        )
        # confirmed not executed → 才允许重新执行（handler 被重新调用一次）
        assert calls["n"] == 1
