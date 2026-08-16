"""cf04ops_20260816_add_counselor_role

CF04-OPS-001 (R1 阻塞项): users.role ENUM 缺 'counselor'
- 后端 UserRole 枚举含 COUNSELOR，DB ENUM 无 → counselor 账号从未可创建
  （实证: users 表 counselor=0; role DataError 1265 truncated）
- 纯 additive ENUM 扩值，不改现有数据语义；默认值保持 'teacher'

Revision ID: cf04ops_20260816
Revises: cf05_20260816
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "cf04ops_20260816"
down_revision = "cf05_20260816"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "role",
        existing_type=sa.Enum(
            "ms_admin", "group_admin", "branch_admin", "grade_leader",
            "class_teacher", "teacher", "parent", "student",
            name="role",
        ),
        type_=sa.Enum(
            "ms_admin", "group_admin", "branch_admin", "grade_leader",
            "class_teacher", "teacher", "counselor", "parent", "student",
            name="role",
        ),
        existing_nullable=False,
        server_default="teacher",
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "role",
        existing_type=sa.Enum(
            "ms_admin", "group_admin", "branch_admin", "grade_leader",
            "class_teacher", "teacher", "counselor", "parent", "student",
            name="role",
        ),
        type_=sa.Enum(
            "ms_admin", "group_admin", "branch_admin", "grade_leader",
            "class_teacher", "teacher", "parent", "student",
            name="role",
        ),
        existing_nullable=False,
        server_default="teacher",
    )
