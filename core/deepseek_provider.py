"""
DeepSeekProvider — WINGS 统一的 DeepSeek HTTP 调用抽象（P-1）

职责边界（BOSS 钉死，见 plans/p1-deepseek-provider.md）：
- 仅封装 env 读取 + httpx 握手 + 鉴权头 + 超时 + response_format。
- 不解析 JSON、不吞异常、不建模业务、不引入 OpenAI SDK。
- 返回 (content: str, usage: dict | None)，由各调用点保留其原有解析 / 异常 / 返回差异。

双接口非可选（只统一接口，不统一执行模型）：
- call()  —— 同步 httpx.Client，供 Celery 同步任务（ai_prescription/tasks.py、teach_math/services.py）
- acall() —— 异步 httpx.AsyncClient，供 FastAPI 异步路径（其余 5 处）
各点 timeout / format / 温度 / 消息结构 / 返回类型 / 异常分支原样保留。
"""
import os

import httpx

_DEFAULT_URL = "https://api.deepseek.com/v1/chat/completions"
_DEFAULT_MODEL = "deepseek-chat"


class DeepSeekProvider:
    def __init__(
        self,
        *,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_url = api_url or os.environ.get("LLM_API_URL", _DEFAULT_URL)
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.model = model or os.environ.get("LLM_MODEL", _DEFAULT_MODEL)

    @staticmethod
    def _payload(
        *,
        messages: list[dict],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        model: str,
    ) -> dict:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def call(
        self,
        messages: list[dict],
        *,
        timeout: float = 60.0,
        json_mode: bool = False,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        model: str | None = None,
    ) -> tuple[str, dict | None]:
        """同步调用。返回 (content, usage)。非 2xx 抛 httpx.HTTPStatusError。"""
        payload = self._payload(
            messages=messages,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model or self.model,
        )
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"], data.get("usage")

    async def acall(
        self,
        messages: list[dict],
        *,
        timeout: float = 30.0,
        json_mode: bool = False,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        model: str | None = None,
    ) -> tuple[str, dict | None]:
        """异步调用。返回 (content, usage)。非 2xx 抛 httpx.HTTPStatusError。"""
        payload = self._payload(
            messages=messages,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model or self.model,
        )
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"], data.get("usage")
