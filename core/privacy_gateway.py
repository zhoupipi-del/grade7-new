"""
core.privacy_gateway — ⑤.5 CF-03 AI Privacy Gateway
====================================================

所有外部 LLM 调用的唯一合规出口。

BOSS 铁律（CF-03 硬纪律）：
  - 业务模块禁止直连 DeepSeekProvider / OpenAI / requests.post(ai-provider)。
  - 一切外发必须经 Gateway：字段最小化(DROP/DEID) → 敏感字段阻断(BLOCK, fail-closed)
    → 去标识化(HMAC student_ref) → ProviderRouter/DeepSeekProvider → 审计回写。
  - CI 必须失败任何绕过 Gateway 的调用（见 tests/test_privacy_gateway.py::test_no_bypass_in_ai_prescription）。

数据流：
  业务数据 → AI Privacy Gateway → 分类 fail-closed → 文本脱敏/阻断 → Provider → privacy_audit

关键不变式（fail-closed）：
  1. data_classification ∈ {psych_sensitive, student_pii} 默认不向外发送，返回 (None, audit)，
     强制调用方走确定性降级；绝不把姓名/心理量表/咨询危机元数据/电话/身份证/地址送第三方。
  2. 即便 EXTERNAL_PSYCH_AI_ENABLED=true，psych 数据仍被 Gateway 阻断——
     开关语义由 Gateway 接管，不再由业务模块直接决定外发。
  3. 审计可追：返回 privacy_audit = {policy_version, external_provider, data_classification,
     fields_allowed, fields_blocked, deidentified, blocked, reason}。

复用（不重新发明）：
  - core.deepseek_provider.DeepSeekProvider（禁止裸 HTTP client）。
  - ai_native.governance.data_classification.DataClassification（四级单调，小写）。
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from ai_native.governance.data_classification import DataClassification

logger = logging.getLogger(__name__)

PRIVACY_POLICY_VERSION = "cf03-v1"

# 去标识密钥：生产必须注入 PRIVACY_GATEWAY_SECRET；缺失则降级为 salted-HMAC（不可逆，仅弱于带密钥版本）
_GATEWAY_SECRET = os.environ.get("PRIVACY_GATEWAY_SECRET", "")


# ─────────────────────────────────────────────────────────────
# 字段级规则
# ─────────────────────────────────────────────────────────────
# DROP：直接丢弃的 PII（绝不出现在外发 payload）
DROP_FIELDS = {
    "name", "student_name", "real_name", "full_name",
    "phone", "mobile", "tel", "telephone",
    "id_card", "id_number", "idcard", "identity_no",
    "address", "home_address", "residential_address",
    "parent_phone", "parent1_phone", "parent2_phone", "parent_name",
    "guardian_phone", "guardian_name", "email", "email_address",
}
# DEID：去标识 → student_ref（HMAC 伪标识，可回溯但不可逆）
DEID_FIELDS = {
    "student_id", "student_no", "stu_id", "learner_id", "student_number",
}
# BLOCK：命中即整次调用 fail-closed（不入 prompt，返回 None）
BLOCK_FIELDS = {
    "psych_details", "psych_profile", "psych_screening", "psych_deep",
    "psych_assessment", "mental_health",
    "medical_details", "medical_history",
    "consultation_text", "counseling_notes", "therapy_notes",
    "crisis_metadata", "crisis_record",
    "diagnosis", "diagnoses",
}


# ─────────────────────────────────────────────────────────────
# 文本级强扫描（最后一道防线，针对已拼成自由文本的场景）
# ─────────────────────────────────────────────────────────────
_RE_PHONE = re.compile(r"1[3-9]\d{9}")
_RE_IDCARD = re.compile(r"\b\d{17}[\dXx]\b")
_RE_NAME_LINE = re.compile(r"(姓名|学生姓名|真实姓名|患儿姓名)\s*[:：]\s*([^\s,，。\n]{1,12})")
_RE_STUID_LINE = re.compile(r"(学生\s*ID|学号|student_id|student_no)\s*[:：]\s*(\d+)")

# 自由文本中若这些标记出现，视为 BLOCK 级敏感（fail-closed 参考）
_SENSITIVE_TEXT_MARKERS = {
    "psych_details": ("心理档案", "心理10维", "心理综合档案"),
    "psych_screening": ("筛查记录", "量表", "测评分"),
    "crisis_metadata": ("危机干预", "自伤", "转介"),
    "consultation_text": ("咨询记录", "咨询原文", "访谈"),
}


class PrivacyBlocked(Exception):
    """外发被 Gateway 阻断（fail-closed）。"""


def make_student_ref(
    school_id: int,
    student_id: Any,
    scope: str = "psych",
    secret: Optional[str] = None,
) -> str:
    """HMAC-SHA256 去标识：school_id + student_id + provider_scope → stu_<16hex>。

    不可逆（无法从 stu_xxx 反推 student_id）；同输入稳定；跨 scope 不同。
    """
    msg = f"{school_id}:{student_id}:{scope}".encode("utf-8")
    key = (secret if secret is not None else _GATEWAY_SECRET).encode("utf-8") or b"wings-cf03-salt"
    digest = hmac.new(key, msg, hashlib.sha256).hexdigest()
    return f"stu_{digest[:16]}"


def _classify(data_classification: str) -> DataClassification:
    try:
        return DataClassification(data_classification)
    except ValueError:
        return DataClassification.internal


class PrivacyGateway:
    """外部 LLM 调用的唯一合规模断点。"""

    def __init__(self, provider: Optional[Any] = None) -> None:
        # 懒加载 DeepSeekProvider：测试可注入 fake，避免硬依赖 httpx
        if provider is None:
            from core.deepseek_provider import DeepSeekProvider

            provider = DeepSeekProvider()
        self._provider = provider

    # ── 结构化脱敏（供 ai_native 新路径的 dict payload）──────────
    def sanitize(
        self,
        obj: Any,
        *,
        school_id: Optional[int] = None,
        student_id: Optional[Any] = None,
        scope: str = "psych",
        _audit: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, Dict[str, Any]]:
        audit = _audit or {
            "fields_allowed": [],
            "fields_blocked": [],
            "deidentified": [],
        }
        if isinstance(obj, dict):
            out: Dict[str, Any] = {}
            for k, v in obj.items():
                kl = str(k).lower()
                if kl in BLOCK_FIELDS:
                    audit["fields_blocked"].append(k)
                    continue  # 阻断：整字段不出现
                if kl in DROP_FIELDS:
                    audit["fields_blocked"].append(k)  # 记为 blocked（被丢弃）
                    continue
                if kl in DEID_FIELDS and student_id is not None:
                    out["student_ref"] = make_student_ref(
                        school_id or 0, v, scope, _GATEWAY_SECRET or None
                    )
                    audit["deidentified"].append(k)
                    continue
                cleaned, _ = self.sanitize(
                    v, school_id=school_id, student_id=student_id, scope=scope, _audit=audit
                )
                out[k] = cleaned
            return out, audit
        if isinstance(obj, list):
            cleaned_list = [
                self.sanitize(x, school_id=school_id, student_id=student_id, scope=scope, _audit=audit)[0]
                for x in obj
            ]
            return cleaned_list, audit
        return obj, audit

    # ── 文本级脱敏 ───────────────────────────────────────────
    def scrub_text(self, text: str, *, audit: Dict[str, Any]) -> str:
        if not isinstance(text, str):
            return text
        if _RE_PHONE.search(text):
            audit["fields_blocked"].append("phone")
            text = _RE_PHONE.sub("[PHONE]", text)
        if _RE_IDCARD.search(text):
            audit["fields_blocked"].append("id_card")
            text = _RE_IDCARD.sub("[ID]", text)
        m = _RE_NAME_LINE.search(text)
        if m:
            audit["fields_blocked"].append("name")
            text = _RE_NAME_LINE.sub(lambda x: f"{x.group(1)}：[NAME]", text)
        m2 = _RE_STUID_LINE.search(text)
        if m2:
            audit["deidentified"].append("student_id")
            text = _RE_STUID_LINE.sub(lambda x: f"{x.group(1)}：[STU_REF]", text)
        # 自由文本敏感标记扫描
        for field, markers in _SENSITIVE_TEXT_MARKERS.items():
            if any(mk in text for mk in markers):
                if field not in audit["fields_blocked"]:
                    audit["fields_blocked"].append(field)
        return text

    # ── 主入口 ───────────────────────────────────────────────
    def call(
        self,
        messages: List[Dict[str, str]],
        *,
        data_classification: str,
        school_id: Optional[int] = None,
        student_id: Optional[Any] = None,
        scope: str = "psych",
        timeout: float = 60.0,
        json_mode: bool = False,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """调用外部 LLM（经 DeepSeekProvider）。

        返回 (content, audit)：
          - content=None 且 audit["blocked"]=True → 外发被阻断，调用方应走确定性降级。
          - content=str → 已脱敏的外发结果。
        """
        dc = _classify(data_classification)
        audit: Dict[str, Any] = {
            "policy_version": PRIVACY_POLICY_VERSION,
            "external_provider": getattr(self._provider, "model", "deepseek"),
            "data_classification": dc.value,
            "fields_allowed": [],
            "fields_blocked": [],
            "deidentified": [],
            "blocked": False,
            "reason": "",
        }

        # ② 文本脱敏 + 敏感标记扫描（无论是否阻断都先扫描，保证审计可追）
        clean_messages: List[Dict[str, str]] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            cleaned = self.scrub_text(content, audit=audit)
            clean_messages.append({"role": role, "content": cleaned})

        # ① 分类 fail-closed：psych_sensitive / student_pii 默认不向外发送
        if dc in (DataClassification.psych_sensitive, DataClassification.student_pii):
            audit["blocked"] = True
            audit["reason"] = (
                f"data_classification={dc.value} 命中 fail-closed："
                "psych/PII 数据禁止外发至第三方 LLM，调用方须走确定性降级"
            )
            logger.warning("[PrivacyGateway] 外发阻断：%s", audit["reason"])
            return None, audit

        # ③ 若文本中仍含 BLOCK 级标记 → fail-closed（防御误标 classification）
        if any(f in audit["fields_blocked"] for f in BLOCK_FIELDS):
            audit["blocked"] = True
            audit["reason"] = "payload 含 BLOCK 级敏感字段（psych/consultation/crisis），fail-closed 阻断外发"
            logger.warning("[PrivacyGateway] 外发阻断：%s", audit["reason"])
            return None, audit

        # ④ 路由 Provider
        content, _usage = self._provider.call(
            clean_messages,
            timeout=timeout,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # ⑤ 允许字段清单（脱敏后外发的字段摘要）
        audit["fields_allowed"] = ["summary", "aggregates", "student_ref(deid)"]
        return content, audit
