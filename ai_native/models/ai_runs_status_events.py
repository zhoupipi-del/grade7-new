"""
ai_native.models.ai_runs_status_events — Run 状态机 8 态事件流

v3.2 FINAL frozen. 锚定 Inv 3/10/19/24/26。

★ composite tenant FK: (school_id, run_id) → ai_runs(school_id, id) ON DELETE RESTRICT。
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.mysql import JSON

from core.models import Base


class AiRunsStatusEvents(Base):
    """Run 状态机 8 态事件流。"""

    __tablename__ = "ai_runs_status_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)

    school_id = Column(BigInteger, nullable=False, comment="租户冗余")
    run_id = Column(BigInteger, nullable=False, comment="FK → ai_runs.id（composite）")

    from_status = Column(String(30), nullable=True)
    to_status = Column(String(30), nullable=False)
    trigger_reason = Column(String(256), nullable=True, comment="状态转换触发原因（脱敏）")
    payload = Column(JSON, nullable=True, comment="附加上下文（不含敏感原文）")

    created_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        # composite tenant FK（Inv 24/26）+ RESTRICT（Inv 19）
        ForeignKeyConstraint(
            ["school_id", "run_id"],
            ["ai_runs.school_id", "ai_runs.id"],
            name="fk_ai_runs_status_events_run",
            ondelete="RESTRICT",
        ),
        Index("idx_ai_runs_status_events_run", "run_id", "created_at"),
        Index(
            "idx_ai_runs_status_events_school_run",
            "school_id", "created_at",
        ),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )