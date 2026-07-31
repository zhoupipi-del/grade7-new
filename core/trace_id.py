"""
core/trace_id.py — 请求级 Trace ID 注入器

设计:
  1. 每个请求自动生成 12 位 hex trace_id（或从 X-Trace-ID 请求头继承）
  2. 通过 contextvar 在整个请求生命周期内传递
  3. LogFilter 自动将 trace_id 注入所有日志记录（零侵入，不需要改任何 logger.info()）
  4. 响应头返回 X-Trace-ID，便于前端/运维追踪
"""

import uuid
import logging
import contextvars
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# ── 请求级上下文变量 ──
trace_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default="-"
)


class TraceIDMiddleware(BaseHTTPMiddleware):
    """
    为每个 HTTP 请求生成唯一 Trace ID。
    - 优先从 X-Trace-ID 请求头继承（支持上下游链路追踪）
    - 否则自动生成 12 位 hex
    - 注入 contextvar + 响应头
    """

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID") or uuid.uuid4().hex[:12]
        token = trace_id_ctx.set(trace_id)

        try:
            response = await call_next(request)
            response.headers["X-Trace-ID"] = trace_id
            return response
        finally:
            trace_id_ctx.reset(token)


class TraceIDLogFilter(logging.Filter):
    """
    日志过滤器：自动将当前请求的 trace_id 注入日志记录。
    零侵入 — 所有 logger.info/error/warning 自动带上 trace_id。
    """

    def filter(self, record):
        record.trace_id = trace_id_ctx.get()
        return True
