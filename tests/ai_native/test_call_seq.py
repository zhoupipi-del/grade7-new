"""
tests/ai_native/test_call_seq.py — Inv 27

★ Inv 27: 同 tenant + Run 的 ai_model_calls.call_seq 唯一且单调递增
  • DB UNIQUE(school_id, run_id, call_seq)  ← 本文件验证
  • Runtime call_seq 自增（每 Run 从 1 起）  ← Phase E runtime 验证
"""

from __future__ import annotations

import pytest

from tests.ai_native.conftest import (
    raw_info_schema_columns,
    raw_info_schema_statistics,
)


class TestInv27CallSeqDBUnique:
    """DB 层 UNIQUE(school_id, run_id, call_seq) — 用 NON_UNIQUE 真实验证。"""

    def test_unique_index_columns_and_uniqueness(self, engine):
        """★ 真正查 INFORMATION_SCHEMA.STATISTICS.NON_UNIQUE = 0 即 UNIQUE。
        不再用 assert True 假 PASS。"""
        rows = raw_info_schema_statistics(
            engine, "ai_model_calls", "uq_model_call_seq",
        )
        assert rows, "uq_model_call_seq 未建"
        cols = [r["COLUMN_NAME"].lower() for r in rows]
        assert cols == ["school_id", "run_id", "call_seq"], (
            f"uq_model_call_seq 列序不对：实为 {cols}"
        )
        # ★ 真 UNIQUE 断言
        non_unique_values = {r["NON_UNIQUE"] for r in rows}
        assert non_unique_values == {0}, (
            f"uq_model_call_seq 不是 UNIQUE 索引：NON_UNIQUE={non_unique_values} "
            f"（0 = UNIQUE，1 = 非 UNIQUE）"
        )

    def test_call_seq_column_unsigned_int_default_1(self, engine):
        rows = raw_info_schema_columns(engine, "ai_model_calls")
        c = next(r for r in rows if r["COLUMN_NAME"] == "call_seq")
        assert c["DATA_TYPE"] == "int"
        assert "unsigned" in c["COLUMN_TYPE"].lower()
        assert c["IS_NULLABLE"] == "NO"
        default = str(c["COLUMN_DEFAULT"] or "").strip("'\"")
        assert default == "1", f"call_seq DEFAULT 应为 1，实为 {c['COLUMN_DEFAULT']!r}"

    def test_unique_constraint_present_in_inspector(self, db_inspector):
        """★ 双保险：SQLAlchemy Inspector 报告 UNIQUE 约束名存在。"""
        from tests.ai_native.conftest import table_constraints

        c = table_constraints(db_inspector, "ai_model_calls")
        assert "uq_model_call_seq" in c["unique"], (
            f"uq_model_call_seq 缺失；现有：{sorted(c['unique'])}"
        )


class TestInv27CallSeqRuntimeMonotonicDeferred:
    """Inv 27 Runtime 单调递增由 Phase E 补全。

    ★ 行为证明（B1 阶段可做部分 DB 验证）：
      DB 层 UNIQUE 已禁相同 (school_id, run_id, call_seq)；运行时 INSERT 两条
      同 call_seq 行应被 DB 拒绝（IntegrityError）。Runtime 单调自增由 Provider
      Adapter / ToolExecutor 保证（Phase E）。
    """

    def test_db_rejects_duplicate_call_seq(self, db_session, cross_school_setup):
        """★ B1 的 DB 行为证明：在合法 Run（cross_school_setup 已建）上，
        两条相同 (school_id, run_id, call_seq) 第二条必须被 DB 拒绝。"""
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        setup = cross_school_setup
        now = setup["now"]
        params = {
            "school_id": setup["school_id"],
            "run_id": setup["run_id"],
            "now": now,
        }

        # INSERT #1 — 合法（FK → ai_runs 存在）
        db_session.execute(
            text(
                """
                INSERT INTO ai_model_calls
                  (school_id, run_id, call_seq,
                   provider, model, call_type,
                   data_classification_at_call,
                   cost_amount, cost_currency, started_at)
                VALUES
                  (:school_id, :run_id, 1,
                   'test', 'm', 'chat',
                   'internal',
                   0.0, 'USD', :now)
                """
            ),
            params,
        )
        db_session.flush()

        # INSERT #2 — 同 (school_id, run_id, call_seq) → UNIQUE 冲突
        with pytest.raises(IntegrityError):
            db_session.execute(
                text(
                    """
                    INSERT INTO ai_model_calls
                      (school_id, run_id, call_seq,
                       provider, model, call_type,
                       data_classification_at_call,
                       cost_amount, cost_currency, started_at)
                    VALUES
                      (:school_id, :run_id, 1,
                       'test', 'm', 'chat',
                       'internal',
                       0.0, 'USD', :now)
                    """
                ),
                params,
            )
            db_session.flush()

    def test_runtime_monotonic_pending_phase_e(self):
        pytest.skip(
            "Runtime call_seq 单调自增由 ai_native/runtime/tool_executor.py "
            "（Phase E 实现）补全"
        )