"""cf05_ai_provenance_records

CF-05 Batch A: AI Content Provenance Registry (2026-08-16)

AI 业务产物溯源层：回答"谁生成、什么模型、什么数据、过没过 Gateway、
有没有人审、发布的是哪个版本"。

设计要点：
- run_id → ai_runs.run_uuid（真 FK，平台内部关系）
- business_type + business_id 逻辑关联（不强 FK，避免耦死业务表）
- public_provenance_id 唯一（WAI-YYYYMMDD-XXXXXXXX），外部暴露专用，不可反推内部结构
- review_requirement 生成时冻结（REQUIRED/CONFIRM_BEFORE_PUBLISH/OPTIONAL/NONE）
- 双 hash：model_output_sha256(LLM 原稿) / final_content_sha256(人审修改后)
- final_content_sha256 可为 NULL（未 finalize）；finalized_at 标记完成

Revision ID: cf05_20260816
Revises: b2c3d4researchai
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "cf05_20260816"
down_revision = "b2c3d4researchai"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_provenance_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_provenance_id", sa.String(64), nullable=False, comment="外部溯源 ID: WAI-YYYYMMDD-XXXXXXXX"),
        sa.Column("run_id", sa.String(64), nullable=True, comment="ai_runs.run_uuid 关联"),
        sa.Column("business_type", sa.String(64), nullable=False, comment="业务类型: ai_prescription/student_comment/lesson_plan/..."),
        sa.Column("business_id", sa.Integer(), nullable=True, comment="业务记录 ID（逻辑关联，不强 FK）"),
        sa.Column("artifact_version", sa.Integer(), nullable=False, server_default="1", comment="同一产物版本"),
        sa.Column("ai_generated", sa.Boolean(), nullable=False, server_default=sa.text("1"), comment="是否 AI 生成"),
        sa.Column("policy_version", sa.String(32), nullable=True, comment="生成时 policy.yaml 版本"),
        sa.Column("prompt_template_version", sa.String(64), nullable=True, comment="prompt 模板版本"),
        sa.Column("review_requirement", sa.String(32), nullable=False, server_default="REQUIRED",
                  comment="REQUIRED/CONFIRM_BEFORE_PUBLISH/OPTIONAL/NONE（生成时冻结）"),
        sa.Column("review_status", sa.String(32), nullable=True, server_default="PENDING_REVIEW",
                  comment="PENDING_REVIEW/APPROVED/MODIFIED/REJECTED"),
        sa.Column("reviewer_id", sa.Integer(), nullable=True, comment="审核人 user_id"),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("model_output_sha256", sa.String(64), nullable=True, comment="LLM 原始输出 canonical hash"),
        sa.Column("final_content_sha256", sa.String(64), nullable=True, comment="人审/修改后最终内容 hash"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("finalized_at", sa.DateTime(), nullable=True, comment="finalize 时间"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("uq_ppv_public_id", "ai_provenance_records", ["public_provenance_id"], unique=True)
    op.create_index("idx_ppv_run_id", "ai_provenance_records", ["run_id"], unique=False)
    op.create_index("idx_ppv_biz", "ai_provenance_records", ["business_type", "business_id"], unique=False)
    op.create_index("idx_ppv_status", "ai_provenance_records", ["review_status"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_ppv_status", table_name="ai_provenance_records")
    op.drop_index("idx_ppv_biz", table_name="ai_provenance_records")
    op.drop_index("idx_ppv_run_id", table_name="ai_provenance_records")
    op.drop_index("uq_ppv_public_id", table_name="ai_provenance_records")
    op.drop_table("ai_provenance_records")
