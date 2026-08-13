"""evaluation_scores_source_incident

evaluation_scores 增加 source 数据来源标记列 + incident_date 事件日期列
（周主任 2026-08-13 拍板，正向加分链治理）。

背景：
  审计发现 evaluation_scores 1154 条中 1151 条是成绩导入（ind8 学业成绩，
  scorer_type=system，6-30 批量"期末考试总分"），真实教师正向加分 = 0。
  正向加分与成绩导入混在同一张表且无来源标记 → 无法区分可信来源，
  也无法支撑"正能量排行榜"只消费真实表扬。

约定：
  source 取值与 discipline_records 完全一致:
    teacher_manual     老师真实登记（QuickPraise 服务端显式写）
    system_generated   系统自动产生
    import             批量导入（成绩导入走此标记）
    device             设备产生
    test_demo          测试/演示数据
    legacy_unknown     历史遗留、来源不明（新数据默认值，保守）

  incident_date:
    事件发生日期（表扬是"某天发生的事"）。旧数据不凭空猜：
    已确认导入批次 → 按批次规则填；否则保留 NULL（查询兼容 created_at）。

Revision ID: 20260813_0906
Revises: 20260813_0806
Create Date: 2026-08-13 09:06:00.000000

★ 人工编写。downgrade 可逆（删列）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260813_0906"
down_revision: str | None = "20260813_0806"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_scores",
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default="legacy_unknown",
            comment="数据来源: teacher_manual/system_generated/import/device/test_demo/legacy_unknown",
        ),
    )
    op.add_column(
        "evaluation_scores",
        sa.Column(
            "incident_date",
            sa.Date(),
            nullable=True,
            comment="事件发生日期（表扬/评分发生日）；旧数据可为 NULL",
        ),
    )
    op.create_index("idx_es_source", "evaluation_scores", ["source"])


def downgrade() -> None:
    op.drop_index("idx_es_source", table_name="evaluation_scores")
    op.drop_column("evaluation_scores", "incident_date")
    op.drop_column("evaluation_scores", "source")
