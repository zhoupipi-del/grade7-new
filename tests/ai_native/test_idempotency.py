"""
tests/ai_native/test_idempotency.py — Inv 7

★ Inv 7: ai_tool_calls 有 idempotency_key + UNIQUE 约束
★ Inv 8 (UNKNOWN_COMMIT 不自动 retry) 属 Runtime — 由
  test_runtime_scaffolds.py::TestInv8UnknownCommitNoRetry 占位
"""

from __future__ import annotations

import pytest

from tests.ai_native.conftest import raw_info_schema_columns, table_constraints


class TestInv7IdempotencyKeyColumn:
    """idempotency_key 列必须存在且 NOT NULL。"""

    def test_idempotency_key_not_null(self, engine):
        rows = raw_info_schema_columns(engine, "ai_tool_calls")
        c = next(r for r in rows if r["COLUMN_NAME"] == "idempotency_key")
        assert c["IS_NULLABLE"] == "NO"
        assert c["DATA_TYPE"] == "varchar"


class TestInv7IdempotencyUnique:
    """uq_school_idempotency (school_id, idempotency_key) UNIQUE 必建。"""

    def test_unique_constraint_exists(self, db_inspector):
        c = table_constraints(db_inspector, "ai_tool_calls")
        assert "uq_school_idempotency" in c["unique"], (
            f"uq_school_idempotency 缺失；现有：{sorted(c['unique'])}"
        )

    def test_unique_index_is_real_unique(self, engine):
        """★ 双保险：查 INFORMATION_SCHEMA.STATISTICS.NON_UNIQUE=0 验真 UNIQUE。"""
        from tests.ai_native.conftest import raw_info_schema_statistics

        rows = raw_info_schema_statistics(
            engine, "ai_tool_calls", "uq_school_idempotency",
        )
        assert rows, "uq_school_idempotency 未建"
        cols = [r["COLUMN_NAME"].lower() for r in rows]
        assert cols == ["school_id", "idempotency_key"], (
            f"uq_school_idempotency 列序不对：{cols}"
        )
        non_unique_values = {r["NON_UNIQUE"] for r in rows}
        assert non_unique_values == {0}, (
            f"uq_school_idempotency 不是 UNIQUE：NON_UNIQUE={non_unique_values}"
        )