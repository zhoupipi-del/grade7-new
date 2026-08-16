"""
modules.ai_teacher_assistant.tools.write_test_marker — FT-015 审批验证专用写工具
================================================================================

无害测试 Tool：向隔离测试表 ai_approval_test_markers 写入一条 marker 记录。
绝不触碰任何真实学生/业务数据。

approval_policy = always（WRITE/SIDE_EFFECT → APPROVAL_REQUIRED）
ToolExecutor 强制执行点会校验 APPROVED approval + args hash 匹配后才允许执行。
"""

from __future__ import annotations

from typing import Any, Dict

TOOL_NAME = "write_test_marker"


def build_write_test_marker_descriptor() -> Any:
    """构造 ToolDescriptor（approval_policy=always，side_effect=write）。"""
    from ai_native.runtime.tool_descriptor import ToolDescriptor

    return ToolDescriptor(
        name=TOOL_NAME,
        version="0.1.0",
        description="写入一条隔离测试标记（仅 FT-015 审批验证用，不碰真实数据）",
        input_schema={"marker": "str", "value": "str"},
        output_schema={"written": "bool", "marker": "str", "value": "str"},
        action="write",
        side_effect="write",
        required_scope="school",
        declared_output_classification="internal",
        allowed_input_classification="internal",
        approval_policy="always",
        idempotent=False,
        timeout_seconds=10,
        supported_roles=["grade_leader", "ms_admin"],
        handler=write_test_marker_handler,
    )


async def write_test_marker_handler(run: Dict[str, Any] = None, **_: Any) -> Dict[str, Any]:
    """写隔离测试表 ai_approval_test_markers。

    run 需含: session(AsyncSession), approval_args(marker/value), run_id, school_id
    """
    if not run:
        raise RuntimeError("write_test_marker: run 上下文缺失")
    session = run.get("session")
    marker = (run.get("approval_args") or {}).get("marker")
    value = (run.get("approval_args") or {}).get("value")
    if session is None:
        raise RuntimeError("write_test_marker: session 缺失")
    if marker is None or value is None:
        raise RuntimeError("write_test_marker: marker/value 缺失")

    from sqlalchemy import text
    await session.execute(
        text(
            "INSERT INTO ai_approval_test_markers "
            "(run_id, school_id, marker, value, created_at) "
            "VALUES (:run_id, :school_id, :marker, :value, UTC_TIMESTAMP())"
        ).bindparams(
            run_id=run.get("run_id"), school_id=run.get("school_id"),
            marker=marker, value=value,
        )
    )
    await session.commit()
    return {"written": True, "marker": marker, "value": value}
