"""
LLM 客户端工具 — 共享大模型调用接口（熔断增强版）
供 interview_briefing.py, endterm_comment.py 等模块统一调用

增强特性:
  - 指数退避重试 (最多 2 次)
  - 熔断保护 (连续 3 次失败 → 60s 冷却期)
  - 线程安全 (Gunicorn gthread 兼容)
"""
import threading
import time
import requests
from flask import current_app


# ── 熔断器 ──────────────────────────────────────────────────────────

class LLMAvailabilityError(RuntimeError):
    """LLM 服务暂时不可用（熔断保护中），调用方应优雅降级"""
    pass


class _CircuitBreaker:
    """线程安全的简单熔断器

    状态机:
      closed  → 正常调用，记录成功/失败
      open    → 连续失败达阈值，立即拒绝请求
      half-open → 冷却期结束，尝试一次探测，成功则 closed
    """
    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()

    def check(self) -> str:
        """返回当前状态: 'closed' | 'open' | 'half-open'"""
        with self._lock:
            if self._failure_count >= self.failure_threshold:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    return "half-open"
                return "open"
            return "closed"

    def record_success(self):
        with self._lock:
            self._failure_count = 0

    def record_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()


# 全局单例（跨所有线程共享）
_circuit = _CircuitBreaker(failure_threshold=3, recovery_timeout=60)

# 可重试的 HTTP 状态码
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


# ── 核心调用函数 ───────────────────────────────────────────────────

def call_llm(system_prompt: str, user_content: str, **kwargs) -> str:
    """
    调用大模型 API（支持 DeepSeek / 通义千问 / OpenAI 兼容接口）

    内置保护:
      - 连续 3 次失败后熔断 60 秒（直接抛 LLMAvailabilityError）
      - 可重试错误（429/502/503/504/超时/连接失败）指数退避最多 2 次
      - 不可重试错误（401/403/400）立即抛出

    Args:
        system_prompt: 系统提示词
        user_content: 用户内容
        **kwargs: 可选参数
            - temperature: 温度参数（默认 0.7）
            - max_tokens: 最大 token 数（默认 1024）
            - response_format: 响应格式（默认 None）
            - timeout: 单次请求超时时间（默认 30s）

    Returns:
        LLM 返回的文本内容

    Raises:
        RuntimeError: API Key 未配置
        LLMAvailabilityError: LLM 服务熔断中，不可用
        requests.HTTPError: HTTP 请求失败（不可重试）
        requests.exceptions.Timeout: 连接超时（所有重试耗尽）
        requests.exceptions.ConnectionError: 连接失败（所有重试耗尽）
    """
    api_key = current_app.config.get("LLM_API_KEY", "")
    api_url = current_app.config.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
    model = current_app.config.get("LLM_MODEL", "deepseek-chat")
    timeout = kwargs.pop("timeout", current_app.config.get("LLM_TIMEOUT", 30))

    if not api_key:
        raise RuntimeError("LLM_API_KEY 未配置，请在环境变量中设置")

    # ── 熔断检查 ──
    state = _circuit.check()
    if state == "open":
        remaining = int(_circuit.recovery_timeout - (time.time() - _circuit._last_failure_time))
        raise LLMAvailabilityError(
            f"AI 简报服务暂时不可用，请 {remaining} 秒后重试（熔断保护中）"
        )

    # ── 构建 payload ──
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": kwargs.get("temperature", 0.7),
        "max_tokens": kwargs.get("max_tokens", 1024),
    }

    response_format = kwargs.get("response_format")
    if response_format:
        payload["response_format"] = response_format

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # ── 重试循环 ──
    max_retries = 2
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                backoff = min(2 ** attempt, 8)  # 2s, 4s, 8s cap
                time.sleep(backoff)

            resp = requests.post(api_url, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()

            # 成功 → 重置熔断器
            _circuit.record_success()

            result = resp.json()
            return result["choices"][0]["message"]["content"]

        except requests.exceptions.Timeout as e:
            last_error = e
            current_app.logger.warning(
                f"[LLM] 超时 (attempt {attempt + 1}/{max_retries + 1}): {e}"
            )
            continue

        except requests.exceptions.ConnectionError as e:
            last_error = e
            current_app.logger.warning(
                f"[LLM] 连接失败 (attempt {attempt + 1}/{max_retries + 1}): {e}"
            )
            continue

        except requests.exceptions.HTTPError as e:
            if resp.status_code in _RETRYABLE_STATUS:
                last_error = e
                current_app.logger.warning(
                    f"[LLM] HTTP {resp.status_code} (attempt {attempt + 1}/{max_retries + 1})"
                )
                continue
            # 不可重试（401/403/400）→ 记录失败并立即抛出
            _circuit.record_failure()
            current_app.logger.error(f"[LLM] 不可重试错误 HTTP {resp.status_code}: {e}")
            raise

        except Exception:
            # 未知错误 → 记录并抛出
            _circuit.record_failure()
            raise

    # 所有重试耗尽
    _circuit.record_failure()
    raise last_error or RuntimeError("LLM 调用失败（所有重试已耗尽）")


def call_llm_json(system_prompt: str, user_content: str, **kwargs) -> dict:
    """
    调用大模型并解析 JSON 响应

    Returns:
        解析后的 JSON 字典

    Raises:
        ValueError: JSON 解析失败
        LLMAvailabilityError: LLM 服务熔断中
    """
    import json
    import re

    kwargs["response_format"] = {"type": "json_object"}
    content = call_llm(system_prompt, user_content, **kwargs)

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # 尝试从文本中提取 JSON
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError(f"LLM 返回非 JSON 格式: {content[:200]}")
