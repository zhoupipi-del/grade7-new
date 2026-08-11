"""
ai_native.models.ai_incidents — 失败分类

v3.2 FINAL frozen. 锚定 Inv 11/19/24/26。

★ 不存原始异常正文（detail_hash 替代 message TEXT，Inv 11）。
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
from sqlalchemy.dialects.mysql import ENUM

from core.models import Base


# incident.category 3 类（WINGS 三类扩展，v3.2 FINAL frozen）
INCIDENT_CATEGORIES = ("capability", "compliance", "data")

# incident.severity 4 档
INCIDENT_SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


class AiIncidents(Base):
    """失败分类。"""

    __tablename__ = "ai_incidents"

    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)

    school_id = Column(BigInteger, nullable=False)
    run_id = Column(BigInteger, nullable=False)

    # ── 分类 ───────────────────────────────────────────
    incident_code = Column(
        String(10), nullable=False,
        comment="P01-P12；编码不够时正式 registry 扩 P13/P14…",
    )
    incident_type = Column(
        String(50), nullable=False,
        comment="scope_violation / tool_descriptor_drift / provider_capability_mismatch / …",
    )
    category = Column(
        ENUM(*INCIDENT_CATEGORIES), nullable=False,
        comment=f"值域 {INCIDENT_CATEGORIES}",
    )
    severity = Column(
        ENUM(*INCIDENT_SEVERITIES), nullable=False,
        comment=f"值域 {INCIDENT_SEVERITIES}",
    )

    # ── 描述（不存原文，Inv 11）───────────────────────
    summary_redacted = Column(String(512), nullable=False, comment="脱敏摘要")
    detail_hash = Column(String(64), nullable=True, comment="详情 SHA-256")

    # ── 状态 ───────────────────────────────────────────
    resolved = Column(Boolean, nullable=False, server_default=text("false"))
    resolved_at = Column(DateTime, nullable=True)
    detected_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        # composite tenant FK: run
        ForeignKeyConstraint(
            ["school_id", "run_id"],
            ["ai_runs.school_id", "ai_runs.id"],
            name="fk_ai_incidents_run",
            ondelete="RESTRICT",
        ),
        Index("idx_ai_incidents_run", "run_id"),
        Index("idx_ai_incidents_code", "incident_code"),
        Index("idx_ai_incidents_category", "category"),
        Index(
            "idx_ai_incidents_school_severity",
            "school_id", "severity", "detected_at",
        ),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )