"""rollover_infra

新学年滚动晋升引擎 — 基础设施表
为 student_registry 模块新增两张物理支撑表：
  1. student_year_history — 学年学籍冷冻快照（溯源/校验）
  2. rollover_lock        — 滚动晋升幂等锁（防二次晋升）

Revision ID: f7c2a91d4b60
Revises: 2d8813121d03
Create Date: 2026-07-16 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "f7c2a91d4b60"
down_revision: str | None = "2d8813121d03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ═══════════════════════════════════════════════════════════
    # 表 1 — student_year_history（学年学籍冷冻快照）
    # ═══════════════════════════════════════════════════════════
    op.create_table(
        "student_year_history",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("school_id", mysql.BIGINT(), nullable=False, index=True),
        sa.Column("student_id", mysql.BIGINT(), nullable=False, index=True),
        sa.Column("school_year", mysql.VARCHAR(length=20), nullable=False),
        sa.Column("grade_id", mysql.BIGINT(), nullable=False, index=True),
        sa.Column("class_id", mysql.BIGINT(), nullable=False, index=True),
        sa.Column("created_at", mysql.DATETIME(), nullable=True),
        sa.ForeignKeyConstraint(
            ["school_id"], ["schools.id"], name=op.f("fk_student_year_history_school_id")
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["students.id"], name=op.f("fk_student_year_history_student_id")
        ),
        sa.ForeignKeyConstraint(
            ["grade_id"], ["grades.id"], name=op.f("fk_student_year_history_grade_id")
        ),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_student_year_history_class_id")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_student_year_history")),
        mysql_engine="InnoDB",
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    # 复合索引: (school_id, school_year) — 按学年批量查询快照
    op.create_index(
        op.f("idx_syh_school_year"),
        "student_year_history",
        ["school_id", "school_year"],
        unique=False,
    )

    # ═══════════════════════════════════════════════════════════
    # 表 2 — rollover_lock（滚动晋升幂等锁）
    # ═══════════════════════════════════════════════════════════
    op.create_table(
        "rollover_lock",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("school_id", mysql.BIGINT(), nullable=False, index=True),
        sa.Column("school_year", mysql.VARCHAR(length=20), nullable=False),
        sa.Column("locked_by", mysql.BIGINT(), nullable=False),
        sa.Column("locked_at", mysql.DATETIME(), nullable=True),
        sa.Column("note", mysql.VARCHAR(length=255), nullable=True),
        sa.Column("released_at", mysql.DATETIME(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(), nullable=True),
        sa.ForeignKeyConstraint(
            ["school_id"], ["schools.id"], name=op.f("fk_rollover_lock_school_id")
        ),
        sa.ForeignKeyConstraint(
            ["locked_by"], ["users.id"], name=op.f("fk_rollover_lock_locked_by")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rollover_lock")),
        mysql_engine="InnoDB",
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    # 唯一约束: (school_id, school_year) — 每校每学年至多一条锁
    op.create_index(
        op.f("uk_rollover_lock_school_year"),
        "rollover_lock",
        ["school_id", "school_year"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("uk_rollover_lock_school_year"), table_name="rollover_lock")
    op.drop_table("rollover_lock")
    op.drop_index(op.f("idx_syh_school_year"), table_name="student_year_history")
    op.drop_table("student_year_history")
