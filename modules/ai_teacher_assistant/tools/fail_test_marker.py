# -*- coding: utf-8 -*-
"""
modules.ai_teacher_assistant.tools.fail_test_marker — FT-016 受控失败测试工具
================================================================================

FT-016 目标：验证 Agent 失败后能否留下可信、可关联、可恢复的 failure evidence。

本工具 = 可控、安全、无业务副作用的失败注入点：
  - 不碰任何真实学生/业务数据（只读自己的 attempt 计数）
  - fail_until=N：该 run 内前 N 次调用抛受控异常（ControlledToolFailure），
    第 N+1 次起成功 —— 用于 FT-016B 可恢复失败（attempt1 FAIL → attempt2 PASS）
  - fail_until=0：永不失败（fallback step 用）
  - 9999：永远失败（FT-016A/C 用）
  - recoverable=True：失败后 run 进 RECOVERING（agent_service 处理）

approval_policy=none / action=read / side_effect=none：FT-016 测 failure 证据链，
不测 approval（FT-015 已覆盖），避免无谓的审批交互。
test-only：AI_FAILURE_TEST_TOOL=1 时才注册（生产默认不暴露）。
"""
from __future__ import annotations

from typing import Any, Dict


class ControlledToolFailure(Exception):
    """受控工具失败（FT-016 test-only）。

    message 即 incident summary（脱敏）；detail 供 detail_hash。
    """

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or message


TOOL_NAME = "fail_test_marker"


def build_fail_test_marker_descriptor() -> Any:
    """构造 ToolDescriptor（受控失败测试工具）。"""
    from ai_native.runtime.tool_descriptor import ToolDescriptor

    return ToolDescriptor(
        name=TOOL_NAME,
        version="0.1.0",
        description="FT-016 受控失败测试工具（按 fail_until 抛异常；不碰真实数据）",
        input_schema={
            "marker": "str",
            "fail_until": "int",
            "recoverable": "bool",
        },
        output_schema={"ok": "bool", "attempt": "int", "marker": "str"},
        action="read",
        side_effect="none",
        required_scope="school",
        declared_output_classification="internal",
        allowed_input_classification="internal",
        approval_policy="none",
        idempotent=False,
        timeout_seconds=10,
        supported_roles=["grade_leader", "ms_admin"],
        handler=fail_test_marker_handler,
    )


async def fail_test_marker_handler(run: Dict[str, Any] = None, **_: Any) -> Dict[str, Any]:
    """受控失败：统计本 run 内本 tool 的 FAILED 次数，< fail_until 则抛异常。

    run 需含: session(AsyncSession), run_id, args
    """
    if not run:
        raise RuntimeError("fail_test_marker: run 上下文缺失")
    session = run.get("session")
    if session is None:
        raise RuntimeError("fail_test_marker: session 缺失")
    run_id = run.get("run_id")
    args = run.get("args") or {}

    from ai_native.models.ai_tool_calls import AiToolCalls
    from sqlalchemy import func, select

    fail_until = int(args.get("fail_until", 1))
    marker = args.get("marker", "ft016")

    # 统计本 run 内该 tool 已 FAILED 的次数（第几次 attempt）
    failed_cnt = (await session.execute(
        select(func.count(AiToolCalls.id)).where(
            AiToolCalls.run_id == run_id,
            AiToolCalls.tool_name == TOOL_NAME,
            AiToolCalls.status == "FAILED",
        )
    )).scalar() or 0
    attempt = failed_cnt + 1

    if failed_cnt < fail_until:
        raise ControlledToolFailure(
            f"fail_test_marker 受控失败 (marker={marker}, attempt={attempt}, fail_until={fail_until})",
            detail=f"marker={marker};attempt={attempt};fail_until={fail_until};tool={TOOL_NAME}",
        )

    return {"ok": True, "attempt": attempt, "marker": marker}
