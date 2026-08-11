"""
ai_native.models.ai_model_calls — LLM 调用明细（计费 + 完整审计）

v3.2 FINAL frozen. 锚定 Inv 3/5/6/10/19/20/21/23/24/25/26/27。

★ UNIQUE(school_id, run_id, call_seq) — Inv 27：同 tenant+Run 内 call_seq
  唯一且单调递增（DB 唯一 + Runtime 单调自增）。
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    DECIMAL,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import CHAR, ENUM, INTEGER

from core.models import Base


# model_call.call_type 4 态（v3.2 FINAL frozen）
MODEL_CALL_TYPES = ("chat", "embedding", "vision", "rerank")


class AiModelCalls(Base):
    """LLM 调用明细。"""

    __tablename__ = "ai_model_calls"

    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)

    school_id = Column(BigInteger, nullable=False)
    run_id = Column(BigInteger, nullable=False)
    tool_call_id = Column(
        BigInteger, nullable=True,
        comment="FK → ai_tool_calls.id；非 Tool 触发的直调为 NULL",
    )

    # Run 内调用序号（Inv 27）
    call_seq = Column(
        INTEGER(unsigned=True), nullable=False, server_default=text("1"),
        comment="Run 内调用序号",
    )

    # ── Provider / Model（Inv 21）──────────────────────
    provider = Column(
        String(50), nullable=False,
        comment="deepseek / local-bge / paddleocr",
    )
    model = Column(
        String(80), nullable=False,
        comment="禁写 deepseek-chat；用 deepseek-v4-flash / deepseek-v4-pro / bge-m3",
    )
    call_type = Column(
        ENUM(*MODEL_CALL_TYPES), nullable=False,
        comment=f"值域 {MODEL_CALL_TYPES}",
    )

    # ── Capability Router 审计字段 ─────────────────────
    preferred_wire_format = Column(
        String(30), nullable=True, comment="chat_completions / responses_api",
    )
    actual_wire_format = Column(
        String(30), nullable=True, comment="fallback 时与 preferred 不同",
    )
    prompt_hash = Column(String(64), nullable=True, comment="prompt SHA-256（不存原文）")
    completion_hash = Column(
        String(64), nullable=True,
        comment="completion SHA-256；可 NULL（流式中断，Inv 6）",
    )
    reasoning_level = Column(
        String(20), nullable=True, comment="none/low/medium/high",
    )
    reasoning_effort = Column(
        String(16), nullable=True,
        comment="none/low/medium/high/max（非 INT，Inv 20）",
    )
    reasoning_tokens = Column(
        INTEGER(unsigned=True), nullable=True,
        comment="Provider 返回 reasoning token 数（只存数值，不存 content）",
    )
    data_classification_at_call = Column(
        String(30), nullable=False,
        comment="调用时刻数据等级（小写，Inv 23）",
    )
    error_kind = Column(
        String(50), nullable=True,
        comment="rate_limit/context_overflow/timeout/content_filter/empty_response/unknown",
    )

    # ── 计费（跨 Provider 通用，Inv 21）────────────────
    prompt_tokens = Column(INTEGER(unsigned=True), nullable=False, server_default=text("0"))
    completion_tokens = Column(
        INTEGER(unsigned=True), nullable=False, server_default=text("0"),
    )
    total_tokens = Column(
        INTEGER(unsigned=True), nullable=False, server_default=text("0"),
    )
    cost_amount = Column(
        DECIMAL(10, 6), nullable=False, server_default=text("0"),
        comment="费用金额（跨币种通用）",
    )
    cost_currency = Column(
        CHAR(3), nullable=False,
        comment="ISO 4217；Provider Adapter 显式写入，无静默默认值（Inv 21）",
    )

    # ── 时间 ───────────────────────────────────────────
    latency_ms = Column(INTEGER(unsigned=True), nullable=True, server_default=text("0"))
    request_sent_at = Column(DateTime, nullable=True)
    response_received_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        # Inv 27: UNIQUE(school_id, run_id, call_seq)
        UniqueConstraint(
            "school_id", "run_id", "call_seq", name="uq_model_call_seq",
        ),
        # composite tenant FK: (school_id, run_id) → ai_runs
        ForeignKeyConstraint(
            ["school_id", "run_id"],
            ["ai_runs.school_id", "ai_runs.id"],
            name="fk_ai_model_calls_run",
            ondelete="RESTRICT",
        ),
        # composite tenant FK: (school_id, tool_call_id) → ai_tool_calls（nullable）
        ForeignKeyConstraint(
            ["school_id", "tool_call_id"],
            ["ai_tool_calls.school_id", "ai_tool_calls.id"],
            name="fk_ai_model_calls_tool_call",
            ondelete="RESTRICT",
        ),
        Index(
            "idx_ai_model_calls_school_run",
            "school_id", "started_at",
        ),
        Index("idx_ai_model_calls_provider_model", "provider", "model"),
        Index("idx_ai_model_calls_tool_call", "tool_call_id"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )