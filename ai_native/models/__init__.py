"""
ai_native.models — SQLAlchemy ORM for the 9 canonical AI Native tables
======================================================================

v3.2 FINAL frozen schema — see quantum-nebula-b1-preflight.md for the full
column-level mapping and the 27 Invariants.

Tables registered here:
    1.  ai_runs                       (Run 主表)
    2.  ai_runs_status_events         (Run 状态机 8 态事件流)
    3.  ai_tool_calls                 (Tool 调用记录；提前建供子表 FK 引用)
    4.  ai_model_calls                (LLM 调用明细)
    5.  ai_retrievals                 (RAG 检索链路)
    6.  ai_approvals                  (审批记录)
    7.  ai_incidents                  (失败分类)
    8.  ai_command_envelopes          (可执行命令包 AES-256-GCM)
    9.  ai_execution_snapshots        (审计证据快照，1:1 on run_id)

Global invariants enforced at the schema layer:
    - All 9 tables carry `school_id BIGINT NOT NULL` (Inv 1, 22)
    - All ID / FK columns = BIGINT signed (matches School.id / User.id)
    - All composite tenant FKs are (school_id, …) ON DELETE RESTRICT (Inv 19, 24)
    - 4 named UNIQUE: uq_run_school / uq_toolcall_school / uq_model_call_seq /
      uq_school_idempotency
    - 3 inline UNIQUE: ai_runs.run_uuid / ai_command_envelopes.envelope_uuid /
      ai_execution_snapshots.run_id (1:1)
    - schools / users are NOT referenced by physical FK (logical reference only,
      §0-E of B1 preflight)
    - All string columns inherit table-level
      `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`
"""

from ai_native.models.ai_runs import AiRuns
from ai_native.models.ai_runs_status_events import AiRunsStatusEvents
from ai_native.models.ai_tool_calls import AiToolCalls
from ai_native.models.ai_model_calls import AiModelCalls
from ai_native.models.ai_retrievals import AiRetrievals
from ai_native.models.ai_approvals import AiApprovals
from ai_native.models.ai_incidents import AiIncidents
from ai_native.models.ai_command_envelopes import AiCommandEnvelopes
from ai_native.models.ai_execution_snapshots import AiExecutionSnapshots

__all__ = [
    "AiRuns",
    "AiRunsStatusEvents",
    "AiToolCalls",
    "AiModelCalls",
    "AiRetrievals",
    "AiApprovals",
    "AiIncidents",
    "AiCommandEnvelopes",
    "AiExecutionSnapshots",
]