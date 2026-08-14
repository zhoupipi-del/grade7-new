"""cf04_human_review

CF-04 (⑤.5 Compliance Foundation V1) — AI 处方人工复核（Human Review Gate）。

给 ai_prescriptions 增加人工复核状态机，回答「AI 能决定什么」：
  review_status: NULL=历史未复核(legacy_unreviewed,不可activate) / PENDING_REVIEW=新生成待人工复核 / CONFIRMED / MODIFIED / REJECTED
  reviewed_by / reviewed_at / review_note / modified_content / modified_payload

铁律：
  - AI generate 永远只能落 PENDING_REVIEW，不能 AI→active→intervention→punishment。
  - 只有人工 CONFIRMED / MODIFIED 之后才允许 bridge 进正式业务。
  - REJECTED 永不 bridge。
  - 人工改动写入 modified_content / modified_payload，不覆盖 AI 原文(full_text/raw_snapshot)。

Revision ID: 20260813_1400
Revises: 20260813_1300
Create Date: 2026-08-13 14:00:00.000000

★ 人工编写。downgrade 可逆（删列 + 删索引）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260813_1400"
down_revision: str | None = "20260813_1300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_prescriptions",
        sa.Column(
            "review_status",
            sa.Enum(
                "PENDING_REVIEW",
                "CONFIRMED",
                "MODIFIED",
                "REJECTED",
                name="review_status",
            ),
            # CF-04 V1：历史 163 行保持 NULL（legacy_unreviewed，不可 activate）；
            # 仅新生成记录由业务代码显式写 PENDING_REVIEW。
            # 严禁 server_default=PENDING_REVIEW——否则会把历史假造成"待审核"假事实。
            nullable=True,
        ),
    )
    op.add_column(
        "ai_prescriptions",
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
    )
    op.add_column(
        "ai_prescriptions",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_prescriptions",
        sa.Column("review_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "ai_prescriptions",
        sa.Column("modified_content", sa.Text(), nullable=True),
    )
    op.add_column(
        "ai_prescriptions",
        sa.Column("modified_payload", sa.JSON(), nullable=True),
    )

    # 索引：按 review_status 快速筛出待复核队列
    op.create_index(
        "ix_ai_prescriptions_review_status",
        "ai_prescriptions",
        ["review_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_prescriptions_review_status", table_name="ai_prescriptions")
    op.drop_column("ai_prescriptions", "modified_payload")
    op.drop_column("ai_prescriptions", "modified_content")
    op.drop_column("ai_prescriptions", "review_note")
    op.drop_column("ai_prescriptions", "reviewed_at")
    op.drop_column("ai_prescriptions", "reviewed_by")
    op.drop_column("ai_prescriptions", "review_status")
