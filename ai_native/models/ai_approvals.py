"""
ai_native.models.ai_approvals — 审批记录

v3.2 FINAL frozen. 锚定 Inv 4/5/9/10/15/19/22/24/25/26。

★ Approval 绑定一次具体执行（tool_call_id NOT NULL，Inv 4），不是绑定 Tool 名。
★ tool_call_id 复合 FK (school_id, tool_call_id) → ai_tool_calls(school_id, id)，
  强制 tenant-consistent（Inv 25：approvals 不得跨 school 引用 tool_call）。
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
from sqlalchemy.dialects.mysql import ENUM, JSON

from core.models import Base


# approval.decision 4 态（v3.2 FINAL frozen）
APPROVAL_DECISIONS = ("PENDING", "APPROVED", "REJECTED", "EXPIRED")


class AiApprovals(Base):
    """审批记录。"""

    __tablename__ = "ai_approvals"

    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)

    school_id = Column(BigInteger, nullable=False)
    run_id = Column(BigInteger, nullable=False)

    # ★ 绑定具体 Tool Call（Inv 4/5/25）
    tool_call_id = Column(BigInteger, nullable=False)

    # 版本绑定链
    tool_name = Column(String(100), nullable=False)
    tool_version = Column(String(20), nullable=False)
    schema_version = Column(String(20), nullable=False)
    policy_version = Column(String(20), nullable=False)
    role_profile_version = Column(String(20), nullable=False)

    # 参数 + Scope（不存原文，Inv 4/10）
    arguments_hash = Column(String(64), nullable=False, comment="审批时参数 SHA-256")
    resource_scope = Column(JSON, nullable=False, comment="审批时 ResourceScope")

    # 决策
    approver_id = Column(
        BigInteger, nullable=True,
        comment="审批人 User.id（类型=User.id；intentionally no FK）",
    )
    decision = Column(
        ENUM(*APPROVAL_DECISIONS),
        nullable=False,
        server_default=text("'PENDING'"),
        comment=f"值域 {APPROVAL_DECISIONS}",
    )
    decided_at = Column(DateTime, nullable=True)
    expiry_at = Column(DateTime, nullable=False)

    __table_args__ = (
        # composite tenant FK: run
        ForeignKeyConstraint(
            ["school_id", "run_id"],
            ["ai_runs.school_id", "ai_runs.id"],
            name="fk_ai_approvals_run",
            ondelete="RESTRICT",
        ),
        # composite tenant FK: tool_call（NOT NULL，Inv 25）
        ForeignKeyConstraint(
            ["school_id", "tool_call_id"],
            ["ai_tool_calls.school_id", "ai_tool_calls.id"],
            name="fk_ai_approvals_tool_call",
            ondelete="RESTRICT",
        ),
        Index("idx_ai_approvals_run", "run_id"),
        Index("idx_ai_approvals_tool_call", "tool_call_id"),
        Index("idx_ai_approvals_decision", "decision", "expiry_at"),
        Index(
            "idx_ai_approvals_school",
            "school_id", "decided_at",
        ),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )