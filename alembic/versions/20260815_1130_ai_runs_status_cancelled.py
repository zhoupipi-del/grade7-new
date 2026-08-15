"""ai_runs.status ENUM + CANCELLED (FT-015 formal migration, idempotent)

Revision ID: 20260815_1130
Revises: 20260815_1020
Create Date: 2026-08-15

背景（为什么需要这个迁移）：
  FT-015 Approval Gate 引入 REJECTED -> CANCELLED 的 Run 终态。
  当时在验证中直接对生产 MySQL 执行了 ALTER 追加 CANCELLED（功能正确），
  但该 schema change 没有进入 Alembic migration graph —— 造成
  production schema != Git migration truth，破坏 FT-014S 刚闭合的 Source-of-Truth。

  本迁移把这桩"既成事实"正式写回 Alembic 历史，使：
    1. 生产环境（ENUM 已含 CANCELLED）→ 检测到已存在，跳过 ALTER，绝不重复修改；
    2. 新环境（按 Alembic 初始化）→ 完整得到含 CANCELLED 的 9 态 ENUM；
    3. ORM model（ai_runs.py）与 DB ENUM / 迁移历史三方重新对齐。

设计纪律：
  - 不重复 ALTER：upgrade 先查 information_schema.COLUMN_TYPE，
    已含 CANCELLED 则 no-op，仅推进 alembic_version；
  - downgrade 对称幂等：仅当 ENUM 含 CANCELLED 且无 CANCELLED 数据行时才还原 8 态，
    有数据行则拒绝（保护已 CANCELLED 的 run 不被 schema 反转破坏）。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "20260815_1130"
down_revision = "20260815_1020"
branch_labels = None
depends_on = None

# 9 态：8 基线 + CANCELLED（与 ai_runs.py model AI_RUN_STATUSES 对齐）
STATUS_9 = (
    "PLANNING", "POLICY_CHECK", "EXECUTING", "WAITING_APPROVAL",
    "RECOVERING", "RESUMING", "COMPLETED", "FAILED", "CANCELLED",
)
# 8 态基线（downgrade 目标）
STATUS_8 = STATUS_9[:8]


def _current_status_type(bind) -> str:
    """读 ai_runs.status 当前 COLUMN_TYPE（如 enum('PLANNING',...)）。"""
    row = bind.execute(
        sa.text(
            "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_runs' "
            "AND COLUMN_NAME = 'status'"
        )
    ).fetchone()
    return (row[0] if row else "") or ""


def _count_cancelled(bind) -> int:
    row = bind.execute(
        sa.text("SELECT COUNT(*) FROM ai_runs WHERE status = 'CANCELLED'")
    ).fetchone()
    return int(row[0]) if row else 0


def upgrade():
    bind = op.get_bind()
    cur = _current_status_type(bind).lower()
    if "cancelled" in cur:
        # 生产已含 CANCELLED（FT-015 手工 ALTER 既成事实）→ 幂等跳过，不重复 ALTER，
        # 仅由 Alembic 推进 alembic_version 到本 revision。
        return
    op.alter_column(
        "ai_runs", "status",
        existing_type=mysql.ENUM(*STATUS_8),
        type_=mysql.ENUM(*STATUS_9),
        existing_nullable=False,
        existing_server_default=sa.text("'PLANNING'"),
    )


def downgrade():
    bind = op.get_bind()
    cur = _current_status_type(bind).lower()
    if "cancelled" not in cur:
        return  # 已是 8 态 → no-op
    if _count_cancelled(bind) > 0:
        # 有 CANCELLED 数据行 → 拒绝反转（保护审计证据）
        raise RuntimeError(
            "downgrade 拒绝：ai_runs 存在 CANCELLED 数据行，不可还原 8 态 ENUM"
        )
    op.alter_column(
        "ai_runs", "status",
        existing_type=mysql.ENUM(*STATUS_9),
        type_=mysql.ENUM(*STATUS_8),
        existing_nullable=False,
        existing_server_default=sa.text("'PLANNING'"),
    )
