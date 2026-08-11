"""
tests/ai_native/test_composite_fk.py — Inv 24/26

★ Inv 24: 跨 AI Native 表引用必须 tenant-consistent
★ Inv 26: DB FK 阻止 cross-tenant relational mismatch

每条 FK 验证完整 shape：
  child columns   = ["school_id", "run_id"] 或 ["school_id", "tool_call_id"]
  referred columns = ["school_id", "id"]
  referred table   ∈ {"ai_runs", "ai_tool_calls"}
  DELETE_RULE      = "RESTRICT"
"""

from __future__ import annotations

import pytest

from tests.ai_native.conftest import (
    CANONICAL_AI_TABLES,
    EXPECTED_COMPOSITE_FKS,
    all_ai_fks,
    raw_info_schema_constraints,
)


class TestCompositeFKCount:
    """★ 12 条 composite tenant FK 数量与名单一致。"""

    def test_exactly_twelve_ai_internal_fks(self, engine):
        ai_internal = [
            r for r in raw_info_schema_constraints(engine)
            if r["TABLE_NAME"].lower() in CANONICAL_AI_TABLES
            and r["REFERENCED_TABLE_NAME"].lower() in {"ai_runs", "ai_tool_calls"}
        ]
        assert len(ai_internal) == 12, (
            f"期望 12 条 composite FK，实有 {len(ai_internal)}：\n"
            + "\n".join(
                f"  {r['TABLE_NAME']}.{r['CONSTRAINT_NAME']} → "
                f"{r['REFERENCED_TABLE_NAME']}"
                for r in ai_internal
            )
        )


class TestCompositeFKExactShape:
    """★ 每条 FK 完整 shape：constrained / referred / parent / DELETE_RULE。"""

    def _fk_by_shape(self, fks, child, parent):
        for fk in fks:
            if (fk["TABLE_NAME"].lower() == child
                    and fk["REFERENCED_TABLE_NAME"].lower() == parent):
                yield fk

    @pytest.mark.parametrize(
        "spec", EXPECTED_COMPOSITE_FKS, ids=lambda s: f"{s['child']}→{s['parent']}",
    )
    def test_one_fk_matches_spec_exact_shape(self, engine, spec):
        fks = all_ai_fks(engine)
        matches = list(self._fk_by_shape(
            fks, spec["child"], spec["parent"],
        ))
        # 至少存在 1 条完全匹配期望 shape
        good = [
            fk for fk in matches
            if fk["constrained_columns"] == spec["constrained"]
            and fk["referred_columns"] == spec["referred"]
            and fk["DELETE_RULE"] == "RESTRICT"
        ]
        assert len(good) >= 1, (
            f"{spec['child']} → {spec['parent']} 找不到形状匹配：\n"
            f"  期望 constrained={spec['constrained']}, "
            f"referred={spec['referred']}, DELETE_RULE=RESTRICT\n"
            f"  实际 candidates：\n"
            + "\n".join(
                f"    {fk['CONSTRAINT_NAME']}: "
                f"constrained={fk['constrained_columns']}, "
                f"referred={fk['referred_columns']}, "
                f"DELETE_RULE={fk['DELETE_RULE']}"
                for fk in matches
            )
        )

    def test_no_single_column_tenant_fk(self, engine):
        """★ 防御性：禁止任何 child.school_id → parent.id 的单列 FK（必须 composite）。"""
        for fk in all_ai_fks(engine):
            if fk["TABLE_NAME"].lower() not in CANONICAL_AI_TABLES:
                continue
            cols = fk["constrained_columns"]
            if "school_id" in cols:
                # 含 school_id 的 FK 必须是 composite（2 列）
                assert len(cols) == 2, (
                    f"{fk['TABLE_NAME']}.{fk['CONSTRAINT_NAME']} 含 school_id 但不是 composite："
                    f"constrained={cols}"
                )

    def test_no_fk_to_schools_or_users(self, engine):
        """§0-E: AI Native 9 表不 FK 到 schools / users（intentional）。"""
        for fk in all_ai_fks(engine):
            if fk["TABLE_NAME"].lower() not in CANONICAL_AI_TABLES:
                continue
            assert fk["REFERENCED_TABLE_NAME"].lower() not in {"schools", "users"}, (
                f"{fk['TABLE_NAME']}.{fk['CONSTRAINT_NAME']} 误 FK 到 "
                f"{fk['REFERENCED_TABLE_NAME']}"
            )


class TestCompositeFKBehaviorCrossTenant:
    """★ Inv 24/26 行为证明：跨 school INSERT 应被 DB 拒绝。

    隔离测试 DB 上：school A 建 Run A + ToolCall A；school B 建 Run B。
    攻击路径：以 (school_id=B, run_id=RunB, tool_call_id=ToolCallA) 插入
    approval/envelope —— run FK 合法、tool_call FK 跨 school →
    IntegrityError 精准证明 Inv25（而非先挂在 run FK）。
    """

    def test_cross_school_approval_insert_rejected(
        self, db_session, cross_school_setup,
    ):
        """(school B, Run B, ToolCall A) → composite FK (school_id, tool_call_id)
        → ai_tool_calls(school_id, id) 必拒绝（Inv 25）。"""
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

    def test_cross_school_envelope_insert_rejected(
        self, db_session, cross_school_setup,
    ):
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        setup = cross_school_setup
        with pytest.raises(IntegrityError):
            db_session.execute(
                text(
                    """
                    INSERT INTO ai_command_envelopes
                      (envelope_uuid, school_id, run_id, tool_call_id,
                       tool_name, tool_version, schema_version,
                       payload_ciphertext, nonce, auth_tag,
                       encryption_key_version, payload_hash_sha256,
                       created_at, expires_at)
                    VALUES
                      (:uuid, :school_b, :run_b, :tool_call_a,
                       'test_tool', '1.0.0', '1.0.0',
                       :blob, :nonce, :tag,
                       'v1', :hash,
                       :now, :expiry_at)
                    """
                ),
                {
                    "uuid": "x" * 36,
                    "school_b": setup["school_b"],
                    "run_b": setup["run_b_id"],
                    "tool_call_a": setup["tool_call_id"],
                    "blob": b"\x00" * 16,
                    "nonce": b"\x00" * 12,
                    "tag": b"\x00" * 16,
                    "hash": "x" * 64,
                    "now": setup["now"],
                    "expiry_at": setup["expiry_at"],
                },
            )
            db_session.flush()


class TestCompositeFKRuntimeMonotonicDeferred:
    """Inv 24/26 的 runtime 侧（service 层 WHERE school_id）由 Phase E 补全。"""

    def test_runtime_pending(self):
        pytest.skip(
            "Phase E 必补：test_tenant_isolation.py runtime — "
            "所有 ai_native.* Service 的 SELECT 走 WHERE school_id IN (access_scope)"
        )