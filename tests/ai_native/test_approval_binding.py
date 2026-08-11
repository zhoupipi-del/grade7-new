"""
tests/ai_native/test_approval_binding.py — Inv 4/5/25

★ Inv 4:  ai_approvals.tool_call_id 非空
★ Inv 5:  ai_command_envelopes.tool_call_id 类型与 ai_tool_calls.id 一致
★ Inv 25: approvals / envelopes 不得跨 school 引用 tool_call
"""

from __future__ import annotations

import pytest

from tests.ai_native.conftest import (
    all_ai_fks,
    fk_constraint_columns,
    fk_referred_columns,
    raw_info_schema_columns,
)


class TestInv4ApprovalToolCallNotNull:
    """Inv 4: ai_approvals.tool_call_id 非空。"""

    def test_approvals_tool_call_id_not_null(self, engine):
        rows = raw_info_schema_columns(engine, "ai_approvals")
        c = next(r for r in rows if r["COLUMN_NAME"] == "tool_call_id")
        assert c["IS_NULLABLE"] == "NO"


class TestInv5EnvelopeToolCallType:
    """Inv 5: ai_command_envelopes.tool_call_id 类型与 ai_tool_calls.id 一致。"""

    def test_envelope_tool_call_id_matches(self, engine):
        env = raw_info_schema_columns(engine, "ai_command_envelopes")
        env_c = next(r for r in env if r["COLUMN_NAME"] == "tool_call_id")
        tc = raw_info_schema_columns(engine, "ai_tool_calls")
        tc_c = next(r for r in tc if r["COLUMN_NAME"] == "id")
        assert env_c["COLUMN_TYPE"] == tc_c["COLUMN_TYPE"]

    def test_envelope_tool_call_id_not_null(self, engine):
        rows = raw_info_schema_columns(engine, "ai_command_envelopes")
        c = next(r for r in rows if r["COLUMN_NAME"] == "tool_call_id")
        assert c["IS_NULLABLE"] == "NO"


class TestInv25CrossSchoolCompositeFKShape:
    """Inv 25: approvals / envelopes 跨 school 引用 tool_call 由 composite FK 阻断。

    ★ 不再只断言"FK 存在"。每条 FK 必须满足：
        constrained = ["school_id", "tool_call_id"]
        referred    = ["school_id", "id"]
        DELETE_RULE  = "RESTRICT"
    """

    @pytest.mark.parametrize(
        "child", ["ai_approvals", "ai_command_envelopes"],
    )
    def test_composite_fk_full_shape(self, engine, child):
        fks = all_ai_fks(engine)
        matches = [
            fk for fk in fks
            if fk["TABLE_NAME"].lower() == child
            and fk["REFERENCED_TABLE_NAME"].lower() == "ai_tool_calls"
        ]
        assert matches, f"{child} → ai_tool_calls FK 缺失"
        good = [
            fk for fk in matches
            if fk["constrained_columns"] == ["school_id", "tool_call_id"]
            and fk["referred_columns"] == ["school_id", "id"]
            and fk["DELETE_RULE"] == "RESTRICT"
        ]
        assert good, (
            f"{child} → ai_tool_calls 找不到完整 composite shape：\n"
            + "\n".join(
                f"  {fk['CONSTRAINT_NAME']}: constrained={fk['constrained_columns']}, "
                f"referred={fk['referred_columns']}, DELETE_RULE={fk['DELETE_RULE']}"
                for fk in matches
            )
        )

    def test_cross_school_approval_insert_rejected(
        self, db_session, cross_school_setup,
    ):
        """★ 行为证明：(school B, Run B, ToolCall A) → IntegrityError。
        run FK 合法，tool_call FK 跨 school —— 精准证明 Inv 25。"""
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        setup = cross_school_setup
        with pytest.raises(IntegrityError):
            db_session.execute(
                text(
                    """
                    INSERT INTO ai_approvals
                      (school_id, run_id, tool_call_id,
                       tool_name, tool_version, schema_version,
                       policy_version, role_profile_version,
                       arguments_hash, resource_scope,
                       decision, expiry_at)
                    VALUES
                      (:school_b, :run_b, :tool_call_a,
                       'test_tool', '1.0.0', '1.0.0',
                       '1.0.0', '1.0.0',
                       :ah, JSON_OBJECT(),
                       'PENDING', :expiry_at)
                    """
                ),
                {
                    "school_b": setup["school_b"],
                    "run_b": setup["run_b_id"],
                    "tool_call_a": setup["tool_call_id"],
                    "ah": "x" * 64,
                    "expiry_at": setup["expiry_at"],
                },
            )
            db_session.flush()


class TestApprovalVersionBindingChain:
    """approvals 版本绑定链字段必建。"""

    @pytest.mark.parametrize(
        "col",
        [
            "tool_name", "tool_version", "schema_version",
            "policy_version", "role_profile_version",
            "arguments_hash", "resource_scope",
        ],
    )
    def test_approvals_required_columns_present(self, engine, col):
        rows = raw_info_schema_columns(engine, "ai_approvals")
        names = {r["COLUMN_NAME"].lower() for r in rows}
        assert col in names