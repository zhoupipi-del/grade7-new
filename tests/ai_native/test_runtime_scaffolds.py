"""
tests/ai_native/test_runtime_scaffolds.py — Phase E 待办 scaffold

B1 Schema Implementation 阶段仅锁 schema；以下 9 项 Runtime Invariant 由 Phase E
接入运行时后补全测试文件（Inv 2/8/11/13/14/15/18/21/27）：
  * test_tenant_context.py          (Inv 2)
  * test_unknown_commit_recovery.py  (Inv 8)
  * test_runtime_psych_audit.py     (Inv 11 runtime)
  * test_tool_descriptor_contract.py (Inv 13/15)
  * test_scope_intersection.py      (Inv 14)
  * static-scan/review gate          (Inv 18)
  * tests/ai_native/test_runtime_provider_currency.py (Inv 21 runtime)
  * tool_executor call_seq          (Inv 27 runtime)

★ 每条 Runtime Invariant 必须 pytest.skip；B1 报告口径明确为
  SCHEMA_CONTRACT=PASS / RUNTIME_CONTRACT=DEFERRED。
  禁止把 pytest.skip 计为 PASS。
"""

from __future__ import annotations

import pytest


class TestInv2RuntimeTenantWhere:
    """Inv 2: tenant query 带 WHERE school_id — Runtime。"""

    def test_runtime_pending(self):
        pytest.skip(
            "Phase E 必补：所有 ai_native.* Service 的查询走 ResourceScopeResolver，"
            "WHERE school_id IN (access_scope)；覆盖单校/跨校聚合"
        )


class TestInv8UnknownCommitNoRetry:
    """Inv 8: UNKNOWN_COMMIT 不允许自动 retry — Runtime。"""

    def test_runtime_pending(self):
        pytest.skip(
            "Phase E 必补：test_unknown_commit_recovery.py — ToolExecutor 断言"
            "Tool.status == 'UNKNOWN_COMMIT' 时不调用 retry()；只走 reconciliation"
        )


class TestInv11PsychSensitiveNotInAuditRuntime:
    """Inv 11 Runtime: psych_sensitive 原文不进永久 Audit payload。"""

    def test_runtime_pending(self):
        pytest.skip(
            "Phase E 必补：写入 ai_execution_snapshots.classification_peak 时，"
            "若 Run 实际接触 psych_sensitive（taint 升级），应正确标记；"
            "且 psych 原文不应出现在 *_refs / argument_hashes / scope_snapshot"
        )


class TestInv13ClassificationMonotonic:
    """Inv 13: Tool actual_classification 可升级不可降级 — Runtime。"""

    def test_runtime_pending(self):
        pytest.skip(
            "Phase E 必补：test_tool_descriptor_contract.py — TaintLogic 断言"
            "actual > declared 时升级 Run.data_classification，且不可降级；"
            "Pydantic Validator 拒绝 'downgrade' 调用"
        )


class TestInv14ClassSummaryNoPII:
    """Inv 14: read_class_grade_summary 输出不含 student_id/name — Runtime。"""

    def test_runtime_pending(self):
        pytest.skip(
            "Phase E 必补：test_scope_intersection.py + Pydantic OutputSchema 断言"
            "read_class_grade_summary 输出 schema 仅含聚合字段（avg/std_dev/分布）；"
            "无 student_id/student_name/个人成绩"
        )


class TestInv15ToolDescriptorRequiredFields:
    """Inv 15: ToolDescriptor 必须声明 action/side_effect/required_scope — Runtime。"""

    def test_runtime_pending(self):
        pytest.skip(
            "Phase E 必补：test_tool_descriptor_contract.py — ToolDescriptor 注册时"
            "校验 action / side_effect / required_scope / declared_output_classification /"
            "allowed_input_classification 必填；缺失即注册失败"
        )


class TestInv18HashNotReversible:
    """Inv 18: payload_hash_sha256 仅一致性/绑定，**不可逆** — Runtime/语义。"""

    def test_runtime_pending(self):
        pytest.skip(
            "Phase E 必补：code review 保证 + 静态扫描禁止任何 reverse_hash / "
            "decrypt_from_hash 类工具函数；payload_hash_sha256 仅用于 Approval binding "
            "一致性校验"
        )


class TestInv21RuntimeProviderExplicit:
    """Inv 21 Runtime: Provider Adapter 必填 cost_currency（DB 层已无静默默认）。"""

    def test_runtime_pending(self):
        pytest.skip(
            "Phase E 必补：DeepSeekProvider / BGE-M3 / PaddleOCR Adapter 在写入"
            "ai_model_calls 时强制传 cost_currency；若空则 raise，不静默默认"
        )


class TestInv27RuntimeMonotonic:
    """Inv 27 Runtime: call_seq 单调自增（DB UNIQUE 已验；Runtime 由 Phase E 补）。"""

    def test_runtime_pending(self):
        pytest.skip(
            "Phase E 必补：ToolExecutor 写入 ai_model_calls 时 call_seq 自增；"
            "同一 Run 内连续两次 INSERT 的 call_seq 必须严格递增"
        )