"""
ai_native.runtime.agent_run — AgentRun 持久化闭环（Slice 1，v2 修复版）
======================================================================

Slice 1 最小闭环。run lifecycle += ai_runs + ai_runs_status_events + ai_execution_snapshots。

v2 修复（FT-014）：
  - terminal states 写 completed_at（UTC），非 terminal 保持 NULL
  - run 创建时生成一次 trace_id（复用 core.trace_id contextvar，否则生成 12 位 hex），一路传播
  - query_hash 用 keyed HMAC-SHA256(server_secret, normalized_query)，非可逆普通 hash
  - query_redacted 存脱敏摘要（数字泛化），不存原始 query
  - snapshot_hash 用 canonical JSON（sort_keys + 稳定分隔符 + UTF-8）→ SHA-256，彻底移除 placeholder

生产 session 模型 = AsyncSession（core/routers.py `get_db() -> AsyncSession`）。
★ 不硬用 ai_approvals / ai_command_envelopes。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
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
RUN_STATUS_CANCELLED = "CANCELLED"
RUN_STATUS_TIMED_OUT = "TIMED_OUT"
RUN_STATUS_ABORTED = "ABORTED"

RUN_STATUSES = (
    RUN_STATUS_PLANNING, RUN_STATUS_POLICY_CHECK, RUN_STATUS_EXECUTING,
    RUN_STATUS_WAITING_APPROVAL, RUN_STATUS_RECOVERING, RUN_STATUS_RESUMING,
    RUN_STATUS_COMPLETED, RUN_STATUS_FAILED,
    RUN_STATUS_CANCELLED, RUN_STATUS_TIMED_OUT, RUN_STATUS_ABORTED,
)

# terminal states：进入即写 completed_at（UTC）
TERMINAL_STATES = {
    RUN_STATUS_COMPLETED, RUN_STATUS_FAILED,
    RUN_STATUS_CANCELLED, RUN_STATUS_TIMED_OUT, RUN_STATUS_ABORTED,
}


def _utcnow() -> datetime:
    """naive UTC now（与 created_at 的 SQLAlchemy utcnow 默认一致）。"""
    return datetime.utcnow()


def _resolve_trace_id() -> str:
    """复用 core.trace_id 的请求级 contextvar；非 HTTP 上下文则生成 12 位 hex。"""
    try:
        from core.trace_id import trace_id_ctx
        t = trace_id_ctx.get()
        if t and t != "-":
            return t
    except Exception:
        pass
    return uuid4().hex[:12]


def _keyed_query_hash(query: str) -> Optional[str]:
    """keyed HMAC-SHA256(server_secret, normalized_query)。防字典猜测，非可逆普通 hash。"""
    if not query:
        return None
    secret = os.environ.get("SECRET_KEY") or os.environ.get("JWT_SECRET_KEY") or ""
    normalized = " ".join(query.strip().split())
    return hmac.new(secret.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def _redact_query(query: str, max_len: int = 200) -> Optional[str]:
    """脱敏摘要：数字泛化为 [n]（学号/班级号），截断。不存原始 query。"""
    if not query:
        return None
    normalized = " ".join(query.strip().split())
    redacted = re.sub(r"\d+", "[n]", normalized)
    if len(redacted) > max_len:
        redacted = redacted[:max_len] + "..."
    return redacted


def _canonical_hash(obj: Any) -> str:
    """canonical JSON（sort_keys + 稳定分隔符 + UTF-8）→ SHA-256。"""
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AgentRun:
    """Run 生命周期（async Session；写入 ai_runs + status_events + snapshots）。"""

    def __init__(
        self, *, school_id: int, user_id: int,
        tool_name: str = "", role: str = "teacher", session: Any = None,
        query: str = "",
    ) -> None:
        self.school_id = school_id
        self.user_id = user_id
        self.tool_name = tool_name
        self.role = role
        self.session = session
        self.query = query
        self.run_id: Optional[int] = None
        self.run_uuid: str = str(uuid4())
        self.trace_id: str = _resolve_trace_id()  # 生成一次，一路传播
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
                     trace_id=self.trace_id,
                     query_hash=_keyed_query_hash(self.query),
                     query_redacted=_redact_query(self.query),
                     started_at=_utcnow())
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
            if to_status in TERMINAL_STATES:
                run.completed_at = _utcnow()
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
                                    snapshot_hash=_canonical_hash(snapshot),
                                    argument_hashes={})
        db.add(snap)
        await db.flush()
