"""
ai_native.runtime.approval_gate — 最小 Approval Gate（FT-015）
================================================================

CommandEnvelope（AES-256-GCM）+ Approval 状态机 + ToolExecutor 强制执行点。

状态机:  PENDING → APPROVED | REJECTED | EXPIRED
绑定:    tool_name + canonical args hash + school_id + run_id（反 TOCTOU）
密钥:    AI_APPROVAL_ENVELOPE_KEY（独立安全域，不复用 JWT SECRET_KEY / 心理档案 key）
规则:    禁止默认批准；approval record missing / expired / rejected /
         envelope mismatch / tenant mismatch → 全部 fail-closed。
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select

ENVELOPE_TTL_SECONDS = 30 * 60      # 30min TTL（model 注释一致）
APPROVAL_TTL_SECONDS = 30 * 60
ENVELOPE_KEY_VERSION = "env-v1"


class ApprovalGateError(Exception):
    """审批门禁拒绝。message 即 fail-closed 原因。"""


def _env_key() -> bytes:
    """AI_APPROVAL_ENVELOPE_KEY → 32 字节 AES key。"""
    raw = os.environ.get("AI_APPROVAL_ENVELOPE_KEY", "")
    if not raw:
        raise ApprovalGateError("AI_APPROVAL_ENVELOPE_KEY 未设置")
    if len(raw) == 64:  # 32 bytes hex
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def args_hash(args: Any) -> str:
    """canonical 参数 SHA-256（approval 绑定 + 执行时重算对比）。"""
    return hashlib.sha256(_canonical_json(args).encode("utf-8")).hexdigest()


def _encrypt_payload(plain: str) -> Tuple[bytes, bytes, bytes]:
    """AES-256-GCM → (ciphertext, nonce(12), auth_tag(16))。"""
    aesgcm = AESGCM(_env_key())
    nonce = os.urandom(12)
    ct_and_tag = aesgcm.encrypt(nonce, plain.encode("utf-8"), None)
    return ct_and_tag[:-16], nonce, ct_and_tag[-16:]


class ApprovalGate:
    """Approval 最小闭环（async session）。

    用法（FT-015 验证 / 生产 services 接入共用）：
      gate = ApprovalGate(session, school_id)
      envelope_uuid, approval_id = await gate.create_envelope(...)
      await gate.approve(approval_id=..., approver_id=..., school_id=...)
      ok, reason = await gate.validate(run_id=..., tool_call_id=..., actual_args=...)
    """

    def __init__(self, session: Any, school_id: int) -> None:
        self.db = session
        self.school_id = school_id

    # ── 创建：envelope(加密) + approval(PENDING) ──────────────────────────
    async def create_envelope(
        self,
        *,
        run_id: int,
        user_id: int,
        tool_call_id: int,
        tool_name: str,
        tool_version: str,
        args: Dict[str, Any],
        risk_level: str = "high",
    ) -> Tuple[str, int]:
        from ai_native.models.ai_command_envelopes import AiCommandEnvelopes
        from ai_native.models.ai_approvals import AiApprovals

        now = datetime.utcnow()
        payload_json = _canonical_json({"tool": tool_name, "args": args})
        ct, nonce, tag = _encrypt_payload(payload_json)
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        a_hash = args_hash(args)

        envelope = AiCommandEnvelopes(
            envelope_uuid=str(uuid.uuid4()),
            school_id=self.school_id,
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_version=tool_version,
            schema_version="1",
            payload_ciphertext=ct,
            nonce=nonce,
            auth_tag=tag,
            crypto_algorithm="AES-256-GCM",
            encryption_key_version=ENVELOPE_KEY_VERSION,
            payload_hash_sha256=payload_hash,
            expires_at=now + timedelta(seconds=ENVELOPE_TTL_SECONDS),
        )
        self.db.add(envelope)

        approval = AiApprovals(
            school_id=self.school_id,
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_version=tool_version,
            schema_version="1",
            policy_version="1",
            role_profile_version="1",
            arguments_hash=a_hash,
            resource_scope={"risk_level": risk_level, "school_id": self.school_id},
            decision="PENDING",
            expiry_at=now + timedelta(seconds=APPROVAL_TTL_SECONDS),
        )
        self.db.add(approval)
        await self.db.flush()
        return envelope.envelope_uuid, approval.id

    # ── 决策：approve / reject（人工）──────────────────────────────────────
    async def _decide(self, *, approval_id: int, approver_id: int, school_id: int, decision: str) -> None:
        from ai_native.models.ai_approvals import AiApprovals

        approval = await self.db.get(AiApprovals, approval_id)
        if approval is None:
            raise ApprovalGateError("approval record missing")
        if approval.school_id != school_id:
            raise ApprovalGateError("approval tenant mismatch")
        if approval.decision != "PENDING":
            raise ApprovalGateError(f"approval not PENDING: {approval.decision}")
        if approval.expiry_at < datetime.utcnow():
            raise ApprovalGateError("approval expired")
        approval.decision = decision
        approval.approver_id = approver_id
        approval.decided_at = datetime.utcnow()
        await self.db.flush()

    async def approve(self, *, approval_id: int, approver_id: int, school_id: int) -> None:
        await self._decide(approval_id=approval_id, approver_id=approver_id,
                           school_id=school_id, decision="APPROVED")

    async def reject(self, *, approval_id: int, approver_id: int, school_id: int) -> None:
        await self._decide(approval_id=approval_id, approver_id=approver_id,
                           school_id=school_id, decision="REJECTED")

    # ── resume 支持：解密 envelope，恢复批准时的原始 args（HTTP E2E / services 用）──
    async def reveal_args(self, *, approval_id: int, school_id: int) -> Dict[str, Any]:
        """解密 envelope payload，返回批准时的原始 args（resume SAME run 用）。

        fail-closed：approval/envelope 缺失、tenant 不匹配、非 APPROVED、过期 → 拒绝。
        """
        from ai_native.models.ai_approvals import AiApprovals
        from ai_native.models.ai_command_envelopes import AiCommandEnvelopes

        approval = await self.db.get(AiApprovals, approval_id)
        if approval is None:
            raise ApprovalGateError("approval record missing")
        if approval.school_id != school_id:
            raise ApprovalGateError("approval tenant mismatch")
        if approval.decision != "APPROVED":
            raise ApprovalGateError(f"approval not approved: {approval.decision}")

        res = await self.db.execute(
            select(AiCommandEnvelopes).where(
                AiCommandEnvelopes.school_id == school_id,
                AiCommandEnvelopes.run_id == approval.run_id,
                AiCommandEnvelopes.tool_call_id == approval.tool_call_id,
            )
        )
        env = res.scalar_one_or_none()
        if env is None:
            raise ApprovalGateError("envelope missing")
        if env.expires_at < datetime.utcnow():
            raise ApprovalGateError("envelope expired")

        aesgcm = AESGCM(_env_key())
        try:
            plain = aesgcm.decrypt(
                env.nonce, env.payload_ciphertext + env.auth_tag, None
            ).decode("utf-8")
        except Exception:
            raise ApprovalGateError("envelope decrypt failed")
        payload = json.loads(plain)
        return payload.get("args", {})

    # ── 强制执行点：ToolExecutor 调用（fail-closed）────────────────────────
    async def validate(
        self,
        *,
        run_id: int,
        school_id: int,
        tool_call_id: int,
        actual_args: Any,
    ) -> Tuple[bool, str]:
        """校验：approval APPROVED + 未过期 + canonical args hash 匹配（反 TOCTOU）。"""
        from ai_native.models.ai_approvals import AiApprovals

        res = await self.db.execute(
            select(AiApprovals).where(
                AiApprovals.school_id == school_id,
                AiApprovals.run_id == run_id,
                AiApprovals.tool_call_id == tool_call_id,
            )
        )
        approval = res.scalar_one_or_none()
        if approval is None:
            return False, "approval record missing"
        if approval.decision != "APPROVED":
            return False, f"approval not approved: {approval.decision}"
        if approval.expiry_at < datetime.utcnow():
            return False, "approval expired"
        actual_hash = args_hash(actual_args)
        if actual_hash != approval.arguments_hash:
            return False, "APPROVAL_SCOPE_MISMATCH"
        return True, "ok"
