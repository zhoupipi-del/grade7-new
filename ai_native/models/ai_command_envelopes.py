"""
ai_native.models.ai_command_envelopes — 可执行命令包（AES-256-GCM，短 TTL 30min）

v3.2 FINAL frozen. 锚定 Inv 5/18/19/24/25/26。

★ nonce / auth_tag 分列存储（不内嵌 BLOB）。
★ payload_hash_sha256 仅用于一致性 + Approval binding，**不可逆**（Inv 18）。
★ 30min TTL：expires_at 绝对过期；过期后不为审计保留可解密 payload。
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import BLOB, VARBINARY, CHAR

from core.models import Base


class AiCommandEnvelopes(Base):
    """可执行命令包（AES-256-GCM 加密，短 TTL）。"""

    __tablename__ = "ai_command_envelopes"

    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)

    # 对外 UUID
    envelope_uuid = Column(CHAR(36), nullable=False, comment="对外 Envelope UUID")

    school_id = Column(BigInteger, nullable=False)
    run_id = Column(BigInteger, nullable=False)
    tool_call_id = Column(BigInteger, nullable=False)

    # 版本绑定
    tool_name = Column(String(100), nullable=False, comment="审批时的 Tool 名")
    tool_version = Column(String(20), nullable=False, comment="审批时的 Tool 版本")
    schema_version = Column(String(20), nullable=False)

    # 加密 payload（nonce / tag 分列）
    payload_ciphertext = Column(BLOB, nullable=False, comment="AES-256-GCM 密文")
    nonce = Column(VARBINARY(12), nullable=False, comment="GCM nonce")
    auth_tag = Column(VARBINARY(16), nullable=False, comment="GCM auth_tag")
    crypto_algorithm = Column(
        String(20), nullable=False, server_default=text("'AES-256-GCM'"),
    )
    encryption_key_version = Column(String(32), nullable=False, comment="KMS / app key 版本")

    # 完整性校验（Inv 18：仅一致性/绑定，不可逆）
    payload_hash_sha256 = Column(
        String(64), nullable=False,
        comment="明文 payload SHA-256；用于 Approval binding 一致性校验，**不可逆**",
    )

    # 生命周期
    created_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"),
    )
    expires_at = Column(DateTime, nullable=False, comment="30min TTL 绝对过期时间")
    consumed_at = Column(DateTime, nullable=True, comment="被执行时间（NULL=未消费）")

    __table_args__ = (
        # inline UNIQUE: envelope_uuid
        UniqueConstraint("envelope_uuid", name="uq_ai_command_envelopes_envelope_uuid"),
        # composite tenant FK: run
        ForeignKeyConstraint(
            ["school_id", "run_id"],
            ["ai_runs.school_id", "ai_runs.id"],
            name="fk_ai_command_envelopes_run",
            ondelete="RESTRICT",
        ),
        # composite tenant FK: tool_call
        ForeignKeyConstraint(
            ["school_id", "tool_call_id"],
            ["ai_tool_calls.school_id", "ai_tool_calls.id"],
            name="fk_ai_command_envelopes_tool_call",
            ondelete="RESTRICT",
        ),
        Index("idx_ai_command_envelopes_run", "run_id"),
        Index("idx_ai_command_envelopes_tool_call", "tool_call_id"),
        Index("idx_ai_command_envelopes_expires_at", "expires_at"),
        Index(
            "idx_ai_command_envelopes_school_run",
            "school_id", "created_at",
        ),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )