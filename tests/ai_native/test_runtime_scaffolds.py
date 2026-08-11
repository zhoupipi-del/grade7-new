"""
tests/ai_native/test_runtime_scaffolds.py — Phase E Runtime scaffold（Slice 1 RED GATE 后）

Slice 1 第一刀已建立真实测试文件的（对应 placeholder 删除，不再 skip）：
  * test_tenant_context.py            (Inv 2)
  * test_unknown_commit_recovery.py   (Inv 8)
  * test_tool_descriptor_contract.py  (Inv 13/15)
  * test_scope_intersection.py        (Inv 14)
  * test_runtime_provider_currency.py (Inv 21)
  * test_call_seq_runtime.py          (Inv 27)

仍保留 DEFERRED 的：
  * Inv 11 → DEFERRED（test_runtime_psych_audit.py，Slice 1 路径未触达 psych_sensitive）
  * Inv 18 → STATIC GATE / DEFERRED（code review + 静态扫描禁止 reverse_hash /
    decrypt_from_hash；不建真测试，走静态 gate 覆盖）

★ 报告口径：RUNTIME_CONTRACT = PARTIAL / IN PROGRESS（禁止写 PASS）。
   DEFERRED 项不得计为 PASS。
"""

from __future__ import annotations

import pytest


class TestInv11PsychSensitiveNotInAuditRuntime:
    """Inv 11 Runtime: psych_sensitive 原文不进永久 Audit payload — DEFERRED。"""

    def test_runtime_pending(self):
        pytest.skip(
            "DEFERRED（Slice 1 第一刀 read_class_grade_summary 不触达 psych_sensitive）："
            "写入 ai_execution_snapshots.classification_peak 时，若 Run 实际接触 "
            "psych_sensitive（taint 升级），应正确标记；且 psych 原文不应出现在 "
            "*_refs / argument_hashes / scope_snapshot"
        )


class TestInv18HashNotReversible:
    """Inv 18: payload_hash_sha256 仅一致性/绑定，**不可逆** — STATIC GATE / DEFERRED。"""

    def test_runtime_pending(self):
        pytest.skip(
            "STATIC GATE / DEFERRED：code review 保证 + 静态扫描禁止任何 reverse_hash / "
            "decrypt_from_hash 类工具函数；payload_hash_sha256 仅用于 Approval binding "
            "一致性校验"
        )
