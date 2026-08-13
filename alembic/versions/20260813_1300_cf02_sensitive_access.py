"""cf02_sensitive_access

CF-02 (⑤.5 Compliance Foundation V1) — 敏感数据访问审计账本。

新建 sensitive_data_access_logs 表，记录所有心理类敏感资源的
「合法访问 / 越权尝试 / 异常」，回答「谁在何时以何种用途访问了
哪个学生的什么资源」。purpose 由后端常量自动填，调用方不可伪造。

Revision ID: 20260813_1300
Revises: 20260813_1145
Create Date: 2026-08-13 13:00:00.000000

★ 人工编写。downgrade 可逆（删表）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260813_1300"
down_revision: str | None = "20260813_1145"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common_collate() -> dict:
    return {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
    }


def upgrade() -> None:
    op.create_table(
        "sensitive_data_access_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("school_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("student_id", sa.BigInteger(), nullable=True),
        sa.Column("resource_type", sa.String(40), nullable=False),
        sa.Column("resource_id", sa.String(80), nullable=True),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("purpose_note", sa.Text(), nullable=True),
        sa.Column("scope_type", sa.String(20), nullable=True),
        sa.Column("scope_id", sa.BigInteger(), nullable=True),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        **_common_collate(),
    )
    op.create_index(
        "idx_sdal_user", "sensitive_data_access_logs",
        ["school_id", "user_id", "created_at"],
    )
    op.create_index(
        "idx_sdal_student", "sensitive_data_access_logs",
        ["school_id", "student_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_sdal_student", table_name="sensitive_data_access_logs")
    op.drop_index("idx_sdal_user", table_name="sensitive_data_access_logs")
    op.drop_table("sensitive_data_access_logs")
