"""
tests/test_psych_capability — ⑤.5 CF-01 心理专业授权硬验收（核心逻辑）

不依赖数据库 / 外部服务，用 unittest.mock 模拟 db 与 user，断言
resolve_psych_access 的三层访问级别判定与 attention_payload 输出形态。

验收不变量（周主任 2026-08-13 冻结口径）：
  1. psych_authorized = active counselor TeacherRoleAssignment + scope，绝不回退 user.role/ms_admin
  2. detail   → 仅 counselor assignment
  3. attention → class_teacher(本班) / grade_leader(本年级)
  4. deny     → ms_admin / teacher / 跨 scope / parent / student
  5. not_found→ 跨校 / 不存在
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

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── stub core.models + core.access ──
_fc = types.ModuleType("core")
_fc.__path__ = []
sys.modules["core"] = _fc

_fm = types.ModuleType("core.models")
_Base = declarative_base()


class _SchoolMixin:
    school_id = Column(BigInteger, ForeignKey("schools.id"), nullable=False, index=True)


class _Student(_Base):
    __tablename__ = "students"
    id = Column(BigInteger, primary_key=True)
    school_id = Column(BigInteger)
    grade_id = Column(BigInteger)
    class_id = Column(BigInteger)


class _User:
    pass


_fm.Base = _Base
_fm.SchoolMixin = _SchoolMixin
_fm.Student = _Student
_fm.User = _User
sys.modules["core.models"] = _fm

_fa = types.ModuleType("core.access")


def _role_str(user):
    r = getattr(user, "role", None)
    if hasattr(r, "value"):
        r = r.value
    return (r or "").lower()


_fa.role_str = _role_str
sys.modules["core.access"] = _fa

# ── 加载 psych_capability ──
_spec = importlib.util.spec_from_file_location(
    "psych_capability_test_shim", str(ROOT / "core" / "psych_capability.py")
)
pa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pa)


def _user(uid, role, class_id=None, grade_id=None, school_id=1):
    u = mock.MagicMock()
    u.id = uid
    u.school_id = school_id
    u.role = role
    u.class_id = class_id
    u.grade_id = grade_id
    return u


def _student(sid, school_id=1, grade_id=1, class_id=1):
    s = _Student()
    s.id = sid
    s.school_id = school_id
    s.grade_id = grade_id
    s.class_id = class_id
    return s


async def _resolve(user, student, counselor_covers):
    db = mock.MagicMock()
    exec_res = mock.MagicMock()
    exec_res.scalar_one_or_none.return_value = student
    db.execute = mock.AsyncMock(return_value=exec_res)
    with mock.patch.object(
        pa, "_counselor_scope_covers", new=mock.AsyncMock(return_value=counselor_covers)
    ):
        return await pa.resolve_psych_access(db, user, student.id if student else 999)


def test_attention_payload_shape():
    p = pa.attention_payload(True)
    assert p["professional_followup_required"] is True
    assert p["detail_access"] is False
    assert p["recommended_action"] == "refer_to_psych_staff"
    # 绝不含任何详情字段
    for banned in ("scale_name", "score", "risk_factor", "consultation", "crisis", "notes"):
        assert banned not in p


def test_counselor_assignment_yields_detail():
    async def run():
        user = _user(9, "ms_admin")  # 即使 user.role=ms_admin，有 counselor assignment 也只看 assignment
        assert await _resolve(user, _student(1), counselor_covers=True) == pa.PSY_DETAIL
    asyncio.run(run())


def test_class_teacher_in_scope_yields_attention():
    async def run():
        user = _user(3, "class_teacher", class_id=1)
        assert await _resolve(user, _student(1, class_id=1), counselor_covers=False) == pa.PSY_ATTENTION
    asyncio.run(run())


def test_grade_leader_in_scope_yields_attention():
    async def run():
        user = _user(2, "grade_leader", grade_id=1)
        assert await _resolve(user, _student(1, grade_id=1), counselor_covers=False) == pa.PSY_ATTENTION
    asyncio.run(run())


def test_class_teacher_out_of_scope_yields_deny():
    async def run():
        user = _user(3, "class_teacher", class_id=1)
        assert await _resolve(user, _student(2, class_id=2), counselor_covers=False) == pa.PSY_DENY
    asyncio.run(run())


def test_ms_admin_yields_deny_without_assignment():
    async def run():
        user = _user(1, "ms_admin")  # ms_admin 默认无心理详情
        assert await _resolve(user, _student(1), counselor_covers=False) == pa.PSY_DENY
    asyncio.run(run())


def test_teacher_yields_deny():
    async def run():
        user = _user(8, "teacher", class_id=1)  # 任课教师连关注标记都没有
        assert await _resolve(user, _student(1, class_id=1), counselor_covers=False) == pa.PSY_DENY
    asyncio.run(run())


def test_cross_school_yields_not_found():
    async def run():
        user = _user(1, "ms_admin", school_id=1)
        assert await _resolve(user, None, counselor_covers=False) == pa.PSY_NOT_FOUND
    asyncio.run(run())


def test_counselor_scope_fail_closed_when_module_missing():
    """teacher_mgmt 未加载时，counselor 判定 fail-closed（返回 False，绝不放行）。"""
    async def run():
        db = mock.MagicMock()
        db.execute = mock.AsyncMock()
        # modules.teacher_mgmt.models 未被 stub → ImportError → False
        assert await pa._counselor_scope_covers(db, _user(1, "x"), _student(1)) is False
    asyncio.run(run())


async def _resolve_list(user, has_counselor):
    db = mock.MagicMock()
    with mock.patch.object(pa, "_has_counselor_assignment", new=mock.AsyncMock(return_value=has_counselor)):
        return await pa.resolve_psych_list_access(db, user)


def test_list_access_counselor_yields_detail():
    assert asyncio.run(_resolve_list(_user(9, "teacher"), has_counselor=True)) == pa.PSY_DETAIL


def test_list_access_class_teacher_yields_attention():
    assert asyncio.run(_resolve_list(_user(3, "class_teacher", class_id=1), has_counselor=False)) == pa.PSY_ATTENTION


def test_list_access_grade_leader_yields_attention():
    assert asyncio.run(_resolve_list(_user(2, "grade_leader", grade_id=1), has_counselor=False)) == pa.PSY_ATTENTION


def test_list_access_ms_admin_yields_deny():
    assert asyncio.run(_resolve_list(_user(1, "ms_admin"), has_counselor=False)) == pa.PSY_DENY


def test_list_access_teacher_yields_deny():
    assert asyncio.run(_resolve_list(_user(8, "teacher", class_id=1), has_counselor=False)) == pa.PSY_DENY


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("ALL CF-01 CAPABILITY TESTS PASSED")
