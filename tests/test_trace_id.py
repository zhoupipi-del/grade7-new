"""
test_trace_id.py — TraceID 中间件与日志过滤器测试

覆盖范围：
- X-Trace-ID 请求头继承
- 自动生成 TraceID
- 响应头注入
- TraceIDLogFilter 日志注入
"""
import os
import logging

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")

from core.trace_id import TraceIDMiddleware, TraceIDLogFilter, trace_id_ctx


class TestTraceIDMiddleware:
    """TraceID 中间件测试"""

    def _make_client(self):
        """创建带 TraceIDMiddleware 的测试 ASGI app"""
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route
        from starlette.testclient import TestClient

        async def homepage(request):
            return JSONResponse({"trace_id": trace_id_ctx.get()})

        app = Starlette(routes=[Route("/", homepage)])
        app.add_middleware(TraceIDMiddleware)
        return TestClient(app)

    def test_trace_id_inherited_from_header(self):
        """请求头中的 X-Trace-ID 被继承到响应头"""
        client = self._make_client()
        response = client.get("/", headers={"X-Trace-ID": "abcdef123456"})
        assert response.headers["X-Trace-ID"] == "abcdef123456"

    def test_trace_id_auto_generated(self):
        """无 X-Trace-ID 请求头时自动生成 12 位 hex"""
        client = self._make_client()
        response = client.get("/")
        trace_id = response.headers["X-Trace-ID"]
        assert len(trace_id) == 12
        # 验证是合法的 hex 字符串
        int(trace_id, 16)

    def test_trace_id_unique_per_request(self):
        """每个请求生成不同的 trace_id"""
        client = self._make_client()
        r1 = client.get("/")
        r2 = client.get("/")
        assert r1.headers["X-Trace-ID"] != r2.headers["X-Trace-ID"]

    def test_trace_id_available_in_handler(self):
        """trace_id 在请求处理函数中可通过 contextvar 获取"""
        client = self._make_client()
        response = client.get("/", headers={"X-Trace-ID": "testtrace001"})
        assert response.json()["trace_id"] == "testtrace001"


class TestTraceIDLogFilter:
    """TraceID 日志过滤器测试"""

    def test_filter_adds_trace_id_to_record(self):
        """过滤器将 trace_id 添加到日志记录"""
        token = trace_id_ctx.set("logtest12345")
        try:
            filt = TraceIDLogFilter()
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="test message",
                args=None,
                exc_info=None,
            )
            filt.filter(record)
            assert hasattr(record, "trace_id")
            assert record.trace_id == "logtest12345"
        finally:
            trace_id_ctx.reset(token)

    def test_filter_without_trace_id(self):
        """无 trace_id 时 filter 不报错"""
        token = trace_id_ctx.set("")
        try:
            filt = TraceIDLogFilter()
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="test message",
                args=None,
                exc_info=None,
            )
            result = filt.filter(record)
            assert result is True
        finally:
            trace_id_ctx.reset(token)
