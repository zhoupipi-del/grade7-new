"""b1_ai_native_9tables

WINGS AI Native 2.1 — Phase B1 Schema Implementation
引入 canonical v3.2 FINAL 锁定的 9 张表（ai_native 包）：

  1. ai_runs                       (Run 主表，状态机 8 态)
  2. ai_runs_status_events         (Run 状态机事件流)
  3. ai_tool_calls                 (Tool 调用记录，状态机 7 态含 UNKNOWN_COMMIT)
  4. ai_model_calls                (LLM 调用明细，UNIQUE call_seq)
  5. ai_retrievals                 (RAG 检索链路，不存 query/chunk 原文)
  6. ai_approvals                  (审批记录，绑定 tool_call)
  7. ai_incidents                  (失败分类)
  8. ai_command_envelopes          (AES-256-GCM 加密命令包)
  9. ai_execution_snapshots        (审计证据快照，1:1 on run_id)

v3.2 FINAL frozen schema requirements:
  • 全部 ID/FK = BIGINT signed
  • 全部 string 列 → utf8mb4_unicode_ci
  • 6 个 Frozen Enum 用 ENUM 物理类型：
        ai_runs.status          ENUM(8: PLANNING..FAILED)
        ai_tool_calls.status    ENUM(7: PENDING..DENIED)
        ai_model_calls.call_type ENUM(4: chat/embedding/vision/rerank)
        ai_approvals.decision   ENUM(4: PENDING/APPROVED/REJECTED/EXPIRED)
        ai_incidents.category   ENUM(3: capability/compliance/data)
        ai_incidents.severity   ENUM(4: LOW/MEDIUM/HIGH/CRITICAL)
  • SHA-256 字段全部 VARCHAR(64)（query_hash/error_message_hash/prompt_hash/
    completion_hash/payload_hash_sha256/snapshot_hash）
  • ai_runs.updated_at → DEFAULT + ON UPDATE CURRENT_TIMESTAMP
    （MySQL 方言无独立 ON UPDATE 选项；官方写法 =
    server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")）
  • ai_tool_calls.retry_count = INT UNSIGNED
  • ai_command_envelopes.payload_ciphertext = 裸 BLOB（不带 display length）
  • 内部 FK 一律 composite tenant FK (school_id, …) + ON DELETE RESTRICT
  • 4 named UNIQUE KEY：
        uq_run_school          (ai_runs.school_id, id)
        uq_toolcall_school     (ai_tool_calls.school_id, id)
        uq_model_call_seq      (ai_model_calls.school_id, run_id, call_seq)
        uq_school_idempotency  (ai_tool_calls.school_id, idempotency_key)
  • 3 inline UNIQUE：
        ai_runs.run_uuid
        ai_command_envelopes.envelope_uuid
        ai_execution_snapshots.run_id   (1 Run : 1 Snapshot)
  • schools / users 故意不加 physical FK（logical reference + 运行时 WHERE）
  • 27 Invariants 全部落地（tests/ai_native/* 覆盖）

Revision ID: 20260811_1810
Revises: f7c2a91d4b60
Create Date: 2026-08-11 18:10:00.000000

★ 本 migration 由人工按 v3.2 FINAL 编写，不依赖 autogenerate。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = "20260811_1810"
down_revision: str | None = "f7c2a91d4b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ═══════════════════════════════════════════════════════════════
#  Schema-level helpers（统一全表字符集 + 复合 FK + RESTRICT）
# ═══════════════════════════════════════════════════════════════


_TABLE_OPTS = dict(
    mysql_engine="InnoDB",
    mysql_default_charset="utf8mb4",
    mysql_collate="utf8mb4_unicode_ci",
)


def _run_fk(table_name: str) -> sa.ForeignKeyConstraint:
    """composite tenant FK (school_id, run_id) → ai_runs(school_id, id) RESTRICT."""
    return sa.ForeignKeyConstraint(
        ["school_id", "run_id"],
        ["ai_runs.school_id", "ai_runs.id"],
        name=op.f(f"fk_{table_name}_run"),
        ondelete="RESTRICT",
    )


def _toolcall_fk(table_name: str) -> sa.ForeignKeyConstraint:
    """composite tenant FK (school_id, tool_call_id) → ai_tool_calls(school_id, id) RESTRICT."""
    return sa.ForeignKeyConstraint(
        ["school_id", "tool_call_id"],
        ["ai_tool_calls.school_id", "ai_tool_calls.id"],
        name=op.f(f"fk_{table_name}_tool_call"),
        ondelete="RESTRICT",
    )


# ═══════════════════════════════════════════════════════════════
#  upgrade — 按依赖顺序建表（父表先建以满足子表 FK）
# ═══════════════════════════════════════════════════════════════


def upgrade() -> None:
    # ────────────────────────────────────────────────────────
    # 1. ai_runs — 父表（被 8 张子表 composite FK 引用）
    # ────────────────────────────────────────────────────────
    op.create_table(
        "ai_runs",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("run_uuid", mysql.CHAR(36), nullable=False, comment="对外 Run UUID"),
        sa.Column(
            "school_id", mysql.BIGINT(), nullable=False,
            comment="租户隔离；类型=School.id；intentionally no FK",
        ),
        sa.Column(
            "user_id", mysql.BIGINT(), nullable=False,
            comment="触发者；类型=User.id；intentionally no FK",
        ),
        sa.Column("role_profile", mysql.VARCHAR(50), nullable=False),
        sa.Column("role_profile_version", mysql.VARCHAR(20), nullable=True),
        sa.Column("copilot_profile", mysql.VARCHAR(64), nullable=True),
        sa.Column("query_hash", mysql.VARCHAR(64), nullable=True),
        sa.Column("query_redacted", mysql.VARCHAR(512), nullable=True),
        sa.Column("input_summary", mysql.VARCHAR(256), nullable=True),
        sa.Column(
            "status",
            mysql.ENUM(
                "PLANNING", "POLICY_CHECK", "EXECUTING", "WAITING_APPROVAL",
                "RECOVERING", "RESUMING", "COMPLETED", "FAILED",
            ),
            nullable=False,
            server_default=sa.text("'PLANNING'"),
        ),
        sa.Column(
            "data_classification", mysql.VARCHAR(30), nullable=False,
            server_default=sa.text("'internal'"),
        ),
        sa.Column("data_classification_peak", mysql.VARCHAR(30), nullable=True),
        sa.Column("trace_id", mysql.VARCHAR(64), nullable=True),
        sa.Column("primary_provider", mysql.VARCHAR(50), nullable=True),
        sa.Column("primary_model", mysql.VARCHAR(80), nullable=True),
        sa.Column(
            "started_at", mysql.DATETIME(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", mysql.DATETIME(), nullable=True),
        sa.Column("error_kind", mysql.VARCHAR(50), nullable=True),
        sa.Column("error_message_hash", mysql.VARCHAR(64), nullable=True),
        sa.Column(
            "created_at", mysql.DATETIME(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", mysql.DATETIME(), nullable=False,
            server_default=sa.text(
                "CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
            ),
        ),
        # UNIQUE: uq_run_school (school_id, id) — 父键复合 UNIQUE
        sa.UniqueConstraint("school_id", "id", name="uq_run_school"),
        # UNIQUE: run_uuid（inline）
        sa.UniqueConstraint("run_uuid", name="uq_ai_runs_run_uuid"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_runs")),
        mysql_engine="InnoDB",
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        op.f("idx_ai_runs_user_id"), "ai_runs", ["user_id"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_runs_status"), "ai_runs", ["status"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_runs_started_at"), "ai_runs", ["started_at"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_runs_classification_peak"),
        "ai_runs", ["data_classification_peak", "created_at"], unique=False,
    )

    # ────────────────────────────────────────────────────────
    # 2. ai_runs_status_events
    # ────────────────────────────────────────────────────────
    op.create_table(
        "ai_runs_status_events",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("school_id", mysql.BIGINT(), nullable=False),
        sa.Column("run_id", mysql.BIGINT(), nullable=False),
        sa.Column("from_status", mysql.VARCHAR(30), nullable=True),
        sa.Column("to_status", mysql.VARCHAR(30), nullable=False),
        sa.Column("trigger_reason", mysql.VARCHAR(256), nullable=True),
        sa.Column("payload", mysql.JSON(), nullable=True),
        sa.Column(
            "created_at", mysql.DATETIME(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        _run_fk("ai_runs_status_events"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_runs_status_events")),
        **_TABLE_OPTS,
    )
    op.create_index(
        op.f("idx_ai_runs_status_events_run"),
        "ai_runs_status_events", ["run_id", "created_at"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_runs_status_events_school_run"),
        "ai_runs_status_events", ["school_id", "created_at"], unique=False,
    )

    # ────────────────────────────────────────────────────────
    # 3. ai_tool_calls — 提前建（供 model_calls/retrievals/approvals/envelopes FK）
    # ────────────────────────────────────────────────────────
    op.create_table(
        "ai_tool_calls",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("school_id", mysql.BIGINT(), nullable=False),
        sa.Column("run_id", mysql.BIGINT(), nullable=False),
        sa.Column("tool_name", mysql.VARCHAR(100), nullable=False),
        sa.Column("tool_version", mysql.VARCHAR(20), nullable=False),
        sa.Column("schema_version", mysql.VARCHAR(20), nullable=False),
        sa.Column("action", mysql.VARCHAR(30), nullable=False),
        sa.Column(
            "side_effect", mysql.VARCHAR(30), nullable=False,
            server_default=sa.text("'none'"),
        ),
        sa.Column("arguments_hash", mysql.VARCHAR(64), nullable=False),
        sa.Column("idempotency_key", mysql.VARCHAR(64), nullable=False),
        sa.Column("resource_scope", mysql.JSON(), nullable=False),
        sa.Column("declared_output_classification", mysql.VARCHAR(30), nullable=False),
        sa.Column("actual_output_classification", mysql.VARCHAR(30), nullable=True),
        sa.Column(
            "status",
            mysql.ENUM(
                "PENDING", "EXECUTING", "EXECUTED", "FAILED",
                "UNKNOWN_COMMIT", "AWAITING_APPROVAL", "DENIED",
            ),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("result_hash", mysql.VARCHAR(64), nullable=True),
        sa.Column("code_revision", mysql.VARCHAR(64), nullable=True),
        sa.Column(
            "retry_count", mysql.INTEGER(unsigned=True), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "reconciliation_attempted", mysql.BOOLEAN(), nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("error_kind", mysql.VARCHAR(50), nullable=True),
        sa.Column("started_at", mysql.DATETIME(), nullable=False),
        sa.Column("completed_at", mysql.DATETIME(), nullable=True),
        # UNIQUE: uq_toolcall_school (school_id, id)
        sa.UniqueConstraint("school_id", "id", name="uq_toolcall_school"),
        # UNIQUE: uq_school_idempotency (school_id, idempotency_key)
        sa.UniqueConstraint(
            "school_id", "idempotency_key", name="uq_school_idempotency",
        ),
        _run_fk("ai_tool_calls"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_tool_calls")),
        **_TABLE_OPTS,
    )
    op.create_index(
        op.f("idx_ai_tool_calls_run"), "ai_tool_calls", ["run_id"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_tool_calls_tool"),
        "ai_tool_calls", ["tool_name", "tool_version"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_tool_calls_school_status"),
        "ai_tool_calls", ["school_id", "status", "started_at"], unique=False,
    )

    # ────────────────────────────────────────────────────────
    # 4. ai_model_calls
    # ────────────────────────────────────────────────────────
    op.create_table(
        "ai_model_calls",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("school_id", mysql.BIGINT(), nullable=False),
        sa.Column("run_id", mysql.BIGINT(), nullable=False),
        sa.Column("tool_call_id", mysql.BIGINT(), nullable=True),
        sa.Column(
            "call_seq", mysql.INTEGER(unsigned=True), nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("provider", mysql.VARCHAR(50), nullable=False),
        sa.Column("model", mysql.VARCHAR(80), nullable=False),
        sa.Column("call_type",
                  mysql.ENUM("chat", "embedding", "vision", "rerank"),
                  nullable=False),
        sa.Column("preferred_wire_format", mysql.VARCHAR(30), nullable=True),
        sa.Column("actual_wire_format", mysql.VARCHAR(30), nullable=True),
        sa.Column("prompt_hash", mysql.VARCHAR(64), nullable=True),
        sa.Column("completion_hash", mysql.VARCHAR(64), nullable=True),
        sa.Column("reasoning_level", mysql.VARCHAR(20), nullable=True),
        sa.Column("reasoning_effort", mysql.VARCHAR(16), nullable=True),
        sa.Column(
            "reasoning_tokens", mysql.INTEGER(unsigned=True), nullable=True,
        ),
        sa.Column("data_classification_at_call", mysql.VARCHAR(30), nullable=False),
        sa.Column("error_kind", mysql.VARCHAR(50), nullable=True),
        sa.Column(
            "prompt_tokens", mysql.INTEGER(unsigned=True), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "completion_tokens", mysql.INTEGER(unsigned=True), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_tokens", mysql.INTEGER(unsigned=True), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "cost_amount", mysql.DECIMAL(10, 6), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("cost_currency", mysql.CHAR(3), nullable=False),
        sa.Column(
            "latency_ms", mysql.INTEGER(unsigned=True), nullable=True,
            server_default=sa.text("0"),
        ),
        sa.Column("request_sent_at", mysql.DATETIME(), nullable=True),
        sa.Column("response_received_at", mysql.DATETIME(), nullable=True),
        sa.Column("started_at", mysql.DATETIME(), nullable=False),
        sa.Column("completed_at", mysql.DATETIME(), nullable=True),
        # UNIQUE: uq_model_call_seq (school_id, run_id, call_seq)
        sa.UniqueConstraint(
            "school_id", "run_id", "call_seq", name="uq_model_call_seq",
        ),
        _run_fk("ai_model_calls"),
        _toolcall_fk("ai_model_calls"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_model_calls")),
        **_TABLE_OPTS,
    )
    op.create_index(
        op.f("idx_ai_model_calls_school_run"),
        "ai_model_calls", ["school_id", "started_at"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_model_calls_provider_model"),
        "ai_model_calls", ["provider", "model"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_model_calls_tool_call"),
        "ai_model_calls", ["tool_call_id"], unique=False,
    )

    # ────────────────────────────────────────────────────────
    # 5. ai_retrievals
    # ────────────────────────────────────────────────────────
    op.create_table(
        "ai_retrievals",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("school_id", mysql.BIGINT(), nullable=False),
        sa.Column("run_id", mysql.BIGINT(), nullable=False),
        sa.Column("tool_call_id", mysql.BIGINT(), nullable=True),
        sa.Column("query_hash", mysql.VARCHAR(64), nullable=False),
        sa.Column("embedding_provider", mysql.VARCHAR(50), nullable=False),
        sa.Column("embedding_model", mysql.VARCHAR(80), nullable=False),
        sa.Column("vector_store", mysql.VARCHAR(50), nullable=False),
        sa.Column("index_version", mysql.VARCHAR(20), nullable=True),
        sa.Column(
            "top_k", mysql.INTEGER(unsigned=True), nullable=False,
            server_default=sa.text("5"),
        ),
        sa.Column("candidate_chunk_ids", mysql.JSON(), nullable=False),
        sa.Column("returned_chunk_ids", mysql.JSON(), nullable=False),
        sa.Column("cosine_scores", mysql.JSON(), nullable=True),
        sa.Column(
            "threshold_passed", mysql.BOOLEAN(), nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "rbac_filtered_count", mysql.INTEGER(unsigned=True), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "qdrant_ranking_preserved", mysql.BOOLEAN(), nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("resource_scope", mysql.JSON(), nullable=False),
        sa.Column("acl_filter", mysql.JSON(), nullable=True),
        sa.Column(
            "latency_ms", mysql.INTEGER(unsigned=True), nullable=True,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "occurred_at", mysql.DATETIME(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        _run_fk("ai_retrievals"),
        _toolcall_fk("ai_retrievals"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_retrievals")),
        **_TABLE_OPTS,
    )
    op.create_index(
        op.f("idx_ai_retrievals_run"), "ai_retrievals", ["run_id"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_retrievals_school_run"),
        "ai_retrievals", ["school_id", "occurred_at"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_retrievals_tool_call"),
        "ai_retrievals", ["tool_call_id"], unique=False,
    )

    # ────────────────────────────────────────────────────────
    # 6. ai_approvals
    # ────────────────────────────────────────────────────────
    op.create_table(
        "ai_approvals",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("school_id", mysql.BIGINT(), nullable=False),
        sa.Column("run_id", mysql.BIGINT(), nullable=False),
        sa.Column("tool_call_id", mysql.BIGINT(), nullable=False),
        sa.Column("tool_name", mysql.VARCHAR(100), nullable=False),
        sa.Column("tool_version", mysql.VARCHAR(20), nullable=False),
        sa.Column("schema_version", mysql.VARCHAR(20), nullable=False),
        sa.Column("policy_version", mysql.VARCHAR(20), nullable=False),
        sa.Column("role_profile_version", mysql.VARCHAR(20), nullable=False),
        sa.Column("arguments_hash", mysql.VARCHAR(64), nullable=False),
        sa.Column("resource_scope", mysql.JSON(), nullable=False),
        sa.Column("approver_id", mysql.BIGINT(), nullable=True),
        sa.Column(
            "decision",
            mysql.ENUM("PENDING", "APPROVED", "REJECTED", "EXPIRED"),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("decided_at", mysql.DATETIME(), nullable=True),
        sa.Column("expiry_at", mysql.DATETIME(), nullable=False),
        _run_fk("ai_approvals"),
        _toolcall_fk("ai_approvals"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_approvals")),
        **_TABLE_OPTS,
    )
    op.create_index(
        op.f("idx_ai_approvals_run"), "ai_approvals", ["run_id"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_approvals_tool_call"),
        "ai_approvals", ["tool_call_id"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_approvals_decision"),
        "ai_approvals", ["decision", "expiry_at"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_approvals_school"),
        "ai_approvals", ["school_id", "decided_at"], unique=False,
    )

    # ────────────────────────────────────────────────────────
    # 7. ai_incidents
    # ────────────────────────────────────────────────────────
    op.create_table(
        "ai_incidents",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("school_id", mysql.BIGINT(), nullable=False),
        sa.Column("run_id", mysql.BIGINT(), nullable=False),
        sa.Column("incident_code", mysql.VARCHAR(10), nullable=False),
        sa.Column("incident_type", mysql.VARCHAR(50), nullable=False),
        sa.Column(
            "category", mysql.ENUM("capability", "compliance", "data"),
            nullable=False,
        ),
        sa.Column(
            "severity",
            mysql.ENUM("LOW", "MEDIUM", "HIGH", "CRITICAL"),
            nullable=False,
        ),
        sa.Column("summary_redacted", mysql.VARCHAR(512), nullable=False),
        sa.Column("detail_hash", mysql.VARCHAR(64), nullable=True),
        sa.Column(
            "resolved", mysql.BOOLEAN(), nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("resolved_at", mysql.DATETIME(), nullable=True),
        sa.Column(
            "detected_at", mysql.DATETIME(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        _run_fk("ai_incidents"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_incidents")),
        **_TABLE_OPTS,
    )
    op.create_index(
        op.f("idx_ai_incidents_run"), "ai_incidents", ["run_id"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_incidents_code"),
        "ai_incidents", ["incident_code"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_incidents_category"),
        "ai_incidents", ["category"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_incidents_school_severity"),
        "ai_incidents", ["school_id", "severity", "detected_at"], unique=False,
    )

    # ────────────────────────────────────────────────────────
    # 8. ai_command_envelopes
    # ────────────────────────────────────────────────────────
    op.create_table(
        "ai_command_envelopes",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column(
            "envelope_uuid", mysql.CHAR(36), nullable=False,
            comment="对外 Envelope UUID",
        ),
        sa.Column("school_id", mysql.BIGINT(), nullable=False),
        sa.Column("run_id", mysql.BIGINT(), nullable=False),
        sa.Column("tool_call_id", mysql.BIGINT(), nullable=False),
        sa.Column("tool_name", mysql.VARCHAR(100), nullable=False),
        sa.Column("tool_version", mysql.VARCHAR(20), nullable=False),
        sa.Column("schema_version", mysql.VARCHAR(20), nullable=False),
        sa.Column("payload_ciphertext", mysql.BLOB(), nullable=False),
        sa.Column("nonce", mysql.VARBINARY(12), nullable=False),
        sa.Column("auth_tag", mysql.VARBINARY(16), nullable=False),
        sa.Column(
            "crypto_algorithm", mysql.VARCHAR(20), nullable=False,
            server_default=sa.text("'AES-256-GCM'"),
        ),
        sa.Column("encryption_key_version", mysql.VARCHAR(32), nullable=False),
        sa.Column("payload_hash_sha256", mysql.VARCHAR(64), nullable=False),
        sa.Column(
            "created_at", mysql.DATETIME(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", mysql.DATETIME(), nullable=False),
        sa.Column("consumed_at", mysql.DATETIME(), nullable=True),
        # UNIQUE: envelope_uuid（inline）
        sa.UniqueConstraint(
            "envelope_uuid", name="uq_ai_command_envelopes_envelope_uuid",
        ),
        _run_fk("ai_command_envelopes"),
        _toolcall_fk("ai_command_envelopes"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_command_envelopes")),
        **_TABLE_OPTS,
    )
    op.create_index(
        op.f("idx_ai_command_envelopes_run"),
        "ai_command_envelopes", ["run_id"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_command_envelopes_tool_call"),
        "ai_command_envelopes", ["tool_call_id"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_command_envelopes_expires_at"),
        "ai_command_envelopes", ["expires_at"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_command_envelopes_school_run"),
        "ai_command_envelopes", ["school_id", "created_at"], unique=False,
    )

    # ────────────────────────────────────────────────────────
    # 9. ai_execution_snapshots（1:1 on run_id，最后建）
    # ────────────────────────────────────────────────────────
    op.create_table(
        "ai_execution_snapshots",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("school_id", mysql.BIGINT(), nullable=False),
        sa.Column("run_id", mysql.BIGINT(), nullable=False),
        sa.Column("snapshot_hash", mysql.VARCHAR(64), nullable=False),
        sa.Column("role_profile_version", mysql.VARCHAR(20), nullable=True),
        sa.Column("policy_version", mysql.VARCHAR(20), nullable=True),
        sa.Column("prompt_version", mysql.VARCHAR(20), nullable=True),
        sa.Column("ui_schema_version", mysql.VARCHAR(20), nullable=True),
        sa.Column("tool_versions", mysql.JSON(), nullable=True),
        sa.Column("model_call_refs", mysql.JSON(), nullable=True),
        sa.Column("retrieval_refs", mysql.JSON(), nullable=True),
        sa.Column("approval_refs", mysql.JSON(), nullable=True),
        sa.Column("classification_peak", mysql.VARCHAR(30), nullable=False),
        sa.Column("argument_hashes", mysql.JSON(), nullable=False),
        sa.Column("scope_snapshot", mysql.JSON(), nullable=True),
        sa.Column(
            "created_at", mysql.DATETIME(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        # UNIQUE: run_id（1 Run : 1 Snapshot，inline）
        sa.UniqueConstraint(
            "run_id", name="uq_ai_execution_snapshots_run_id",
        ),
        _run_fk("ai_execution_snapshots"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_execution_snapshots")),
        **_TABLE_OPTS,
    )
    op.create_index(
        op.f("idx_ai_execution_snapshots_run"),
        "ai_execution_snapshots", ["run_id"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_execution_snapshots_school_run"),
        "ai_execution_snapshots", ["school_id", "created_at"], unique=False,
    )
    op.create_index(
        op.f("idx_ai_execution_snapshots_classification"),
        "ai_execution_snapshots", ["classification_peak", "created_at"], unique=False,
    )


# ═══════════════════════════════════════════════════════════════
#  downgrade — 按依赖逆序 drop
# ═══════════════════════════════════════════════════════════════


def downgrade() -> None:
    # 9 → 1（子表先 drop，父表最后）
    op.drop_table("ai_execution_snapshots")
    op.drop_table("ai_command_envelopes")
    op.drop_table("ai_incidents")
    op.drop_table("ai_approvals")
    op.drop_table("ai_retrievals")
    op.drop_table("ai_model_calls")
    op.drop_table("ai_tool_calls")
    op.drop_table("ai_runs_status_events")
    op.drop_table("ai_runs")