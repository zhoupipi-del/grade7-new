"""risk_warnings lifecycle & dedup fields (DATA-GOV-001 Phase 2/3)

Revision ID: 20260815_1200
Revises: 20260815_1130
Create Date: 2026-08-15

背景（DATA-GOV-001 P1-HIGH）：
  批处理扫描（batch_scan）每日 01:00 对同一学生同一信号重复 INSERT 预警，
  产生 125 rows = 7 students + 每日重复 + 103 过期未关单 + trigger_event_id=0。
  本迁移为幂等/生命周期/治理打标提供字段支撑：

    - occurrence_count   : 同一 fingerprint 累计被扫描命中的次数（重复报警计数）
    - last_seen_at       : 该信号最近一次被确认/扫描的时间（幂等 UPDATE 用）
    - source_fingerprint : 幂等键（school/student/signal/source/version 的稳定 hash）
    - governance_status  : 历史 reconciliation 治理打标
                           (VALID_CURRENT/EXPIRED/DUPLICATE/SUPERSEDED/
                            UNANCHORED/DATA_QUALITY_DEGRADED)，不物理删除历史

设计纪律：
  - 全部幂等：列不存在才 ADD；已存在则 no-op（防止重复执行）。
  - 不破坏现有数据：历史行 occurrence_count 默认 1，last_seen_at 默认 NULL
    （由 reconciliation 脚本回填为 warned_at），source_fingerprint 默认 NULL
    （历史不可考，留空表示 legacy，不伪造指纹）。
"""

from alembic import op
import sqlalchemy as sa

revision = "20260815_1200"
down_revision = "20260815_1130"
branch_labels = None
depends_on = None


def _column_exists(bind, table: str, column: str) -> bool:
    row = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
        ),
        {"t": table, "c": column},
    ).scalar()
    return int(row) > 0


def _index_exists(bind, table: str, index: str) -> bool:
    row = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :i"
        ),
        {"t": table, "i": index},
    ).scalar()
    return int(row) > 0


def upgrade():
    bind = op.get_bind()

    if not _column_exists(bind, "risk_warnings", "occurrence_count"):
        op.add_column(
            "risk_warnings",
            sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        )
    if not _column_exists(bind, "risk_warnings", "last_seen_at"):
        op.add_column("risk_warnings", sa.Column("last_seen_at", sa.DateTime(), nullable=True))
    if not _column_exists(bind, "risk_warnings", "source_fingerprint"):
        op.add_column(
            "risk_warnings",
            sa.Column("source_fingerprint", sa.String(length=80), nullable=True),
        )
    if not _column_exists(bind, "risk_warnings", "governance_status"):
        op.add_column(
            "risk_warnings",
            sa.Column("governance_status", sa.String(length=30), nullable=True),
        )
    # fingerprint 索引（幂等查询加速）——MySQL 不支持 IF NOT EXISTS，手动判存在
    if not _index_exists(bind, "risk_warnings", "idx_rw_fingerprint"):
        op.execute(
            sa.text(
                "CREATE INDEX idx_rw_fingerprint "
                "ON risk_warnings (source_fingerprint)"
            )
        )


def downgrade():
    bind = op.get_bind()
    # 仅当无数据依赖时降级；数据行存在则拒绝（保护审计证据）
    cnt = bind.execute(sa.text("SELECT COUNT(*) FROM risk_warnings")).scalar()
    if int(cnt) > 0:
        raise RuntimeError("downgrade 拒绝：risk_warnings 存在数据行，不删除治理字段")
    for col in ("governance_status", "source_fingerprint", "last_seen_at", "occurrence_count"):
        if _column_exists(bind, "risk_warnings", col):
            op.drop_column("risk_warnings", col)
