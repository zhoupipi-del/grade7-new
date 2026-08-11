"""
ai_native.models.ai_retrievals — RAG 检索链路（Grounding 审计）

v3.2 FINAL frozen. 锚定 Inv 9/12/17/19/24/25/26。

★ 不存 query 原文，不存 chunk 正文（Inv 12/17）。
★ 正文始终从业务知识库按 school_id + ACL + chunk_id 重新读取。
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
    text,
)
from sqlalchemy.dialects.mysql import INTEGER, JSON

from core.models import Base


class AiRetrievals(Base):
    """RAG 检索链路（Grounding 审计）。"""

    __tablename__ = "ai_retrievals"

    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)

    school_id = Column(BigInteger, nullable=False)
    run_id = Column(BigInteger, nullable=False)
    tool_call_id = Column(BigInteger, nullable=True, comment="哪个 Tool 触发的检索")

    # ── 查询（不存原文，Inv 12/17）────────────────────
    query_hash = Column(String(64), nullable=False, comment="query SHA-256（不存原文）")

    # ── Embedding / VectorStore ────────────────────────
    embedding_provider = Column(String(50), nullable=False, comment="bge-m3")
    embedding_model = Column(String(80), nullable=False, comment="bge-m3-v1")
    vector_store = Column(String(50), nullable=False, comment="qdrant")
    index_version = Column(String(20), nullable=True)

    top_k = Column(INTEGER(unsigned=True), nullable=False, server_default=text("5"))

    # ── FINAL Grounding 审计字段 ───────────────────────
    candidate_chunk_ids = Column(JSON, nullable=False, comment="向量检索命中 chunk ID 列表")
    returned_chunk_ids = Column(JSON, nullable=False, comment="ACL 过滤后实际返回 chunk ID 列表")
    cosine_scores = Column(JSON, nullable=True, comment="与 returned_chunk_ids 对齐")
    threshold_passed = Column(
        Boolean, nullable=False, server_default=text("false"),
        comment="GroundingGate 相似度阈值是否通过",
    )
    rbac_filtered_count = Column(
        INTEGER(unsigned=True), nullable=False, server_default=text("0"),
    )
    qdrant_ranking_preserved = Column(
        Boolean, nullable=False, server_default=text("true"),
    )

    # ── 范围 ───────────────────────────────────────────
    resource_scope = Column(
        JSON, nullable=False,
        comment="{school_id, grade_id, class_id, student_id, subject_id}",
    )
    acl_filter = Column(JSON, nullable=True)

    latency_ms = Column(INTEGER(unsigned=True), nullable=True, server_default=text("0"))
    occurred_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        # composite tenant FK: run
        ForeignKeyConstraint(
            ["school_id", "run_id"],
            ["ai_runs.school_id", "ai_runs.id"],
            name="fk_ai_retrievals_run",
            ondelete="RESTRICT",
        ),
        # composite tenant FK: tool_call（nullable）
        ForeignKeyConstraint(
            ["school_id", "tool_call_id"],
            ["ai_tool_calls.school_id", "ai_tool_calls.id"],
            name="fk_ai_retrievals_tool_call",
            ondelete="RESTRICT",
        ),
        Index("idx_ai_retrievals_run", "run_id"),
        Index(
            "idx_ai_retrievals_school_run",
            "school_id", "occurred_at",
        ),
        Index("idx_ai_retrievals_tool_call", "tool_call_id"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )