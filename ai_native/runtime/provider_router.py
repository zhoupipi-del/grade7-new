"""
ai_native.runtime.provider_router — Provider Router（Inv 21）
=============================================================

- 复用 core/deepseek_provider.py 的 DeepSeekProvider（禁止新写裸 HTTP client）。
- ModelCallRecord：cost_amount + cost_currency 必填；
  cost_currency None / "" / 缺失 → ValueError（禁止默默补 USD/CNY，
  计费信息由 Provider Adapter 显式提供）。
- ProviderRouter.route(model, data_classification, ...) 必须接受当前 Run 的
  data_classification（预留 classification-aware routing，避免将来绕开
  classification policy）。

对应测试：tests/ai_native/test_runtime_provider_currency.py（Inv 21 全量）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from core.deepseek_provider import DeepSeekProvider


@dataclass
class ModelCallRecord:
    """成功 ai_model_calls 的计费记录契约（cost_amount/cost_currency 必填）。"""

    model: str
    cost_amount: Any
    cost_currency: Optional[str] = None
    usage: Dict[str, Any] = field(default_factory=dict)
    call_seq: Optional[int] = None

    def __post_init__(self) -> None:
        if self.cost_amount is None:
            raise ValueError("ModelCallRecord 缺少 cost_amount")
        if not self.cost_currency:
            raise ValueError(
                "ModelCallRecord 缺少 cost_currency（由 Provider Adapter 显式提供，"
                "禁止自动补 USD/CNY）"
            )


class ProviderRouter:
    """模型路由：复用 DeepSeekProvider，不写裸 HTTP。"""

    def __init__(self, provider: DeepSeekProvider | None = None) -> None:
        self._provider = provider or DeepSeekProvider()

    def route(
        self,
        *,
        model: str,
        data_classification: str,
        **kwargs: Any,
    ) -> DeepSeekProvider:
        """返回与 model 匹配的 Provider。

        classification-aware routing 预留：接口必须接受 Run 当前
        data_classification，后续据此做 provider 选择/策略路由，
        而不是由调用方绕过 classification policy。
        """
        return self._provider

    def provider(self) -> DeepSeekProvider:
        return self._provider
