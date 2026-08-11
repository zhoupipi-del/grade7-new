"""
tests/ai_native/conftest.py — 共享 fixture + schema introspection helpers

B1 Schema Implementation 测试基础设施：
  * DATABASE_URL 指向本地/隔离 MySQL（拒指 wings3 生产库）。
  * 9 张 canonical AI Native 表 allowlist（含列白名单）。
  * 12 条 composite tenant FK shape 期望清单。
  * 7 UNIQUE（4 named + 3 inline）期望清单。
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path

import pytest


# ────────────────────────────────────────────────────────
#  路径注入
# ────────────────────────────────────────────────────────

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ────────────────────────────────────────────────────────
#  DB session fixture（要求 DATABASE_URL 已设置）
# ────────────────────────────────────────────────────────


def _test_db_url() -> str:
    """测试 DB URL；强制只看 DATABASE_URL_TEST，绝不 fallback DATABASE_URL。

    战略目的：B1 schema tests 会跑 negative INSERT（跨 school approval/envelope）。
    MySQL AUTO_INCREMENT 消耗等副作用即便事务回滚也不一定完全恢复。
    因此即使 db_name 看起来像 test，也禁止 fallback 到生产 DATABASE_URL。

    使用方式（每次跑 B1 schema tests 前必须显式 export）：
        export DATABASE_URL_TEST='mysql+pymysql://tester:***@127.0.0.1:3307/wings3_b1_test'
    """
    url = os.environ.get("DATABASE_URL_TEST", "").strip()
    if not url:
        pytest.fail(
            "B1 schema tests require explicit DATABASE_URL_TEST environment variable. "
            "Fallback to DATABASE_URL is forbidden (production safety); "
            "set DATABASE_URL_TEST pointing to a dedicated test DB "
            "(db name recommended to contain '_test' or '_b1').",
            pytrace=False,
        )
    return url.replace("mysql+aiomysql://", "mysql+pymysql://")


@pytest.fixture(scope="session")
def engine():
    """Session-scoped sync Engine。"""
    from sqlalchemy import create_engine

    eng = create_engine(_test_db_url(), future=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def db_inspector(engine):
    """Session-scoped Inspector。"""
    from sqlalchemy import inspect

    return inspect(engine)


@pytest.fixture
def db_session(engine):
    """Function-scoped transactional Session（fixture 结束 rollback）。"""
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=engine, future=True)
    sess = Session()
    try:
        yield sess
    finally:
        sess.rollback()
        sess.close()


# ────────────────────────────────────────────────────────
#  Canonical 9 表清单 — single source of truth
# ────────────────────────────────────────────────────────


CANONICAL_AI_TABLES: tuple[str, ...] = (
    "ai_runs",
    "ai_runs_status_events",
    "ai_tool_calls",
    "ai_model_calls",
    "ai_retrievals",
    "ai_approvals",
    "ai_incidents",
    "ai_command_envelopes",
    "ai_execution_snapshots",
)


# ── 列 allowlist（最强契约：DB 实际列必须正好等于此集合）──


CANONICAL_AI_TABLE_COLUMNS: dict[str, frozenset[str]] = {
    "ai_runs": frozenset({
        "id", "run_uuid",
        "school_id", "user_id",
        "role_profile", "role_profile_version", "copilot_profile",
        "query_hash", "query_redacted", "input_summary",
        "status", "data_classification", "data_classification_peak",
        "trace_id", "primary_provider", "primary_model",
        "started_at", "completed_at",
        "error_kind", "error_message_hash",
        "created_at", "updated_at",
    }),
    "ai_runs_status_events": frozenset({
        "id", "school_id", "run_id",
        "from_status", "to_status",
        "trigger_reason", "payload",
        "created_at",
    }),
    "ai_tool_calls": frozenset({
        "id", "school_id", "run_id",
        "tool_name", "tool_version", "schema_version",
        "action", "side_effect",
        "arguments_hash", "idempotency_key",
        "resource_scope",
        "declared_output_classification", "actual_output_classification",
        "status",
        "result_hash", "code_revision",
        "retry_count", "reconciliation_attempted",
        "error_kind",
        "started_at", "completed_at",
    }),
    "ai_model_calls": frozenset({
        "id", "school_id", "run_id", "tool_call_id",
        "call_seq",
        "provider", "model", "call_type",
        "preferred_wire_format", "actual_wire_format",
        "prompt_hash", "completion_hash",
        "reasoning_level", "reasoning_effort", "reasoning_tokens",
        "data_classification_at_call",
        "error_kind",
        "prompt_tokens", "completion_tokens", "total_tokens",
        "cost_amount", "cost_currency",
        "latency_ms",
        "request_sent_at", "response_received_at",
        "started_at", "completed_at",
    }),
    "ai_retrievals": frozenset({
        "id", "school_id", "run_id", "tool_call_id",
        "query_hash",
        "embedding_provider", "embedding_model", "vector_store",
        "index_version",
        "top_k",
        "candidate_chunk_ids", "returned_chunk_ids", "cosine_scores",
        "threshold_passed", "rbac_filtered_count",
        "qdrant_ranking_preserved",
        "resource_scope", "acl_filter",
        "latency_ms",
        "occurred_at",
    }),
    "ai_approvals": frozenset({
        "id", "school_id", "run_id", "tool_call_id",
        "tool_name", "tool_version", "schema_version",
        "policy_version", "role_profile_version",
        "arguments_hash", "resource_scope",
        "approver_id",
        "decision", "decided_at", "expiry_at",
    }),
    "ai_incidents": frozenset({
        "id", "school_id", "run_id",
        "incident_code", "incident_type",
        "category", "severity",
        "summary_redacted", "detail_hash",
        "resolved", "resolved_at", "detected_at",
    }),
    "ai_command_envelopes": frozenset({
        "id", "envelope_uuid",
        "school_id", "run_id", "tool_call_id",
        "tool_name", "tool_version", "schema_version",
        "payload_ciphertext", "nonce", "auth_tag",
        "crypto_algorithm", "encryption_key_version",
        "payload_hash_sha256",
        "created_at", "expires_at", "consumed_at",
    }),
    "ai_execution_snapshots": frozenset({
        "id", "school_id", "run_id",
        "snapshot_hash",
        "role_profile_version", "policy_version",
        "prompt_version", "ui_schema_version",
        "tool_versions", "model_call_refs",
        "retrieval_refs", "approval_refs",
        "classification_peak",
        "argument_hashes", "scope_snapshot",
        "created_at",
    }),
}


# ── 7 UNIQUE 期望（4 named + 3 inline）──


NAMED_UNIQUE_KEYS: dict[str, tuple[str, ...]] = {
    "ai_runs":                ("uq_run_school", "uq_ai_runs_run_uuid"),
    "ai_tool_calls":          ("uq_toolcall_school", "uq_school_idempotency"),
    "ai_model_calls":         ("uq_model_call_seq",),
    "ai_command_envelopes":   ("uq_ai_command_envelopes_envelope_uuid",),
    "ai_execution_snapshots": ("uq_ai_execution_snapshots_run_id",),
}


# ── 12 条 composite tenant FK shape 期望（child → parent）──


EXPECTED_COMPOSITE_FKS: list[dict] = [
    {"child": "ai_runs_status_events", "parent": "ai_runs",
     "constrained": ["school_id", "run_id"], "referred": ["school_id", "id"]},
    {"child": "ai_tool_calls", "parent": "ai_runs",
     "constrained": ["school_id", "run_id"], "referred": ["school_id", "id"]},
    {"child": "ai_model_calls", "parent": "ai_runs",
     "constrained": ["school_id", "run_id"], "referred": ["school_id", "id"]},
    {"child": "ai_model_calls", "parent": "ai_tool_calls",
     "constrained": ["school_id", "tool_call_id"], "referred": ["school_id", "id"]},
    {"child": "ai_retrievals", "parent": "ai_runs",
     "constrained": ["school_id", "run_id"], "referred": ["school_id", "id"]},
    {"child": "ai_retrievals", "parent": "ai_tool_calls",
     "constrained": ["school_id", "tool_call_id"], "referred": ["school_id", "id"]},
    {"child": "ai_approvals", "parent": "ai_runs",
     "constrained": ["school_id", "run_id"], "referred": ["school_id", "id"]},
    {"child": "ai_approvals", "parent": "ai_tool_calls",
     "constrained": ["school_id", "tool_call_id"], "referred": ["school_id", "id"]},
    {"child": "ai_incidents", "parent": "ai_runs",
     "constrained": ["school_id", "run_id"], "referred": ["school_id", "id"]},
    {"child": "ai_command_envelopes", "parent": "ai_runs",
     "constrained": ["school_id", "run_id"], "referred": ["school_id", "id"]},
    {"child": "ai_command_envelopes", "parent": "ai_tool_calls",
     "constrained": ["school_id", "tool_call_id"], "referred": ["school_id", "id"]},
    {"child": "ai_execution_snapshots", "parent": "ai_runs",
     "constrained": ["school_id", "run_id"], "referred": ["school_id", "id"]},
]


# ── Physical type contract（Canonical 精确物理类型，统一断言）──
# 每项 = (table, column, 期望 COLUMN_TYPE 小写字符串)。
# 一旦发现新的 Canonical 物理类型漂移，在这里加一行即可，不用再造新测试。
# COLUMN_TYPE 取自 INFORMATION_SCHEMA.COLUMNS（如 enum('...') / varchar(64) /
# int unsigned / varbinary(12) / blob）。updated_at 的 ON UPDATE 单独用 EXTRA 断言。
CANONICAL_COLUMN_TYPES: list[dict] = [
    # ── 6 个 Frozen Enum ──────────────────────────────
    {"table": "ai_runs", "column": "status",
     "column_type": "enum('planning','policy_check','executing','waiting_approval','recovering','resuming','completed','failed')"},
    {"table": "ai_tool_calls", "column": "status",
     "column_type": "enum('pending','executing','executed','failed','unknown_commit','awaiting_approval','denied')"},
    {"table": "ai_model_calls", "column": "call_type",
     "column_type": "enum('chat','embedding','vision','rerank')"},
    {"table": "ai_approvals", "column": "decision",
     "column_type": "enum('pending','approved','rejected','expired')"},
    {"table": "ai_incidents", "column": "category",
     "column_type": "enum('capability','compliance','data')"},
    {"table": "ai_incidents", "column": "severity",
     "column_type": "enum('low','medium','high','critical')"},
    # ── 6 个 SHA-256 字段 = VARCHAR(64) ────────────────
    {"table": "ai_runs", "column": "query_hash", "column_type": "varchar(64)"},
    {"table": "ai_runs", "column": "error_message_hash", "column_type": "varchar(64)"},
    {"table": "ai_model_calls", "column": "prompt_hash", "column_type": "varchar(64)"},
    {"table": "ai_model_calls", "column": "completion_hash", "column_type": "varchar(64)"},
    {"table": "ai_command_envelopes", "column": "payload_hash_sha256",
     "column_type": "varchar(64)"},
    {"table": "ai_execution_snapshots", "column": "snapshot_hash",
     "column_type": "varchar(64)"},
    # ── retry_count = INT UNSIGNED ─────────────────────
    {"table": "ai_tool_calls", "column": "retry_count", "column_type": "int unsigned"},
    # ── nonce / auth_tag / payload_ciphertext ──────────
    {"table": "ai_command_envelopes", "column": "nonce", "column_type": "varbinary(12)"},
    {"table": "ai_command_envelopes", "column": "auth_tag", "column_type": "varbinary(16)"},
    {"table": "ai_command_envelopes", "column": "payload_ciphertext",
     "column_type": "blob"},
]

# ── updated_at 必须带 ON UPDATE CURRENT_TIMESTAMP（EXTRA 断言）──
ON_UPDATE_COLUMNS: list[dict] = [
    {"table": "ai_runs", "column": "updated_at"},
]


# ────────────────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def canonical_tables_present(db_inspector) -> set[str]:
    """DB 中所有表名（小写）。"""
    return {t.lower() for t in db_inspector.get_table_names()}


@pytest.fixture(scope="session")
def ai_native_tables_exist(canonical_tables_present) -> bool:
    return set(CANONICAL_AI_TABLES).issubset(canonical_tables_present)


@pytest.fixture(scope="session")
def ai_native_tables_missing(canonical_tables_present) -> set[str]:
    return set(CANONICAL_AI_TABLES) - canonical_tables_present


def table_constraints(db_inspector, table: str) -> dict:
    """某表的 UNIQUE / FK / index 概览。"""
    return {
        "unique": {u["name"] for u in db_inspector.get_unique_constraints(table)},
        "fk": db_inspector.get_foreign_keys(table),
        "indexes": {i["name"] for i in db_inspector.get_indexes(table)},
    }


def actual_columns(db_inspector, table: str) -> set[str]:
    """某表的真实列名集合（小写）。"""
    return {c["name"].lower() for c in db_inspector.get_columns(table)}


def raw_info_schema_constraints(engine) -> list[dict]:
    """INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS。"""
    from sqlalchemy import text

    sql = text(
        """
        SELECT
            CONSTRAINT_NAME,
            TABLE_NAME,
            REFERENCED_TABLE_NAME,
            DELETE_RULE,
            UNIQUE_CONSTRAINT_NAME
        FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r._mapping) for r in rows]


def raw_info_schema_columns(engine, table: str) -> list[dict]:
    """INFORMATION_SCHEMA.COLUMNS。"""
    from sqlalchemy import text

    sql = text(
        """
        SELECT
            COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, IS_NULLABLE,
            COLUMN_DEFAULT, CHARACTER_SET_NAME, COLLATION_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"table": table}).fetchall()
    return [dict(r._mapping) for r in rows]


def raw_info_schema_statistics(engine, table: str, index_name: str) -> list[dict]:
    """INFORMATION_SCHEMA.STATISTICS（带 NON_UNIQUE 列）。"""
    from sqlalchemy import text

    sql = text(
        """
        SELECT INDEX_NAME, COLUMN_NAME, SEQ_IN_INDEX, NON_UNIQUE
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = :table
          AND INDEX_NAME = :idx
        ORDER BY SEQ_IN_INDEX
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"table": table, "idx": index_name}).fetchall()
    return [dict(r._mapping) for r in rows]


def fk_constraint_columns(engine, table: str, constraint_name: str) -> list[str]:
    """返回 FK 约束的 constrained 列（按 ORDINAL_POSITION 排序）。

    ★ 必须同时传 table 与 constraint_name。KEY_COLUMN_USAGE 在同一 DB 内同
    名约束极少见，但不能依赖；带上 TABLE_NAME 杜绝误匹配。
    """
    from sqlalchemy import text

    sql = text(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = :table
          AND CONSTRAINT_NAME = :c
        ORDER BY ORDINAL_POSITION
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"table": table, "c": constraint_name}).fetchall()
    return [r[0].lower() for r in rows]


def fk_referred_columns(engine, table: str, constraint_name: str) -> list[str]:
    """返回 FK 约束的 referred columns（父表被引用列）。

    ★ 必须返回 REFERENCED_COLUMN_NAME，不要返回 COLUMN_NAME（那是子表列）。
    旧实现的 bug：返回的是 ['school_id', 'run_id']（子表列），正确应
    返回 ['school_id', 'id']。同时传 table + constraint_name 双重定位。
    """
    from sqlalchemy import text

    sql = text(
        """
        SELECT REFERENCED_COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = :table
          AND CONSTRAINT_NAME = :c
          AND REFERENCED_TABLE_NAME IS NOT NULL
        ORDER BY ORDINAL_POSITION
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"table": table, "c": constraint_name}).fetchall()
    # FILTER 防御：REFERENCED_COLUMN_NAME 应为非 NULL（非外键列会被排除）
    return [r[0].lower() for r in rows if r[0] is not None]


def all_ai_fks(engine) -> list[dict]:
    """AI Native 9 表的所有 FK（含 shape）。"""
    refs = raw_info_schema_constraints(engine)
    ai_refs = [r for r in refs if r["TABLE_NAME"].lower() in CANONICAL_AI_TABLES]
    out = []
    for r in ai_refs:
        tbl = r["TABLE_NAME"].lower()
        cname = r["CONSTRAINT_NAME"]
        out.append({
            **r,
            "constrained_columns": fk_constraint_columns(engine, tbl, cname),
            "referred_columns":    fk_referred_columns(engine, tbl, cname),
        })
    return out


# ────────────────────────────────────────────────────────
#  negative-insert fixture（Inv 24/25/26 行为证明）
# ────────────────────────────────────────────────────────


@pytest.fixture
def cross_school_setup(db_session, ai_native_tables_exist):
    """隔离 DB 上建 school A 的 Run A + ToolCall A，并另建 school B 的 Run B。

    返回 dict：
      school_id    = 1 (school A)
      run_id       = Run A id
      tool_call_id = ToolCall A id
      run_b_id     = Run B id（school B 的合法 Run）
      school_b     = 2
      now / expiry_at

    ★ Inv25 攻击路径：以 (school_id=B, run_id=RunB, tool_call_id=ToolCallA)
      插入 approval/envelope —— run FK 合法、tool_call FK 跨 school →
      IntegrityError 精准证明 Inv25（而非先挂在 run FK）。
    ★ 若 9 表未建（绿地未升），整个 fixture 跳过。
    """
    if not ai_native_tables_exist:
        pytest.skip("9 表未建；negative-insert 测试需先升 alembic upgrade head")

    from sqlalchemy import text

    now = datetime.utcnow()
    run_a_uuid = str(uuid.uuid4())
    run_b_uuid = str(uuid.uuid4())
    new_tc_idem = f"idem-{uuid.uuid4().hex[:16]}"

    # ── School A: Run A ────────────────────────────────
    db_session.execute(
        text(
            """
            INSERT INTO ai_runs
              (id, run_uuid, school_id, user_id, role_profile,
               started_at, created_at, updated_at)
            VALUES
              (DEFAULT, :uuid, 1, 1, 'teacher',
               :now, :now, :now)
            """
        ),
        {"uuid": run_a_uuid, "now": now},
    )
    run_id = db_session.execute(text("SELECT LAST_INSERT_ID()")).scalar()

    # ── School A: ToolCall A ───────────────────────────
    db_session.execute(
        text(
            """
            INSERT INTO ai_tool_calls
              (id, school_id, run_id, tool_name, tool_version,
               schema_version, action, arguments_hash, idempotency_key,
               resource_scope, declared_output_classification,
               status, started_at)
            VALUES
              (DEFAULT, 1, :run_id, 'test_tool', '1.0.0',
               '1.0.0', 'read', :ah, :idem,
               JSON_OBJECT(), 'internal',
               'EXECUTED', :now)
            """
        ),
        {
            "run_id": run_id,
            "ah": "x" * 64,
            "idem": new_tc_idem,
            "now": now,
        },
    )
    tool_call_id = db_session.execute(text("SELECT LAST_INSERT_ID()")).scalar()

    # ── School B: Run B（Inv25 攻击的"合法 run 侧"）────
    db_session.execute(
        text(
            """
            INSERT INTO ai_runs
              (id, run_uuid, school_id, user_id, role_profile,
               started_at, created_at, updated_at)
            VALUES
              (DEFAULT, :uuid, 2, 2, 'teacher',
               :now, :now, :now)
            """
        ),
        {"uuid": run_b_uuid, "now": now},
    )
    run_b_id = db_session.execute(text("SELECT LAST_INSERT_ID()")).scalar()

    return {
        "school_id": 1,
        "run_id": run_id,
        "tool_call_id": tool_call_id,
        "school_b": 2,
        "run_b_id": run_b_id,
        "now": now,
        "expiry_at": now + timedelta(minutes=30),
    }