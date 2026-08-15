"""Task Center V1 schema reconcile (idempotent)

Revision ID: 20260815_1020
Revises: 20260813_1400
Create Date: 2026-08-15

背景（为什么需要这个迁移）：
  生产环境 tasks 表由早期 6 态模型经 Base.metadata.create_all 建出，
  当时 ORM 模型尚未包含 Task Center V1 的 8 个新字段。create_all 只创建
  *缺失* 的表、绝不 ALTER 已存在的表，因此这 8 个字段一直没有落地。

  部署 Batch B 时，已在生产手工 ALTER 补齐了这 8 列（tasks 由 25 列→33 列，
  0 行、零风险）。本迁移把这桩"既成事实"正式写回 Alembic 历史，使：

    1. 生产环境（列已存在）→ 跳过 ADD，不重复建列；
    2. 新环境（按 Alembic 初始化）→ 完整建出 Task Center V1 schema；
    3. ORM 模型与 Alembic 迁移历史重新对齐（migration truth 一致）。

设计纪律（对应 Feature Freeze）：
  - 本迁移不新增任何业务能力，纯粹是"数据库现实 ↔ 迁移事实"的对齐；
  - upgrade / downgrade 均按列存在性做幂等判断，可重复执行、可安全回退。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260815_1020"
down_revision = "20260813_1400"
branch_labels = None
depends_on = None


# Task Center V1 新增的 8 个字段（对齐 modules/tasks/models.py Task）
# 顺序与模型定义一致；downgrade 时逆序删除以保持幂等。
NEW_COLUMNS = [
    ("source_type", sa.String(32), "来源类型（behavior/attendance/class_affair...）"),
    ("source_id", sa.BigInteger(), "来源记录 ID"),
    ("student_id", sa.BigInteger(), "关联学生"),
    ("class_id", sa.BigInteger(), "关联班级"),
    ("grade_id", sa.BigInteger(), "关联年级"),
    ("started_at", sa.DateTime(), "责任人开始处理时间"),
    ("completed_at", sa.DateTime(), "责任人填写结果时间"),
    ("result", sa.Text(), "处理结果留痕"),
]


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("tasks")}
    for name, type_, _comment in NEW_COLUMNS:
        if name in existing:
            # 生产环境列已存在（手工 ALTER 补齐），跳过，避免重复建列
            continue
        op.add_column("tasks", sa.Column(name, type_, nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("tasks")}
    for name, _type, _comment in reversed(NEW_COLUMNS):
        if name not in existing:
            continue
        op.drop_column("tasks", name)
