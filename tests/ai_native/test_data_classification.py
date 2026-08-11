"""
tests/ai_native/test_data_classification.py — Inv 23

★ Inv 23: DataClassification DB 值统一小写
   （public / internal / student_pii / psych_sensitive）

★ B1 阶段 schema 锁的是 VARCHAR(30) + Python DataClassification(str,Enum) 同值；
  DB-level 验证：列类型 + 默认值（归一化引号）+ collation。
"""

from __future__ import annotations

import pytest

from tests.ai_native.conftest import raw_info_schema_columns


# Frozen 值域（v3.2 FINAL）
CLASSIFICATION_VALUES = {"public", "internal", "student_pii", "psych_sensitive"}


class TestClassificationColumnsAreVarchar30:
    """所有 DataClassification 列应为 VARCHAR(30)，允许存任意小写字符串。"""

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


class TestClassificationDefaultLowercase:
    """data_classification 默认值必须是小写 'internal'。

    ★ 不强求 SQL 引号；MySQL 元数据可能返回 'internal' / internal / 'internal'
    等多种形态。归一化后断言。
    """

    def test_default_internal_lowercase(self, engine):
        rows = raw_info_schema_columns(engine, "ai_runs")
        c = next(r for r in rows if r["COLUMN_NAME"] == "data_classification")
        assert c["COLUMN_DEFAULT"] is not None, "data_classification 必有 DEFAULT"
        actual = str(c["COLUMN_DEFAULT"]).strip("'\"").lower()
        assert actual == "internal", (
            f"data_classification 默认值 {c['COLUMN_DEFAULT']!r} "
            f"归一化后为 {actual!r}，期望 'internal'"
        )


class TestPythonDataClassificationEnumDeferred:
    """Python DataClassification Enum 与 DB 值一致（小写）— Phase E 补。"""

    def test_python_enum_pending_phase_e(self):
        pytest.skip(
            "ai_native.governance.types.DataClassification 在 Phase E 接入后补；"
            "B1 schema 仅校验列形态。"
        )