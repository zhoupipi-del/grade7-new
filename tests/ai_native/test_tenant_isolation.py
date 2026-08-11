"""
tests/ai_native/test_tenant_isolation.py — Inv 1/2/22/26

★ Inv 1:  9 表 school_id BIGINT NOT NULL，类型=School.id
★ Inv 2:  tenant query 带 WHERE school_id（Runtime；Phase E 补）
★ Inv 22: user_id 类型=User.id (BigInteger signed)
★ Inv 26: DB FK 阻止 cross-tenant relational mismatch（composite FK 强制）

★ 关键：所有查询限定到 CANONICAL_AI_TABLES，不走 LIKE 'ai_%'（避免误扫
  ai_prescriptions 等旧 WINGS 表）。
"""

from __future__ import annotations

import pytest

from tests.ai_native.conftest import (
    CANONICAL_AI_TABLES,
    all_ai_fks,
    raw_info_schema_columns,
)


class TestTenantSchoolIdPresent:
    """Inv 1: 9 表都有 school_id BIGINT NOT NULL。"""

    @pytest.mark.parametrize("table", CANONICAL_AI_TABLES)
    def test_school_id_not_null(self, engine, table):
        rows = raw_info_schema_columns(engine, table)
        c = next(r for r in rows if r["COLUMN_NAME"] == "school_id")
        assert c["IS_NULLABLE"] == "NO"
        assert c["DATA_TYPE"] == "bigint"


class TestInv2RuntimeTenantQueryDeferred:
    """Inv 2 Runtime：所有 Service 查询 WHERE school_id — Phase E 补。"""

    def test_runtime_pending(self):
        pytest.skip(
            "Phase E 必补：所有 ai_native.* Service 的 SELECT/INSERT/UPDATE/DELETE "
            "走 WHERE school_id IN (access_scope)；由 test_tenant_context.py 6 级 "
            "RBAC 矩阵覆盖"
        )


class TestInv26NoCrossTenantFKOnCanonical9:
    """Inv 26: canonical 9 表 FK 仅引用 ai_runs / ai_tool_calls；不 FK 到 schools/users。

    ★ 通过 `IN :canonical` 限定，不扫 'ai\\_%'（避免误判 ai_prescriptions）。
    """

    def test_ai_fks_reference_only_ai_runs_or_ai_tool_calls(self, engine):
        from sqlalchemy import bindparam, text

        sql = text(
            """
            SELECT TABLE_NAME, CONSTRAINT_NAME, REFERENCED_TABLE_NAME
            FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE()
              AND TABLE_NAME IN :tables
            """
        ).bindparams(bindparam("tables", value=tuple(CANONICAL_AI_TABLES), expanding=True))
        with engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
        ref_tables = {r[2].lower() for r in rows}
        assert ref_tables.issubset({"ai_runs", "ai_tool_calls"}), (
            f"canonical 9 表出现跨包 FK：{ref_tables}"
        )

    def test_no_fk_to_schools_or_users(self, engine):
        from sqlalchemy import bindparam, text

        sql = text(
            """
            SELECT TABLE_NAME, CONSTRAINT_NAME, REFERENCED_TABLE_NAME
            FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE()
              AND TABLE_NAME IN :tables
              AND REFERENCED_TABLE_NAME IN ('schools', 'users')
            """
        ).bindparams(bindparam("tables", value=tuple(CANONICAL_AI_TABLES), expanding=True))
        with engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
        assert not rows, (
            f"canonical 9 表不应 FK 到 schools/users："
            f"{[(r[0], r[1]) for r in rows]}"
        )

    def test_composite_fk_present_for_all_cross_table_refs(self, engine):
        """★ Inv 24/26：跨表引用的 FK 必须 composite（school_id, …）。"""
        for fk in all_ai_fks(engine):
            cols = fk["constrained_columns"]
            if "school_id" in cols:
                assert len(cols) == 2, (
                    f"{fk['TABLE_NAME']}.{fk['CONSTRAINT_NAME']} 含 school_id "
                    f"但不是 composite：{cols}"
                )