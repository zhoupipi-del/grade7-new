"""teacher_subjects_v1_1

WINGS 组织责任模型 V1.1 — teacher_subjects 扩展（周主任 2026-08-13 拍板）

问题：teacher_subjects 只有 grade 粒度，无法表达「哪个班的数学老师」；
      且缺生效/失效时间；旧 UNIQUE (school_id, teacher_user_id, subject_code)
      阻止同师同科多班多行。

V1.1 目标（Schema 先行，真实数据后填）：
  + class_id     BIGINT NULL    授课班级（NULL=年级级任课）
  + is_active    TINYINT(1)     停用标记
  + assigned_at  DATETIME       分配时间
  + expires_at   DATETIME NULL  过期时间
  + scope_key    VARCHAR(32) GENERATED ALWAYS AS (
                    CASE WHEN class_id IS NOT NULL
                         THEN CONCAT('C:', class_id)
                         ELSE CONCAT('G:', COALESCE(grade_id, 0)) END
                  ) STORED
  - DROP 旧唯一约束 uk_teacher_subject / uk_teacher_subject_grade
  + UNIQUE uk_teacher_subject_scope (school_id, teacher_user_id, subject_code, scope_key)
  + INDEX ix_teacher_subject_class (class_id)

业务校验（Service 层，非本 migration）：
  teacher.school_id == class.school_id == grade.school_id == teacher_subject.school_id
  class.grade_id == teacher_subjects.grade_id（class 有值时）

Revision ID: 20260813_0717
Revises: 20260811_1810
Create Date: 2026-08-13 07:17:00.000000

★ 人工编写，不依赖 autogenerate。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


revision: str = "20260813_0717"
down_revision: str | None = "20260811_1810"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_unique_if_exists(bind, table: str, name: str) -> None:
    """MySQL 的 UNIQUE 是索引形态；drop 前先确认存在，避免多环境差异炸迁移。"""
    insp = sa.inspect(bind)
    try:
        idx_names = {i["name"] for i in insp.get_indexes(table)}
        cons_names = {c["name"] for c in insp.get_unique_constraints(table)}
    except Exception:
        idx_names, cons_names = set(), set()
    if name in idx_names or name in cons_names:
        try:
            op.drop_constraint(name, table, type_="unique")
        except Exception:
            op.drop_index(name, table_name=table)


def upgrade() -> None:
    bind = op.get_bind()

    # 1) 加列
    op.add_column(
        "teacher_subjects",
        sa.Column("class_id", sa.BigInteger(), nullable=True, comment="授课班级（NULL=年级级任课）"),
    )
    op.add_column(
        "teacher_subjects",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1"), comment="是否有效"),
    )
    op.add_column(
        "teacher_subjects",
        sa.Column("assigned_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="分配时间"),
    )
    op.add_column(
        "teacher_subjects",
        sa.Column("expires_at", sa.DateTime(), nullable=True, comment="过期时间(可选)"),
    )
    op.add_column(
        "teacher_subjects",
        sa.Column(
            "scope_key",
            sa.String(32),
            sa.Computed(
                "CASE WHEN class_id IS NOT NULL "
                "THEN CONCAT('C:', class_id) "
                "ELSE CONCAT('G:', COALESCE(grade_id, 0)) END",
                persisted=True,
            ),
            nullable=True,
            comment="生成的作用域键 C:<class_id> / G:<grade_id>，用于唯一约束",
        ),
    )

    # 2) 删旧唯一约束（容错）
    _drop_unique_if_exists(bind, "teacher_subjects", "uk_teacher_subject_grade")
    _drop_unique_if_exists(bind, "teacher_subjects", "uk_teacher_subject")

    # 3) 新唯一约束：校+师+科+作用域键
    op.create_unique_constraint(
        "uk_teacher_subject_scope",
        "teacher_subjects",
        ["school_id", "teacher_user_id", "subject_code", "scope_key"],
    )

    # 4) class 索引
    op.create_index("ix_teacher_subject_class", "teacher_subjects", ["class_id"])


def downgrade() -> None:
    bind = op.get_bind()

    # 先删依赖 scope_key 的约束/索引
    op.drop_index("ix_teacher_subject_class", table_name="teacher_subjects")
    _drop_unique_if_exists(bind, "teacher_subjects", "uk_teacher_subject_scope")

    op.drop_column("teacher_subjects", "scope_key")
    op.drop_column("teacher_subjects", "expires_at")
    op.drop_column("teacher_subjects", "assigned_at")
    op.drop_column("teacher_subjects", "is_active")
    op.drop_column("teacher_subjects", "class_id")

    # 恢复旧唯一约束（与生产 V1.0 形态一致）
    op.create_unique_constraint(
        "uk_teacher_subject",
        "teacher_subjects",
        ["school_id", "teacher_user_id", "subject_code"],
    )
    op.create_unique_constraint(
        "uk_teacher_subject_grade",
        "teacher_subjects",
        ["teacher_user_id", "subject_name", "grade_id"],
    )
