"""behavior_source_column

discipline_records 增加 source 数据来源标记列（周主任 2026-08-13 拍板）。

背景：
  Data Capture Audit 发现 189 条违纪记录中 186 条由系统管理员产生，
  其中 11 条 description 明确含测试关键词（烟测/桥接/测试/D3bridge）。
  数据库"有数据"不代表"有真实数据" → 必须能区分来源。

约定：
  source 取值:
    teacher_manual     老师真实登记（QuickRegister 服务端显式写）
    system_generated   系统自动产生
    import             批量导入
    device             设备产生
    test_demo          测试/演示数据
    legacy_unknown     历史遗留、来源不明（新数据默认值，保守）

统计口径：test_demo / legacy_unknown 默认不进入正式行为统计与 AI 趋势。

Revision ID: 20260813_0806
Revises: 20260813_0717
Create Date: 2026-08-13 08:06:00.000000

★ 人工编写。downgrade 可逆（删列）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260813_0806"
down_revision: str | None = "20260813_0717"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "discipline_records",
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default="legacy_unknown",
            comment="数据来源: teacher_manual/system_generated/import/device/test_demo/legacy_unknown",
        ),
    )
    op.create_index("idx_dr_source", "discipline_records", ["source"])


def downgrade() -> None:
    op.drop_index("idx_dr_source", table_name="discipline_records")
    op.drop_column("discipline_records", "source")
