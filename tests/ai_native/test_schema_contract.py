"""
tests/ai_native/test_schema_contract.py — 27 Invariants schema contract 总闸

v3.2 FINAL frozen。本文件 + 子文件全覆盖 27 条 Invariant。报告口径：

  * SCHEMA_CONTRACT = PASS/FAIL        (本文件 + 7 专题 test 覆盖 DB-level)
  * RUNTIME_CONTRACT = DEFERRED        (test_runtime_scaffolds 占位，Phase E 补)
  * UNRESOLVED_MAPPING = 0            (27 条全部 mapped)

禁止把 pytest.skip 报成 PASS。
"""

from __future__ import annotations

import pytest

from tests.ai_native.conftest import (
    CANONICAL_AI_TABLES,
    CANONICAL_AI_TABLE_COLUMNS,
    CANONICAL_COLUMN_TYPES,
    NAMED_UNIQUE_KEYS,
    ON_UPDATE_COLUMNS,
    actual_columns,
    all_ai_fks,
    raw_info_schema_columns,
    raw_info_schema_constraints,
    table_constraints,
)


# ═══════════════════════════════════════════════════════════════
#  Block A — 9 表物理存在 + 严格 9（无 ai_evaluations / 不误含 ai_prescriptions）
# ═══════════════════════════════════════════════════════════════


class TestNineTablesExist:
    """9 表物理存在 + 严格 9（仅限 canonical 9 张，不扫描 ai_prescriptions）。"""

    def test_all_nine_canonical_tables_built(
        self, ai_native_tables_exist, ai_native_tables_missing,
    ):
        assert ai_native_tables_exist, (
            f"缺失 canonical 表：{sorted(ai_native_tables_missing)}"
        )

    def test_canonical_subset_only_no_legacy_ai_prescriptions(
        self, db_inspector,
    ):
        """★ 直接枚举 9 张表，不走 `LIKE 'ai_%'`（避免误扫 ai_prescriptions）。"""
        from sqlalchemy import text

        with db_inspector.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME IN :names
                    """
                ).bindparams(
                    __import__("sqlalchemy").bindparam(
                        "names",
                        value=tuple(CANONICAL_AI_TABLES),
                        expanding=True,
                    )
                )
            ).fetchall()
        present = {r[0].lower() for r in rows}
        assert present == set(CANONICAL_AI_TABLES), (
            f"canonical 9 表集合与 DB 实际不一致：\n"
            f"  missing = {set(CANONICAL_AI_TABLES) - present}\n"
            f"  extra   = {present - set(CANONICAL_AI_TABLES)}"
        )

    def test_ai_evaluations_not_created(
        self, db_inspector,
    ):
        """B0 §4.2 已裁定：禁止 ai_evaluations；显式查 canonical 之外的 ai_evaluations。"""
        from sqlalchemy import text

        with db_inspector.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'ai_evaluations'
                    """
                )
            ).scalar()
        assert row == 0, "B0 §4.2 裁定：禁止 ai_evaluations"


# ═══════════════════════════════════════════════════════════════
#  Block L — 9 表 exact-column allowlist（最强列契约）
# ═══════════════════════════════════════════════════════════════


class TestExactColumnAllowlist:
    """每张 canonical 表的实际列必须 = allowlist（多一列 / 少一列都 FAIL）。"""

    @pytest.mark.parametrize("table", CANONICAL_AI_TABLES)
    def test_columns_match_allowlist(self, db_inspector, table):
        actual = actual_columns(db_inspector, table)
        expected = CANONICAL_AI_TABLE_COLUMNS[table]
        missing = expected - actual
        extra = actual - expected
        assert not missing and not extra, (
            f"{table} 列集合与 canonical 不一致：\n"
            f"  missing = {sorted(missing)}\n"
            f"  extra   = {sorted(extra)}"
        )


# ═══════════════════════════════════════════════════════════════
#  Block B — Inv 1/22: school_id 类型与 School.id 完全一致（BIGINT signed）
# ═══════════════════════════════════════════════════════════════


class TestInv1SchoolIdType:
    """Inv 1: 9 表都有 school_id BIGINT NOT NULL，类型须与 School.id 完全一致。"""

    @pytest.mark.parametrize("table", CANONICAL_AI_TABLES)
    def test_school_id_bigint_signed(self, engine, table):
        rows = raw_info_schema_columns(engine, table)
        cols = {r["COLUMN_NAME"].lower(): r for r in rows}
        assert "school_id" in cols, f"{table} 缺 school_id 列"
        c = cols["school_id"]
        assert c["DATA_TYPE"] == "bigint", (
            f"{table}.school_id DATA_TYPE={c['DATA_TYPE']!r}, 应为 'bigint'"
        )
        assert c["IS_NULLABLE"] == "NO"
        assert "unsigned" not in (c["COLUMN_TYPE"] or "").lower(), (
            f"{table}.school_id COLUMN_TYPE={c['COLUMN_TYPE']!r} 出现 unsigned"
        )

    def test_school_id_type_matches_school_table(self, engine):
        ai_rows = raw_info_schema_columns(engine, "ai_runs")
        ai_cols = {r["COLUMN_NAME"].lower(): r for r in ai_rows}
        sc_rows = raw_info_schema_columns(engine, "schools")
        sc_cols = {r["COLUMN_NAME"].lower(): r for r in sc_rows}
        assert ai_cols["school_id"]["COLUMN_TYPE"] == sc_cols["id"]["COLUMN_TYPE"]


class TestInv22UserIdType:
    """Inv 22: user_id 类型 == User.id (BigInteger signed)。"""

    def test_user_id_bigint_signed(self, engine):
        rows = raw_info_schema_columns(engine, "ai_runs")
        cols = {r["COLUMN_NAME"].lower(): r for r in rows}
        c = cols["user_id"]
        assert c["DATA_TYPE"] == "bigint"
        assert c["IS_NULLABLE"] == "NO"
        assert "unsigned" not in (c["COLUMN_TYPE"] or "").lower()

    def test_user_id_type_matches_users_table(self, engine):
        ai_rows = raw_info_schema_columns(engine, "ai_runs")
        ai_cols = {r["COLUMN_NAME"].lower(): r for r in ai_rows}
        u_rows = raw_info_schema_columns(engine, "users")
        u_cols = {r["COLUMN_NAME"].lower(): r for r in u_rows}
        assert ai_cols["user_id"]["COLUMN_TYPE"] == u_cols["id"]["COLUMN_TYPE"]


# ═══════════════════════════════════════════════════════════════
#  Block C — Inv 19: 所有 FK ON DELETE RESTRICT
# ═══════════════════════════════════════════════════════════════


class TestInv19AllFKRestrict:
    """Inv 19: AI Native 9 表 FK 一律 ON DELETE RESTRICT。"""

    def test_all_ai_fks_are_restrict(self, engine):
        rows = raw_info_schema_constraints(engine)
        ai_fks = [r for r in rows if r["TABLE_NAME"].lower() in CANONICAL_AI_TABLES]
        assert ai_fks, "未发现 AI Native 9 表的任何 FK（schema 未生效）"
        bad = [r for r in ai_fks if r["DELETE_RULE"] != "RESTRICT"]
        assert not bad, "\n".join(
            f"  {r['TABLE_NAME']}.{r['CONSTRAINT_NAME']} DELETE_RULE={r['DELETE_RULE']}"
            for r in bad
        )

    def test_no_cascade_in_ai_native(self, engine):
        rows = raw_info_schema_constraints(engine)
        cascade = [
            r for r in rows
            if r["TABLE_NAME"].lower() in CANONICAL_AI_TABLES
            and r["DELETE_RULE"] == "CASCADE"
        ]
        assert not cascade, (
            f"AI Native 9 表出现 CASCADE FK："
            f"{[(r['TABLE_NAME'], r['CONSTRAINT_NAME']) for r in cascade]}"
        )


# ═══════════════════════════════════════════════════════════════
#  Block D — 7 UNIQUE 真实验证（4 named + 3 inline）
# ═══════════════════════════════════════════════════════════════


class TestUniqueKeysPresent:
    """★ 5 张表共 7 UNIQUE（4 named + 3 inline），全部实测存在。"""

    @pytest.mark.parametrize(
        "table,names", list(NAMED_UNIQUE_KEYS.items()),
    )
    def test_unique_constraint_exists(self, db_inspector, table, names):
        c = table_constraints(db_inspector, table)
        missing = set(names) - c["unique"]
        assert not missing, (
            f"{table} 缺 UNIQUE 约束：{sorted(missing)}；实际：{sorted(c['unique'])}"
        )

    @pytest.mark.parametrize(
        "table,index_name,expected_cols",
        [
            ("ai_runs", "uq_run_school", ["school_id", "id"]),
            ("ai_tool_calls", "uq_toolcall_school", ["school_id", "id"]),
            ("ai_tool_calls", "uq_school_idempotency", ["school_id", "idempotency_key"]),
            ("ai_model_calls", "uq_model_call_seq", ["school_id", "run_id", "call_seq"]),
            ("ai_runs", "uq_ai_runs_run_uuid", ["run_uuid"]),
            ("ai_command_envelopes", "uq_ai_command_envelopes_envelope_uuid",
             ["envelope_uuid"]),
            ("ai_execution_snapshots", "uq_ai_execution_snapshots_run_id",
             ["run_id"]),
        ],
    )
    def test_unique_index_columns_and_uniqueness(
        self, engine, table, index_name, expected_cols,
    ):
        """★ 直接查 INFORMATION_SCHEMA.STATISTICS 的 NON_UNIQUE 列；
        NON_UNIQUE = 0 即真正 UNIQUE 索引。"""
        from tests.ai_native.conftest import raw_info_schema_statistics

        rows = raw_info_schema_statistics(engine, table, index_name)
        assert rows, (
            f"{table}.{index_name} 未建；不能视为 UNIQUE 已生效"
        )
        cols = [r["COLUMN_NAME"].lower() for r in rows]
        assert cols == expected_cols, (
            f"{table}.{index_name} 列序不对：实为 {cols}, 期望 {expected_cols}"
        )
        # ★ 真 UNIQUE 断言（不再 assert True）
        non_unique_values = {r["NON_UNIQUE"] for r in rows}
        assert non_unique_values == {0}, (
            f"{table}.{index_name} 不是 UNIQUE 索引："
            f"NON_UNIQUE={non_unique_values}（0 = UNIQUE）"
        )


# ═══════════════════════════════════════════════════════════════
#  Block E — Inv 3: 子表 run_id 类型 == ai_runs.id (BIGINT)
# ═══════════════════════════════════════════════════════════════


class TestInv3ChildRunIdType:
    """Inv 3: child run_id 类型与 ai_runs.id 一致（BIGINT）。"""

    @pytest.mark.parametrize(
        "table",
        [
            "ai_runs_status_events", "ai_tool_calls", "ai_model_calls",
            "ai_retrievals", "ai_approvals", "ai_incidents",
            "ai_command_envelopes", "ai_execution_snapshots",
        ],
    )
    def test_run_id_type_matches_parent(self, engine, table):
        rows = raw_info_schema_columns(engine, table)
        cols = {r["COLUMN_NAME"].lower(): r for r in rows}
        parent = raw_info_schema_columns(engine, "ai_runs")
        parent_cols = {r["COLUMN_NAME"].lower(): r for r in parent}
        assert cols["run_id"]["COLUMN_TYPE"] == parent_cols["id"]["COLUMN_TYPE"]


# ═══════════════════════════════════════════════════════════════
#  Block F — Inv 4/5: 绑定 tool_call_id 的 NOT NULL / 类型
# ═══════════════════════════════════════════════════════════════


class TestInv4ApprovalToolCallNotNull:
    """Inv 4: ai_approvals.tool_call_id 非空。"""

    def test_approvals_tool_call_id_not_null(self, engine):
        rows = raw_info_schema_columns(engine, "ai_approvals")
        c = next(r for r in rows if r["COLUMN_NAME"] == "tool_call_id")
        assert c["IS_NULLABLE"] == "NO"


class TestInv5EnvelopeToolCallType:
    """Inv 5: ai_command_envelopes.tool_call_id 类型 == ai_tool_calls.id。"""

    def test_envelope_tool_call_id_type(self, engine):
        env = raw_info_schema_columns(engine, "ai_command_envelopes")
        env_c = next(r for r in env if r["COLUMN_NAME"] == "tool_call_id")
        tc = raw_info_schema_columns(engine, "ai_tool_calls")
        tc_c = next(r for r in tc if r["COLUMN_NAME"] == "id")
        assert env_c["COLUMN_TYPE"] == tc_c["COLUMN_TYPE"]


# ═══════════════════════════════════════════════════════════════
#  Block G — Inv 6: completion_hash 可 NULL（流式中断）
# ═══════════════════════════════════════════════════════════════


class TestInv6CompletionHashNullable:
    """Inv 6: completion_hash 可 NULL。"""

    def test_completion_hash_nullable(self, engine):
        rows = raw_info_schema_columns(engine, "ai_model_calls")
        c = next(r for r in rows if r["COLUMN_NAME"] == "completion_hash")
        assert c["IS_NULLABLE"] == "YES"


# ═══════════════════════════════════════════════════════════════
#  Block H — Inv 9: resource_scope 使用 JSON
# ═══════════════════════════════════════════════════════════════


class TestInv9ResourceScopeJSON:
    """Inv 9: resource_scope 使用 JSON。"""

    @pytest.mark.parametrize(
        "table",
        ["ai_tool_calls", "ai_retrievals", "ai_approvals"],
    )
    def test_resource_scope_is_json(self, engine, table):
        rows = raw_info_schema_columns(engine, table)
        c = next(r for r in rows if r["COLUMN_NAME"] == "resource_scope")
        assert c["DATA_TYPE"] == "json"


# ═══════════════════════════════════════════════════════════════
#  Block I — Inv 16/17: 无 error TEXT 列 / 无 query_text 列
# ═══════════════════════════════════════════════════════════════


class TestInv16ErrorHashInsteadOfErrorText:
    """Inv 16: ai_runs.error_message_hash 替代 error TEXT（无 error 列）。"""

    @pytest.mark.parametrize("table", CANONICAL_AI_TABLES)
    def test_no_bare_error_column(self, engine, table):
        rows = raw_info_schema_columns(engine, table)
        names = {r["COLUMN_NAME"].lower() for r in rows}
        # 允许 error_kind / error_message_hash（hash 形式）；禁止裸 error
        assert "error" not in names, (
            f"{table} 不应有 'error' 列；应使用 error_kind + error_message_hash"
        )


class TestInv17NoQueryTextColumn:
    """Inv 17: ai_retrievals 无 query_text 字段。"""

    def test_ai_retrievals_columns(self, engine):
        rows = raw_info_schema_columns(engine, "ai_retrievals")
        names = {r["COLUMN_NAME"].lower() for r in rows}
        # ★ 直白断言（不再有 or 漏洞）
        assert "query_text" not in names
        assert "query" not in names, (
            "ai_retrievals 不应有 'query' 列（用 query_hash）"
        )
        assert "query_hash" in names, "ai_retrievals 缺 query_hash 列"


# ═══════════════════════════════════════════════════════════════
#  Block J — Inv 20/21/23: reasoning_effort VARCHAR(16) / cost_*/DataClassification
# ═══════════════════════════════════════════════════════════════


class TestInv20ReasoningEffortVarchar16:
    """Inv 20: reasoning_effort VARCHAR(16)。"""

    def test_reasoning_effort_varchar_16(self, engine):
        rows = raw_info_schema_columns(engine, "ai_model_calls")
        c = next(r for r in rows if r["COLUMN_NAME"] == "reasoning_effort")
        assert c["COLUMN_TYPE"] == "varchar(16)"


class TestInv21CostAmountDecimalCurrencyChar3:
    """Inv 21: cost_amount DECIMAL(10,6) + cost_currency CHAR(3) NOT NULL。"""

    def test_cost_amount_decimal(self, engine):
        rows = raw_info_schema_columns(engine, "ai_model_calls")
        c = next(r for r in rows if r["COLUMN_NAME"] == "cost_amount")
        assert c["COLUMN_TYPE"] == "decimal(10,6)"
        assert c["IS_NULLABLE"] == "NO"

    def test_cost_currency_char_3_not_null(self, engine):
        rows = raw_info_schema_columns(engine, "ai_model_calls")
        c = next(r for r in rows if r["COLUMN_NAME"] == "cost_currency")
        assert c["COLUMN_TYPE"] == "char(3)"
        assert c["IS_NULLABLE"] == "NO"


class TestInv23DataClassificationLowercase:
    """Inv 23: DataClassification DB 值全小写（VARCHAR(30) + 默认 'internal'）。"""

    @pytest.mark.parametrize(
        "table,column",
        [
            ("ai_runs", "data_classification"),
            ("ai_runs", "data_classification_peak"),
            ("ai_tool_calls", "declared_output_classification"),
            ("ai_tool_calls", "actual_output_classification"),
            ("ai_model_calls", "data_classification_at_call"),
            ("ai_execution_snapshots", "classification_peak"),
        ],
    )
    def test_varchar_30(self, engine, table, column):
        rows = raw_info_schema_columns(engine, table)
        c = next(r for r in rows if r["COLUMN_NAME"] == column)
        assert c["COLUMN_TYPE"] == "varchar(30)"
        assert c["COLLATION_NAME"] == "utf8mb4_unicode_ci"

    def test_default_internal_lowercase(self, engine):
        """★ 不强求 SQL 引号；MySQL 元数据可能返回 'internal' / internal / 'internal'。"""
        rows = raw_info_schema_columns(engine, "ai_runs")
        c = next(r for r in rows if r["COLUMN_NAME"] == "data_classification")
        assert c["COLUMN_DEFAULT"] is not None, (
            "data_classification 必有 DEFAULT"
        )
        actual = str(c["COLUMN_DEFAULT"]).strip("'\"").lower()
        assert actual == "internal", (
            f"data_classification 默认值 {c['COLUMN_DEFAULT']!r} "
            f"归一化后为 {actual!r}，期望 'internal'"
        )


# ═══════════════════════════════════════════════════════════════
#  Block K — 全表 COLLATE = utf8mb4_unicode_ci
# ═══════════════════════════════════════════════════════════════


class TestCollationUtf8mb4UnicodeCi:
    """所有 9 表字符列 COLLATE 必须为 utf8mb4_unicode_ci。"""

    @pytest.mark.parametrize("table", CANONICAL_AI_TABLES)
    def test_table_collation(self, engine, table):
        rows = raw_info_schema_columns(engine, table)
        collations = {r["COLLATION_NAME"] for r in rows if r["COLLATION_NAME"]}
        if collations:
            assert collations == {"utf8mb4_unicode_ci"}, (
                f"{table} 字符列 collation 不一致：{collations}"
            )


# ═══════════════════════════════════════════════════════════════
#  Block N — Canonical 物理类型契约（ENUM / VARCHAR(64) / INT UNSIGNED /
#            VARBINARY(12)/(16) / BLOB / ON UPDATE）
# ═══════════════════════════════════════════════════════════════


class TestCanonicalPhysicalTypeContract:
    """★ 统一 physical type map（CANONICAL_COLUMN_TYPES）—— Canonical 已 frozen，
    任何类型漂移（VARCHAR↔ENUM、CHAR↔VARCHAR、长度错、unsigned 错）都必须 FAIL。
    """

    @pytest.mark.parametrize(
        "spec", CANONICAL_COLUMN_TYPES,
        ids=lambda s: f"{s['table']}.{s['column']}",
    )
    def test_column_physical_type(self, engine, spec):
        rows = raw_info_schema_columns(engine, spec["table"])
        c = next(r for r in rows if r["COLUMN_NAME"].lower() == spec["column"])
        actual = (c["COLUMN_TYPE"] or "").lower()
        assert actual == spec["column_type"], (
            f"{spec['table']}.{spec['column']} 物理类型漂移：\n"
            f"  实际 {actual!r}\n"
            f"  期望 {spec['column_type']!r}"
        )

    @pytest.mark.parametrize(
        "spec", ON_UPDATE_COLUMNS,
        ids=lambda s: f"{s['table']}.{s['column']}",
    )
    def test_column_on_update_current_timestamp(self, engine, spec):
        """★ updated_at 必须真正带 ON UPDATE CURRENT_TIMESTAMP（EXTRA 列断言）。"""
        from sqlalchemy import text

        sql = text(
            """
            SELECT EXTRA
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table
              AND COLUMN_NAME = :column
            """
        )
        with engine.connect() as conn:
            extra = conn.execute(
                sql, {"table": spec["table"], "column": spec["column"]},
            ).scalar()
        extra = (extra or "").lower()
        assert "on update current_timestamp" in extra, (
            f"{spec['table']}.{spec['column']} EXTRA={extra!r}，"
            f"缺 ON UPDATE CURRENT_TIMESTAMP"
        )


# 注：B1 报告口径（SCHEMA_CONTRACT=RUNTIME_CONTRACT=DEFERRED=UNRESOLVED_MAPPING=0）
# 由 Migration Gate wrapper 输出，不再让 pytest 自己测 pytest。
# 本文件不包含 TestReportingContract 哨兵类。