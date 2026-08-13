"""
tests/test_privacy_gateway — ⑤.5 CF-03 网关硬验收（Gate 6 / Gate 7）

不依赖任何外部 Provider / 数据库：通过注入 FakeProvider 验证 Gateway 的合规模不变式。
CI 必须失败任何绕过 Gateway 的业务模块直连（test_no_bypass_in_ai_prescription）。
"""
import importlib.util
import pathlib
import sys

# 让仓库根进入 sys.path，便于解析 ai_native 等顶层包
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 直接按文件加载 privacy_gateway，避免触发 core/__init__.py（其依赖 sqlalchemy）。
# 该模块顶层仅依赖 ai_native.governance.data_classification（stdlib），DeepSeekProvider 为懒加载。
_spec = importlib.util.spec_from_file_location(
    "privacy_gateway_test_shim",
    str(ROOT / "core" / "privacy_gateway.py"),
)
pg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pg)
PrivacyGateway = pg.PrivacyGateway
make_student_ref = pg.make_student_ref
PRIVACY_POLICY_VERSION = pg.PRIVACY_POLICY_VERSION


class _FakeProvider:
    """记录调用、返回固定 content，不触网。"""

    def __init__(self):
        self.calls = []
        self.model = "deepseek-chat"

    def call(self, messages, *, timeout=60, json_mode=False, temperature=0.3,
             max_tokens=2048, model=None):
        self.calls.append((messages, dict(timeout=timeout, json_mode=json_mode)))
        return '{"ok": true}', None


def test_student_ref_stable_and_opaque():
    a = make_student_ref(1, 123, "psych", "secret")
    b = make_student_ref(1, 123, "psych", "secret")
    c = make_student_ref(1, 124, "psych", "secret")
    assert a == b, "同输入必须稳定"
    assert a != c, "不同学生必须不同"
    assert a.startswith("stu_") and len(a) == 20, "stu_<16 hex>"
    assert "123" not in a, "不得含原始 student_id"
    # 跨 scope 不同
    assert make_student_ref(1, 123, "psych", "secret") != make_student_ref(1, 123, "grade", "secret")


def test_gateway_blocks_psych_sensitive():
    """Gate 6：psych_sensitive payload 绝不触达 Provider。"""
    fake = _FakeProvider()
    gw = PrivacyGateway(provider=fake)
    messages = [
        {"role": "system", "content": "x"},
        {"role": "user", "content": "姓名：张三 心理档案：风险红色 筛查记录：总分"},
    ]
    content, audit = gw.call(messages, data_classification="psych_sensitive")
    assert content is None
    assert audit["blocked"] is True
    assert fake.calls == [], "provider 绝不能被调用"
    assert audit["policy_version"] == PRIVACY_POLICY_VERSION
    assert ("psych_details" in audit["fields_blocked"]
            or "name" in audit["fields_blocked"]
            or "psych_screening" in audit["fields_blocked"])


def test_gateway_strips_pii_for_internal():
    """Gate 6：非 psych 调用，外发前 PII 被脱敏。"""
    fake = _FakeProvider()
    gw = PrivacyGateway(provider=fake)
    payload = {"name": "张三", "phone": "13800000000", "summary": "出勤率0.9", "student_id": 123}
    clean, audit = gw.sanitize(payload, school_id=1, student_id=123)
    assert "name" not in clean and "phone" not in clean
    assert clean.get("student_ref", "").startswith("stu_")
    assert "name" in audit["fields_blocked"] and "phone" in audit["fields_blocked"]

    content, audit2 = gw.call(
        [{"role": "user", "content": "姓名：张三 联系13800000000 学号：12345"}],
        data_classification="internal",
    )
    assert content is not None
    sent = fake.calls[-1][0][0]["content"]
    assert "[NAME]" in sent and "[PHONE]" in sent and "[STU_REF]" in sent, (
        f"外发 payload 不得含原始姓名/手机号/学号：{sent}"
    )
    assert "张三" not in sent and "13800000000" not in sent and "12345" not in sent
    assert "phone" in audit2["fields_blocked"] and "name" in audit2["fields_blocked"]


def test_gateway_fails_closed_on_psych_in_text():
    """Gate 7：文本中 BLOCK 级敏感字段 → fields_blocked 可追溯，调用被阻断。"""
    fake = _FakeProvider()
    gw = PrivacyGateway(provider=fake)
    content, audit = gw.call(
        [{"role": "user", "content": "咨询记录：危机干预 自伤风险高"}],
        data_classification="internal",  # 误标，文本扫描仍须捕获
    )
    assert content is None
    assert audit["blocked"] is True
    assert ("consultation_text" in audit["fields_blocked"]
            or "crisis_metadata" in audit["fields_blocked"]), \
        f"阻断字段须在 fields_blocked 可追溯：{audit['fields_blocked']}"


def test_no_bypass_in_ai_prescription():
    """CF-03 硬纪律：ai_prescription 模块不得直连 DeepSeekProvider。"""
    base = ROOT / "modules" / "ai_prescription"
    banned = ("from core.deepseek_provider import", "DeepSeekProvider(", "_deepseek =")
    for f in base.glob("*.py"):
        text = f.read_text(encoding="utf-8")
        for b in banned:
            assert b not in text, f"{f.name} 仍直连 Provider（违反 CF-03 Gateway 纪律）：{b!r}"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
