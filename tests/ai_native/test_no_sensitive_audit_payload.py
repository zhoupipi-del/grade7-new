"""
tests/ai_native/test_no_sensitive_audit_payload.py — Inv 10/11/12/16/17/18

★ Inv 10: ExecutionSnapshot 无明文 payload（refs JSON 引用链替代 LONGBLOB）
★ Inv 11: psych_sensitive 不进永久 Audit payload（schema 层仅校验
  classification_peak NOT NULL；runtime 验证 psych 原文不进入 refs/argument_hashes
  仍属 Phase E contract）
★ Inv 12: Retrieval 不存 query 原文 / raw chunk text
★ Inv 16: ai_runs.error_message_hash 替代 error TEXT
★ Inv 17: ai_retrievals 无 query_text 字段
★ Inv 18: payload_hash_sha256 仅用于一致性校验（schema 锁 VARBINARY+BLOB 形态）
"""

from __future__ import annotations

import pytest

from tests.ai_native.conftest import (
    CANONICAL_AI_TABLE_COLUMNS,
    CANONICAL_AI_TABLES,
    actual_columns,
    raw_info_schema_columns,
)


# 全 9 表禁存的"明文敏感 payload"列名集合。
# 仅 ai_command_envelopes.payload_ciphertext 例外（加密 BLOB，非明文）。
FORBIDDEN_PLAINTEXT_COLUMNS = frozenset({
    "prompt", "completion", "prompt_text", "completion_text",
    "query_text", "chunk_text",
    "arguments", "arguments_json",
    "tool_output", "tool_output_text",
    "result", "result_text",
    "error", "error_message", "error_text",
    "stack_trace", "stacktrace",
    "raw_payload",
    "raw_query", "raw_psych_text", "psych_text", "student_raw_data",
    "raw_chunk_text",
})


class TestNoPlaintextAcrossAllNineTables:
    """★ 9 表全检（含 ai_command_envelopes，仅其 payload_ciphertext 例外）。"""

    @pytest.mark.parametrize("table", CANONICAL_AI_TABLES)
    def test_table_forbids_plaintext_columns(self, db_inspector, table):
        actual = actual_columns(db_inspector, table)
        forbidden = set(FORBIDDEN_PLAINTEXT_COLUMNS)
        # ai_command_envelopes 允许 payload_ciphertext（加密 BLOB，非明文）
        if table == "ai_command_envelopes":
            forbidden.discard("payload_ciphertext")
        bad = actual & forbidden
        assert not bad, (
            f"{table} 出现明文敏感列：{sorted(bad)}；"
            f"应改为 *_hash / *_summary / refs JSON 引用链"
        )

    def test_envelope_table_still_rejects_other_plaintext(self, db_inspector):
        """★ 单独确认 ai_command_envelopes 也受禁列检查（除 ciphertext 外）。"""
        actual = actual_columns(db_inspector, "ai_command_envelopes")
        forbidden = set(FORBIDDEN_PLAINTEXT_COLUMNS)
        forbidden.discard("payload_ciphertext")
        bad = actual & forbidden
        assert not bad, (
            f"ai_command_envelopes 出现明文敏感列（ciphertext 除外）：{sorted(bad)}"
        )


class TestInv12RetrievalNoQueryOrChunkText:
    """Inv 12: ai_retrievals 仅存 query_hash / chunk_id 引用，不存原文。"""

    def test_ai_retrievals_columns(self, engine):
        rows = raw_info_schema_columns(engine, "ai_retrievals")
        names = {r["COLUMN_NAME"].lower() for r in rows}
        # ★ 直白独立断言（不再有 or 漏洞）
        assert "query_text" not in names
        assert "query" not in names, (
            "ai_retrievals 不应有 'query' 列（用 query_hash）"
        )
        assert "chunk_text" not in names, (
            "ai_retrievals 不应有 chunk_text（正文按 chunk_id 实时回业务库读）"
        )
        assert "query_hash" in names
        assert {"candidate_chunk_ids", "returned_chunk_ids"}.issubset(names)


class TestInv16ErrorMessageHashOnly:
    """Inv 16: ai_runs 用 error_kind + error_message_hash，禁止裸 error TEXT。"""

    def test_ai_runs_columns(self, engine):
        rows = raw_info_schema_columns(engine, "ai_runs")
        names = {r["COLUMN_NAME"].lower() for r in rows}
        assert "error" not in names, (
            "ai_runs 不应有 'error' 列；使用 error_kind + error_message_hash"
        )
        assert "error_kind" in names
        assert "error_message_hash" in names


class TestInv10ExecutionSnapshotRefsOnly:
    """Inv 10: ai_execution_snapshots 用 refs JSON 引用链，不用 LONGBLOB payload。"""

    def test_snapshot_columns(self, engine):
        rows = raw_info_schema_columns(engine, "ai_execution_snapshots")
        names = {r["COLUMN_NAME"].lower() for r in rows}
        for forbidden in ("raw_payload", "payload", "prompt", "completion"):
            assert forbidden not in names
        for required in (
            "model_call_refs", "retrieval_refs", "approval_refs",
            "argument_hashes",
        ):
            assert required in names


class TestInv11ClassificationPeakRecordedSchemaOnly:
    """Inv 11: classification_peak 必填（schema 层契约；runtime 不进 psych 原文属 Phase E）。

    ★ B1 仅锁 DB schema；runtime 校验 psych_sensitive 原文不进入 refs /
    argument_hashes / scope_snapshot 由 Phase E 补：
      test_no_sensitive_audit_payload.py::TestRuntimePsychSensitiveNotLeaked
    """

    def test_snapshot_classification_peak_not_null(self, engine):
        rows = raw_info_schema_columns(engine, "ai_execution_snapshots")
        c = next(r for r in rows if r["COLUMN_NAME"] == "classification_peak")
        assert c["IS_NULLABLE"] == "NO"


class TestRuntimePsychSensitiveNotLeakedDeferred:
    """Inv 11 runtime 侧：psych 原文不进入永久 Audit（Phase E 必补）。"""

    def test_runtime_pending(self):
        pytest.skip(
            "Phase E 必补：写入 ai_execution_snapshots 时，若 Run 实际接触 "
            "psych_sensitive（taint 升级），classification_peak 应正确标记；"
            "且 psych 原文不应出现在 *_refs / argument_hashes / scope_snapshot。"
            "本测试需 mock ToolExecutor 写入路径。"
        )


class TestInv18PayloadHashColumnsSchema:
    """Inv 18: payload_hash_sha256 仅一致性/绑定，**不可逆**。

    ★ B1 阶段：schema 已强约束 VARBINARY(12)/VARBINARY(16)/BLOB 形态；
    Runtime 禁止把 hash 用作"还原 key"由 code review + 静态扫描保证（Phase E）。
    """

    def test_envelope_columns_present(self, engine):
        rows = raw_info_schema_columns(engine, "ai_command_envelopes")
        names = {r["COLUMN_NAME"].lower() for r in rows}
        for col in (
            "payload_ciphertext", "nonce", "auth_tag",
            "crypto_algorithm", "encryption_key_version",
            "payload_hash_sha256",
        ):
            assert col in names

    def test_nonce_varbinary_12(self, engine):
        rows = raw_info_schema_columns(engine, "ai_command_envelopes")
        c = next(r for r in rows if r["COLUMN_NAME"] == "nonce")
        # ★ 真验长度：COLUMN_TYPE 必须恰为 varbinary(12)
        assert c["COLUMN_TYPE"].lower() == "varbinary(12)", (
            f"nonce COLUMN_TYPE={c['COLUMN_TYPE']!r}, 应为 varbinary(12)"
        )

    def test_auth_tag_varbinary_16(self, engine):
        rows = raw_info_schema_columns(engine, "ai_command_envelopes")
        c = next(r for r in rows if r["COLUMN_NAME"] == "auth_tag")
        # ★ 真验长度：COLUMN_TYPE 必须恰为 varbinary(16)
        assert c["COLUMN_TYPE"].lower() == "varbinary(16)", (
            f"auth_tag COLUMN_TYPE={c['COLUMN_TYPE']!r}, 应为 varbinary(16)"
        )

    def test_payload_ciphertext_blob(self, engine):
        rows = raw_info_schema_columns(engine, "ai_command_envelopes")
        c = next(r for r in rows if r["COLUMN_NAME"] == "payload_ciphertext")
        # ★ 裸 BLOB（不带 display length）：COLUMN_TYPE 恰为 'blob'
        assert c["COLUMN_TYPE"].lower() == "blob", (
            f"payload_ciphertext COLUMN_TYPE={c['COLUMN_TYPE']!r}, 应为裸 blob"
        )