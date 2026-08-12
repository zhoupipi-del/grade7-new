"""
ai_native.runtime.agent_run — AgentRun 持久化闭环（Slice 1）
============================================================

Slice 1 最小闭环。run lifecycle += ai_runs + ai_runs_status_events + ai_execution_snapshots。

生产 session 模型 = AsyncSession（core/routers.py `get_db() -> AsyncSession`）。
本模块与生产对齐：所有 DB 操作为 async。

列映射对齐 ai_native/models 实际 schema（20260811_1810 frozen）：
    a·runs: school_id / user_id / run_uuid / role_profile / input_summary / copilot_profile /
            status / data_classification / data_classification_peak / started_at
    status_events: school_id / run_id / from_status / to_status / trigger_reason / payload
    snapshots: school_id / run_id / classification_peak / scope_snapshot

★ 不硬用 ai_approvals / ai_command_envelopes。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

RUN_STATUS_PLANNING = "PLANNING"
RUN_STATUS_POLICY_CHECK = "POLICY_CHECK"
RUN_STATUS_EXECUTING = "EXECUTING"
RUN_STATUS_WAITING_APPROVAL = "WAITING_APPROVAL"
RUN_STATUS_RECOVERING = "RECOVERING"
RUN_STATUS_RESUMING = "RESUMING"
RUN_STATUS_COMPLETED = "COMPLETED"
RUN_STATUS_FAILED = "FAILED"

RUN_STATUSES = (
    RUN_STATUS_PLANNING, RUN_STATUS_POLICY_CHECK, RUN_STATUS_EXECUTING,
    RUN_STATUS_WAITING_APPROVAL, RUN_STATUS_RECOVERING, RUN_STATUS_RESUMING,
    RUN_STATUS_COMPLETED, RUN_STATUS_FAILED,
)


class AgentRun:
    """Run 生命周期（async Session；写入 ai_runs + status_events + snapshots）。"""

    def __init__(
        self, *, school_id: int, user_id: int,
        tool_name: str = "", role: str = "teacher", session: Any = None,
    ) -> None:
        self.school_id = school_id
        self.user_id = user_id
        self.tool_name = tool_name
        self.role = role
        self.session = session
        self.run_id: Optional[int] = None
        self.run_uuid: str = str(uuid4())
        self.status: str = RUN_STATUS_PLANNING
        self.data_classification: Optional[str] = "internal"

    async def start(self, session=None) -> int:
        db = session or self.session
        from ai_native.models.ai_runs import AiRuns
        from ai_native.models.ai_runs_status_events import AiRunsStatusEvents

        run = AiRuns(school_id=self.school_id, user_id=self.user_id,
                     run_uuid=self.run_uuid, role_profile=self.role,
                     input_summary=self.tool_name, status=self.status,
                     data_classification=self.data_classification,
                     copilot_profile=self.tool_name,
                     started_at=datetime.now())
        db.add(run)
        await db.flush()
        self.run_id = run.id

        event = AiRunsStatusEvents(school_id=self.school_id, run_id=run.id,
                                   from_status=None, to_status=self.status,
                                   trigger_reason=f"tool={self.tool_name}")
        db.add(event)
        await db.flush()
        return run.id

    async def transition(self, to_status: str, session=None) -> None:
        if to_status not in RUN_STATUSES:
            raise ValueError(f"非法 Run 状态: {to_status!r}")
        db = session or self.session
        from ai_native.models.ai_runs import AiRuns
        from ai_native.models.ai_runs_status_events import AiRunsStatusEvents

        if self.run_id is None:
            raise RuntimeError("AgentRun 未 start 前不可 transition")
        prev = self.status
        self.status = to_status

        run = await db.get(AiRuns, self.run_id)
        if run:
            run.status = to_status
            await db.flush()

        event = AiRunsStatusEvents(school_id=self.school_id, run_id=self.run_id,
                                   from_status=prev, to_status=to_status,
                                   trigger_reason=f"tool={self.tool_name}")
        db.add(event)
        await db.flush()

    async def finish(self, *, snapshot: Dict[str, Any], session=None) -> None:
        db = session or self.session
        from ai_native.models.ai_execution_snapshots import AiExecutionSnapshots

        await self.transition(RUN_STATUS_COMPLETED, session=db)

        snap = AiExecutionSnapshots(school_id=self.school_id, run_id=self.run_id,
                                    classification_peak=self.data_classification,
                                    scope_snapshot=snapshot,
                                    snapshot_hash="placeholder",
                                    argument_hashes={})
        db.add(snap)
        await db.flush()
