"""
tests/ai_native/test_runtime_provider_currency.py — Inv 21: Provider 必填 cost_currency

RED GATE 测试（Phase E Slice 1）：组件 `ai_native.runtime.provider_router`
尚未实现，全部测试预期 FAIL（需求未实现导致的正确失败）。

契约（未来实现必须满足）：
    - 成功的 ai_model_calls 计费记录必须同时具备 cost_amount + cost_currency
    - cost_currency is None 或 "" → 必须报错（不允许自动补 CNY / USD）
    - 计费信息由 Provider Adapter 显式提供，Router 不做静默默认
    - Router 接口必须接受当前 Run 的 data_classification
      （预留 classification-aware routing，避免将来绕开 classification policy）

    实现形态：
        ModelCallRecord（Pydantic/校验模型）—— cost_amount / cost_currency 必填；
        ProviderRouter.route(model, data_classification, ...) —— 签名必须接收
        当前 Run 的 data_classification。
"""

from __future__ import annotations

import importlib

import pytest


def _require_provider_router():
    try:
        return importlib.import_module("ai_native.runtime.provider_router")
    except ModuleNotFoundError as exc:  # pragma: no cover - RED 分支
        pytest.fail(
            f"RED: ai_native/runtime/provider_router.py 尚未实现（Slice 1 需求未落地）: {exc}"
        )


class TestInv21CostCurrencyRequired:
    def test_successful_record_requires_cost_amount_and_currency(self):
        mod = _require_provider_router()
        record = mod.ModelCallRecord(
            model="deepseek-chat",
            cost_amount="0.0012",
            cost_currency="CNY",
            usage={"prompt_tokens": 10, "completion_tokens": 2},
        )
        assert record.cost_amount is not None
        assert record.cost_currency == "CNY"

    def test_none_currency_rejected(self):
        mod = _require_provider_router()
        with pytest.raises(ValueError):
            mod.ModelCallRecord(
                model="deepseek-chat",
                cost_amount="0.0012",
                cost_currency=None,
            )

    def test_empty_string_currency_rejected(self):
        mod = _require_provider_router()
        with pytest.raises(ValueError):
            mod.ModelCallRecord(
                model="deepseek-chat",
                cost_amount="0.0012",
                cost_currency="",
            )

    def test_missing_currency_is_explicit_error_not_default(self):
        mod = _require_provider_router()
        # 不传 cost_currency → 必须显式报错，绝不自动补 CNY / USD
        with pytest.raises(ValueError):
            mod.ModelCallRecord(
                model="deepseek-chat",
                cost_amount="0.0012",
            )


class TestInv21ClassificationAwareRouting:
    def test_provider_router_accepts_run_classification(self):
        mod = _require_provider_router()
        router = mod.ProviderRouter()
        # 接口必须接受当前 Run 的 data_classification（routing 决策输入）
        router.route(model="deepseek-chat", data_classification="student_pii")
