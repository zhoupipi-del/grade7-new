"""
ai_native.models.ai_tool_calls — Tool 调用记录（★ 提前建，供子表 FK 引用）

v3.2 FINAL frozen. 锚定 Inv 1/3/7/8/9/10/13/15/19/24/26。

★ uq_toolcall_school (school_id, id) 是子表 (school_id, tool_call_id) 复合 FK
  的父键唯一约束（§0-C）。
★ UNKNOWN_COMMIT 是执行安全状态，代码层禁止自动 retry（Inv 8）。
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import ENUM, INTEGER, JSON

from core.models import Base


# Tool 状态机 7 态（v3.2 FINAL frozen；含 UNKNOWN_COMMIT，禁止新增 CANCELLED）
AI_TOOL_STATUSES = (
    "PENDING",
    "EXECUTING",
    "EXECUTED",
    "FAILED",
    "UNKNOWN_COMMIT",
    "AWAITING_APPROVAL",
    "DENIED",
)


class AiToolCalls(Base):
    """Tool 调用记录（提前建，供 model_calls / retrievals / approvals / envelopes FK 引用）。"""

    __tablename__ = "ai_tool_calls"

    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)

    school_id = Column(BigInteger, nullable=False, comment="租户冗余")
    run_id = Column(BigInteger, nullable=False, comment="FK → ai_runs.id（composite）")

    # ── Tool 标识 ──────────────────────────────────────
    tool_name = Column(String(100), nullable=False)
    tool_version = Column(String(20), nullable=False, comment="semver")
    schema_version = Column(String(20), nullable=False, comment="input_schema 版本")

    # ── 行为分类（Inv 15 必填）─────────────────────────
    action = Column(
        String(30), nullable=False, comment="read / write / delete / notify",
    )
    side_effect = Column(
        String(30), nullable=False, server_default=text("'none'"),
        comment="none / db_write / api_call / notification / file_write",
    )

    # ── 参数（不存原文；Inv 7/10）─────────────────────
    arguments_hash = Column(String(64), nullable=False, comment="参数 JSON SHA-256")
    idempotency_key = Column(
        String(64), nullable=False,
        comment="幂等键——崩溃恢复时防重复执行（Inv 7）",
    )

    # ── Scope（Inv 9）──────────────────────────────────
    resource_scope = Column(
        JSON, nullable=False,
        comment="ResourceScope 资源维度（请求 ∩ 授权）；无 student_id 裸列",
    )

    # ── 分类（Inv 13）──────────────────────────────────
    declared_output_classification = Column(
        String(30), nullable=False, comment="ToolDescriptor 声明的输出等级",
    )
    actual_output_classification = Column(
        String(30), nullable=True,
        comment="实际输出等级；可升不可降；不得因此降低 Run classification",
    )

    # ── Tool 状态机 7 态（Frozen ENUM，Inv 8）──────────
    status = Column(
        ENUM(*AI_TOOL_STATUSES),
        nullable=False,
        server_default=text("'PENDING'"),
        comment=f"Tool 状态机；值域 {AI_TOOL_STATUSES}；UNKNOWN_COMMIT 禁止自动 retry",
    )

    # ── 结果（不存原文）────────────────────────────────
    result_hash = Column(String(64), nullable=True, comment="结果 SHA-256")
    code_revision = Column(String(64), nullable=True, comment="Tool 代码版本指纹")

    # ── 恢复 / 重试 ────────────────────────────────────
    retry_count = Column(
        INTEGER(unsigned=True), nullable=False, server_default=text("0"),
    )
    reconciliation_attempted = Column(
        Boolean, nullable=False, server_default=text("false"),
    )
    error_kind = Column(String(50), nullable=True)

    # ── 时间 ───────────────────────────────────────────
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        # uq_toolcall_school: 父键复合 UNIQUE，供子表 (school_id, tool_call_id) 复合 FK 引用
        UniqueConstraint("school_id", "id", name="uq_toolcall_school"),
        # Inv 7: idempotency 唯一约束（每校 idempotency_key 全局唯一）
        UniqueConstraint(
            "school_id", "idempotency_key", name="uq_school_idempotency",
        ),
        # composite tenant FK: (school_id, run_id) → ai_runs(school_id, id) RESTRICT
        ForeignKeyConstraint(
            ["school_id", "run_id"],
            ["ai_runs.school_id", "ai_runs.id"],
            name="fk_ai_tool_calls_run",
            ondelete="RESTRICT",
        ),
        Index("idx_ai_tool_calls_run", "run_id"),
        Index("idx_ai_tool_calls_tool", "tool_name", "tool_version"),
        Index(
            "idx_ai_tool_calls_school_status",
            "school_id", "status", "started_at",
        ),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )