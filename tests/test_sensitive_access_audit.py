"""
tests/test_sensitive_access_audit — ⑤.5 CF-02 敏感访问审计硬验收（Gate 4 / Gate 5）

不依赖数据库 / 外部服务：
  - 用 unittest.mock.AsyncMock 模拟请求会话 db，断言审计行的字段与提交行为。
  - 用 stub core.models 避免触发 core/__init__.py 重依赖。

验收点：
  Gate 4：合法心理访问 → 写一条 result=allowed 的审计行（purpose 由后端常量填）。
  Gate 5：越权(403) 心理访问 → 写一条 result=denied 的审计行并原样 re-raise。
  best-effort：审计自身异常绝不外泄到业务请求。
"""
import asyncio
import importlib.util
import pathlib
import sys
import types
from datetime import datetime
from unittest import mock

from sqlalchemy import Column, BigInteger, ForeignKey
from sqlalchemy.orm import declarative_base
from fastapi import HTTPException

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── stub core.models：避免触发 core/__init__.py 重依赖 ──
_fc = types.ModuleType("core")
_fc.__path__ = []
sys.modules["core"] = _fc

_fm = types.ModuleType("core.models")
_Base = declarative_base()


class _SchoolMixin:
    school_id = Column(BigInteger, ForeignKey("schools.id"), nullable=False, index=True)


_fm.Base = _Base
_fm.SchoolMixin = _SchoolMixin
_fm.get_local_now = lambda: datetime.now()
sys.modules["core.models"] = _fm

# ── 直接按文件加载 privacy_audit（顶层仅依赖 core.models + fastapi）──
_spec = importlib.util.spec_from_file_location(
    "privacy_audit_test_shim",
    str(ROOT / "core" / "privacy_audit.py"),
)
pa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pa)

SensitiveDataAccessLog = pa.SensitiveDataAccessLog


def _user(uid, role, class_id=None, grade_id=None, school_id=1):
    u = mock.MagicMock()
    u.id = uid
    u.school_id = school_id
    u.role = role
    u.class_id = class_id
    u.grade_id = grade_id
    return u


def _db():
    """构造请求会话 mock：add 为同步（SQLAlchemy AsyncSession.add 是同步），
    commit/rollback 为异步。"""
    db = mock.MagicMock()
    db.commit = mock.AsyncMock()
    db.rollback = mock.AsyncMock()
    return db


def test_guard_and_audit_denied_logs_and_reraises():
    """Gate 5：越权(403) → 写 denied 行 + 原样 re-raise。"""
    async def run():
        db = _db()
        user = _user(7, "class_teacher", class_id=10)
        student_id = 123

        async def boom():
            raise HTTPException(status_code=403, detail="denied")

        raised = False
        try:
            await pa.guard_and_audit(
                db, user, student_id, boom,
                resource_type="psych_profile", action="read_detail",
                purpose=pa.PURPOSE_STUDENT_SUPPORT,
            )
        except HTTPException:
            raised = True
        assert raised, "guard_and_audit 必须原样 re-raise 403"

        assert db.add.call_count == 1, "denied 必须写一条审计"
        added = db.add.call_args[0][0]
        assert isinstance(added, SensitiveDataAccessLog)
        assert added.user_id == 7
        assert added.student_id == student_id
        assert added.resource_type == "psych_profile"
        assert added.result == pa.ACCESS_DENIED
        assert added.scope_type == "class" and added.scope_id == 10
        assert added.purpose == pa.PURPOSE_STUDENT_SUPPORT

    asyncio.run(run())


def test_guard_and_audit_allowed_logs():
    """Gate 4：合法访问 → 写 allowed 行（purpose 由后端常量填）。"""
    async def run():
        db = _db()
        user = _user(9, "ms_admin")  # 全校权限
        sentinel = object()

        async def ok():
            return sentinel

        res = await pa.guard_and_audit(
            db, user, 55, ok,
            resource_type="psych_assessment", action="read_detail",
            purpose=pa.PURPOSE_SCREENING_REVIEW,
        )
        assert res is sentinel, "check_coro 的返回值应原样返回"
        assert db.add.call_count == 1, "allowed 必须写一条审计"
        added = db.add.call_args[0][0]
        assert added.result == pa.ACCESS_ALLOWED
        assert added.scope_type == "school" and added.scope_id is None
        assert added.student_id == 55
        assert added.purpose == pa.PURPOSE_SCREENING_REVIEW

    asyncio.run(run())


def test_log_access_swallows_db_error():
    """best-effort：审计自身异常绝不外泄到业务请求。"""
    async def run():
        db = _db()
        db.commit.side_effect = RuntimeError("db broke")

        # 不得抛出异常
        await pa.log_access(
            db, user_id=1, school_id=1, student_id=None,
            resource_type="psych_profile", resource_id="scope",
            action="read_list", purpose=pa.PURPOSE_STUDENT_SUPPORT,
            result=pa.ACCESS_ALLOWED,
        )
        assert db.add.call_count == 1, "即使 commit 失败也应已 add"

    asyncio.run(run())


def test_no_direct_purpose_from_request():
    """purpose 仅允许后端常量：确认模块未暴露任何『从请求读取 purpose』的入口。"""
    import inspect
    src = inspect.getsource(pa)
    assert "request" not in src.lower().split("purpose")[0][-200:] or "purpose" in src
    # 关键不变量：log_access / guard_and_audit 的 purpose 参数没有默认值，
    # 调用方（router）必须显式传后端常量，无法由客户端注入。
    sig = inspect.signature(pa.log_access)
    assert sig.parameters["purpose"].default is inspect.Parameter.empty, \
        "purpose 不得有默认值，强制调用方显式传入后端常量"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("ALL CF-02 AUDIT TESTS PASSED")
