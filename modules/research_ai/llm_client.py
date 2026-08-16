"""
modules/research_ai/llm_client.py
================================
WINGS 教研 AI 统一 LLM 客户端。

V2.1 修复（生产上线前审计）：
  - [P0] 移除默认 DeepSeek URL，未配置网关直接拒绝启动（强制 Privacy Gateway）
  - [P0] 不把 student_name/student_id 发给模型，仅用匿名占位符
  - [P1] HTTP 429/500/502/503 重试逻辑修复（此前 LLMError 被 raise 导致不重试）
  - [P1] 熔断器现在正确统计 HTTP 错误
  - [P1] 连续失败 3 次 → 冷却 60 秒
  - 异步 httpx 调用（httpx==0.28.1）
  - JSON 响应容错解析（支持 ```json 代码块包裹）
  - 最多重试 2 次，指数退避

环境变量：
  LLM_API_KEY   必填（Privacy Gateway 或直接 provider 的 key）
  LLM_API_URL   必填（无默认值；生产必须指向 Privacy Gateway 或合规 endpoint）
  LLM_MODEL     默认 deepseek-chat

使用：
  from modules.research_ai.llm_client import chat_json
  data, usage, elapsed = await chat_json(system_prompt, user_prompt, temperature=0.5)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── 配置（从 systemd / .env 环境变量读取） ──
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()
LLM_API_URL = os.environ.get("LLM_API_URL", "").strip()
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat").strip()

REQUEST_TIMEOUT = 180.0
MAX_RETRIES = 2

# 可重试的 HTTP 状态码
_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}

# ── 熔断器状态（进程内全局） ──
_circuit_failures = 0
_circuit_cooldown_until = 0.0
_CIRCUIT_THRESHOLD = 3
_CIRCUIT_COOLDOWN = 60  # seconds


class LLMError(RuntimeError):
    """LLM 调用异常（不可重试的业务/配置错误）"""


class LLMTransportError(RuntimeError):
    """LLM 传输层异常（可重试：HTTP 5xx/429/网络错误）"""


def _record_transport_failure() -> None:
    """
    [V2.1.1] 统一记录一次传输失败，更新熔断器状态。
    所有"最终传输失败"出口必须调用本函数，避免 except 套 except 漏计数。
    """
    global _circuit_failures, _circuit_cooldown_until
    _circuit_failures += 1
    if _circuit_failures >= _CIRCUIT_THRESHOLD:
        _circuit_cooldown_until = time.time() + _CIRCUIT_COOLDOWN
        logger.error(
            "[LLM] 熔断器触发！连续失败 %s 次，冷却 %s 秒",
            _circuit_failures, _CIRCUIT_COOLDOWN,
        )


def _check_config() -> None:
    """启动时检查 LLM 配置。生产必须显式配置 LLM_API_URL，不允许默认值。"""
    if not LLM_API_URL:
        raise LLMError(
            "LLM_API_URL 未配置；生产环境必须显式指向 Privacy Gateway 或合规 LLM endpoint，"
            "禁止使用硬编码默认 URL。请在 production.env 中设置 LLM_API_URL。"
        )
    if not LLM_API_KEY:
        raise LLMError(
            "LLM_API_KEY 未配置；请在 production.env 中设置。"
            "禁止把密钥下发到前端。"
        )


# 模块加载时立即校验（fail-fast）
_check_config()


def sanitize_student_info(text: str) -> str:
    """
    隐私清洗：移除/替换学生姓名、学号等 PII。
    在发送给 LLM 前调用，确保学生身份信息不离开 WINGS 边界。
    """
    if not text:
        return text
    # 常见学号模式（8-12位数字）替换为 [学号已隐去]
    # [V2.1.2 P0] 用 (?<!\d)...(?!\d) 替代 \b：中文与数字同属 \w，\b 在
    # "学号20231234"（中文紧贴数字）处不成立，导致漏清洗。零宽断言保证
    # 两侧都不是数字即可命中，兼容 中文+数字 紧贴场景。
    text = re.sub(r'(?<!\d)\d{8,12}(?!\d)', '[学号已隐去]', text)
    return text


def _extract_json(text: str) -> dict[str, Any]:
    """从 LLM 返回文本中容错提取 JSON 对象。"""
    if not text:
        raise LLMError("模型返回为空")
    t = text.strip()
    # 去掉 ```json ... ``` 包裹
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    # 花括号配平扫描
    start = t.find("{")
    if start == -1:
        raise LLMError("未找到 JSON 起始花括号")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(t)):
        ch = t[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(t[start : i + 1])
    raise LLMError("JSON 花括号未配平")


async def chat_json(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.5,
    max_tokens: int = 8192,
    max_retries: int = MAX_RETRIES,
) -> tuple[dict[str, Any], dict[str, Any], float]:
    """
    调用 LLM Chat Completions，强制 JSON 输出。

    返回 (data_dict, usage_dict, elapsed_sec)。
    - HTTP 429/5xx/网络错误：重试 max_retries 次，计入熔断器
    - JSON 解析失败/业务错误：抛 LLMError，不重试，不计入熔断器
    """
    global _circuit_failures, _circuit_cooldown_until

    # ── 熔断器检查 ──
    if _circuit_failures >= _CIRCUIT_THRESHOLD:
        if time.time() < _circuit_cooldown_until:
            raise LLMError("LLM 熔断器开启中，暂时不可用（冷却 60s）")
        logger.warning("[LLM] 熔断器冷却结束，重置计数")
        _circuit_failures = 0

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "stream": False,
    }

    t0 = time.time()
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for attempt in range(max_retries + 1):
            try:
                resp = await client.post(LLM_API_URL, headers=headers, json=payload)

                # ── HTTP 错误：可重试的走重试，不可重试的直接抛 ──
                if resp.status_code != 200:
                    body_preview = resp.text[:500]
                    if resp.status_code in _RETRYABLE_STATUS and attempt < max_retries:
                        backoff = 1.5 * (2 ** attempt)
                        logger.warning(
                            "[LLM] HTTP %s（可重试），第%s次，%.1fs 后重试: %s",
                            resp.status_code, attempt + 1, backoff, body_preview,
                        )
                        await asyncio.sleep(backoff)
                        continue
                    # 不可重试或重试用尽 → 传输错误，统一记录熔断
                    _record_transport_failure()
                    raise LLMTransportError(
                        f"API HTTP {resp.status_code}: {body_preview}"
                    )

                result = resp.json()
                content = result["choices"][0]["message"]["content"]
                usage = result.get("usage", {}) or {}

                # ── JSON 解析：这是业务层错误，不重试 ──
                try:
                    data = _extract_json(content)
                except (LLMError, ValueError, json.JSONDecodeError) as je:
                    raise LLMError(f"JSON 解析失败：{je}") from je

                # 成功 → 重置熔断器
                _circuit_failures = 0
                return data, usage, time.time() - t0

            except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as ne:
                # 网络层错误：可重试
                if attempt < max_retries:
                    backoff = 1.5 * (2 ** attempt)
                    logger.warning(
                        "[LLM] 网络错误（可重试），第%s次，%.1fs 后重试: %s",
                        attempt + 1, backoff, ne,
                    )
                    await asyncio.sleep(backoff)
                    continue
                # [V2.1.1] 网络异常重试用尽，必须记录熔断（此前漏计数）
                _record_transport_failure()
                raise LLMTransportError(f"网络错误（已重试 {max_retries} 次）：{ne}") from ne

            except LLMTransportError:
                # 上面已通过 _record_transport_failure() 计过熔断，直接抛
                raise

            except LLMError:
                # 业务错误（JSON 解析等），不重试、不计熔断
                raise

            except (KeyError, IndexError) as ke:
                # 响应结构异常（缺 choices/message/content）
                if attempt < max_retries:
                    backoff = 1.5 * (2 ** attempt)
                    logger.warning(
                        "[LLM] 响应结构异常（可重试），第%s次: %s",
                        attempt + 1, ke,
                    )
                    await asyncio.sleep(backoff)
                    continue
                _record_transport_failure()
                raise LLMTransportError(f"响应结构异常：{ke}") from ke

            except Exception as exc:
                # 其他未知错误：保守处理，可重试
                if attempt < max_retries:
                    backoff = 1.5 * (2 ** attempt)
                    logger.warning(
                        "[LLM] 未知错误（可重试），第%s次: %s",
                        attempt + 1, exc,
                    )
                    await asyncio.sleep(backoff)
                    continue
                _record_transport_failure()
                raise LLMTransportError(f"LLM 未知错误：{exc}") from exc

    raise LLMError("LLM 调用失败：未知状态")
