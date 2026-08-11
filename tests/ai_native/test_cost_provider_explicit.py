"""
tests/ai_native/test_cost_provider_explicit.py — Inv 21

★ Inv 21: cost_amount DECIMAL + cost_currency CHAR(3)，不硬编码 CNY
  • DB 层：cost_currency NOT NULL，无静默 DEFAULT（由 Provider Adapter 显式写）
  • Runtime 侧（Provider Adapter 强制）由 Phase E 补：
    tests/ai_native/test_runtime_scaffolds.py::TestInv21RuntimeProviderExplicit
"""

from __future__ import annotations

import pytest

from tests.ai_native.conftest import raw_info_schema_columns


class TestInv21CostAmountDecimal:
    """Inv 21: cost_amount DECIMAL(10,6) NOT NULL。"""

    def test_cost_amount_decimal_10_6(self, engine):
        rows = raw_info_schema_columns(engine, "ai_model_calls")
        c = next(r for r in rows if r["COLUMN_NAME"] == "cost_amount")
        assert c["COLUMN_TYPE"] == "decimal(10,6)"
        assert c["IS_NULLABLE"] == "NO"


class TestInv21CostCurrencyChar3:
    """Inv 21: cost_currency CHAR(3) NOT NULL，无静默 DEFAULT。"""

    def test_cost_currency_char_3_not_null(self, engine):
        rows = raw_info_schema_columns(engine, "ai_model_calls")
        c = next(r for r in rows if r["COLUMN_NAME"] == "cost_currency")
        assert c["COLUMN_TYPE"] == "char(3)"
        assert c["IS_NULLABLE"] == "NO"

    def test_cost_currency_no_default(self, engine):
        """Inv 21: cost_currency 无静默 DEFAULT（Provider Adapter 显式写）。"""
        rows = raw_info_schema_columns(engine, "ai_model_calls")
        c = next(r for r in rows if r["COLUMN_NAME"] == "cost_currency")
        assert c["COLUMN_DEFAULT"] is None, (
            f"Inv 21 违例：cost_currency 出现静默默认值 {c['COLUMN_DEFAULT']!r}；"
            f"必须由 Provider Adapter 显式写入"
        )

    def test_cost_currency_not_cny_hardcoded(self, engine):
        """★ 防御性：DB 元数据不含 'CNY' 默认值字符串。"""
        rows = raw_info_schema_columns(engine, "ai_model_calls")
        c = next(r for r in rows if r["COLUMN_NAME"] == "cost_currency")
        raw = str(c.get("COLUMN_DEFAULT") or "").upper()
        assert "CNY" not in raw, (
            f"cost_currency 默认值 {c['COLUMN_DEFAULT']!r} 含 CNY 硬编码"
        )