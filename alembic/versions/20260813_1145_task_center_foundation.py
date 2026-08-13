"""task_center_foundation

Task Center Foundation V1 — 责任闭环底座（周主任 2026-08-13 拍板）。

设计要点（5 条架构规则锁死）：
1. Task 不自己猜 Owner：创建时经 ResponsibleOwnerResolver，unresolved → 允许建
   但 owner=NULL + unresolved_reason（unassigned / resolution_required），绝不 fallback。
2. 责任快照：tasks 主表保存 owner_user_id/owner_name_snapshot/responsibility_role/
   responsibility_scope_type/responsibility_scope_id/resolution_source/
   resolution_confidence/resolved_at/assignment_id —— 调岗后历史任务仍指向当时的负责人。
3. Assignment 改变 ≠ 历史任务自动换人：task_assignments 只追加（is_current 翻转），
   已处理/已完成任务永远保留原责任人。
4. V1 只管理真实动作：状态机 OPEN→ACCEPTED→IN_PROGRESS→DONE + REJECTED/CANCELLED。
5. DONE ≠ verified：tasks.status=DONE 与 closure_status 分离（V1 完成时标 pending，
   不把"我点了完成"和"问题真的解决了"混成一个字段）。

5 张表：
  tasks            任务主表（含责任快照 + closure 分离）
  task_assignments 分派历史（追加式，is_current 标记当前）
  task_events      状态流转事件流（JSON detail 快照）
  task_evidence    处理证据（note / communication_record / file）
  task_comments    评论

Revision ID: 20260813_1145
Revises: 20260813_0906
Create Date: 2026-08-13 11:45:00.000000

★ 人工编写。downgrade 可逆（删 5 表）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260813_1145"
down_revision: str | None = "20260813_0906"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common_collate() -> dict:
    return {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
    }


def upgrade() -> None:
    # ── tasks 任务主表 ──
    op.create_table(
        "tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("school_id", sa.BigInteger(), nullable=False),
        sa.Column("task_type", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        # ── 责任快照（规则 2）──
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("owner_name_snapshot", sa.String(100), nullable=True),
        sa.Column("responsibility_role", sa.String(32), nullable=True),
        sa.Column("responsibility_scope_type", sa.String(16), nullable=True),
        sa.Column("responsibility_scope_id", sa.BigInteger(), nullable=True),
        sa.Column("resolution_source", sa.String(64), nullable=True),
        sa.Column("resolution_confidence", sa.String(16), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("assignment_id", sa.BigInteger(), nullable=True),
        sa.Column("unresolved_reason", sa.String(200), nullable=True),
        # ── closure 与 status 分离（规则 5）──
        sa.Column("closure_status", sa.String(16), nullable=True),
        sa.Column("closure_verified_at", sa.DateTime(), nullable=True),
        sa.Column("closure_verified_by", sa.BigInteger(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        **_common_collate(),
    )
    op.create_index("idx_tasks_owner_status", "tasks", ["school_id", "owner_user_id", "status"])
    op.create_index("idx_tasks_created", "tasks", ["school_id", "created_at"])

    # ── task_assignments 分派历史（规则 3：追加式）──
    op.create_table(
        "task_assignments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("assignment_id", sa.BigInteger(), nullable=True),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("owner_name_snapshot", sa.String(100), nullable=True),
        sa.Column("responsibility_role", sa.String(32), nullable=True),
        sa.Column("responsibility_scope_type", sa.String(16), nullable=True),
        sa.Column("responsibility_scope_id", sa.BigInteger(), nullable=True),
        sa.Column("resolution_source", sa.String(64), nullable=True),
        sa.Column("resolution_confidence", sa.String(16), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("reassigned_from_user_id", sa.BigInteger(), nullable=True),
        sa.Column("assigned_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "assigned_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("id"),
        **_common_collate(),
    )
    op.create_index("idx_ta_task", "task_assignments", ["task_id"])
    op.create_index("idx_ta_owner", "task_assignments", ["owner_user_id", "is_current"])

    # ── task_events 状态流转事件流 ──
    op.create_table(
        "task_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_name", sa.String(100), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True, comment="JSON 快照"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        **_common_collate(),
    )
    op.create_index("idx_te_task", "task_events", ["task_id"])

    # ── task_evidence 处理证据 ──
    op.create_table(
        "task_evidence",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="note"),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        **_common_collate(),
    )
    op.create_index("idx_td_task", "task_evidence", ["task_id"])

    # ── task_comments 评论 ──
    op.create_table(
        "task_comments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        **_common_collate(),
    )
    op.create_index("idx_tc_task", "task_comments", ["task_id"])


def downgrade() -> None:
    op.drop_index("idx_tc_task", table_name="task_comments")
    op.drop_table("task_comments")
    op.drop_index("idx_td_task", table_name="task_evidence")
    op.drop_table("task_evidence")
    op.drop_index("idx_te_task", table_name="task_events")
    op.drop_table("task_events")
    op.drop_index("idx_ta_owner", table_name="task_assignments")
    op.drop_index("idx_ta_task", table_name="task_assignments")
    op.drop_table("task_assignments")
    op.drop_index("idx_tasks_created", table_name="tasks")
    op.drop_index("idx_tasks_owner_status", table_name="tasks")
    op.drop_table("tasks")
