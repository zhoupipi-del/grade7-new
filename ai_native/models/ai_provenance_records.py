"""
ai_native.models.ai_provenance_records — CF-05 AI 业务产物溯源 Registry

CF-05 Batch A (2026-08-16): 回答"谁生成、什么模型、什么数据、过没过
Privacy Gateway、有没有人审、发布的是哪个版本"。

设计要点（v2 定稿）：
- run_id → ai_runs.run_uuid 逻辑关联（真 FK 不建物理 REFERENCES，与 ai_runs 同款
  logical reference 惯例；DB 层用普通索引）
- business_type + business_id 逻辑关联（不强 FK，避免把 registry 与业务表耦死）
- public_provenance_id 唯一，外部暴露专用（WAI-YYYYMMDD-XXXXXXXX），不可反推内部结构
- review_requirement 生成时冻结（REQUIRED/CONFIRM_BEFORE_PUBLISH/OPTIONAL/NONE）
- 双 hash：model_output_sha256（LLM 原稿）/ final_content_sha256（人审修改后）
- final_content_sha256 可 NULL（未 finalize）；finalized_at 标记完成
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    text,
)

from core.models import Base


class AIProvenanceRecord(Base):
    """AI 业务产物溯源记录（CF-05 Batch A）。"""

    __tablename__ = "ai_provenance_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    public_provenance_id = Column(
        String(64), nullable=False, unique=True,
        comment="外部溯源 ID: WAI-YYYYMMDD-XXXXXXXX",
    )
    run_id = Column(
        String(64), nullable=True, index=True,
        comment="ai_runs.run_uuid 逻辑关联（不强 FK）",
    )
    business_type = Column(
        String(64), nullable=False,
        comment="业务类型: ai_prescription/student_comment/lesson_plan/...",
    )
    business_id = Column(
        BigInteger, nullable=True,
        comment="业务记录 ID（逻辑关联，不强 FK）",
    )
    artifact_version = Column(
        Integer, nullable=False, default=1,
        comment="同一产物版本（草稿 v1 → 修改 v2 → 导出 v3）",
    )
    ai_generated = Column(Boolean, nullable=False, default=True, server_default=text("1"))
    policy_version = Column(String(32), nullable=True, comment="生成时 policy.yaml 版本")
    prompt_template_version = Column(String(64), nullable=True)
    review_requirement = Column(
        String(32), nullable=False, default="REQUIRED", server_default=text("'REQUIRED'"),
        comment="REQUIRED/CONFIRM_BEFORE_PUBLISH/OPTIONAL/NONE（生成时冻结）",
    )
    review_status = Column(
        String(32), nullable=True, default="PENDING_REVIEW", server_default=text("'PENDING_REVIEW'"),
        comment="PENDING_REVIEW/APPROVED/MODIFIED/REJECTED",
    )
    reviewer_id = Column(BigInteger, nullable=True, comment="审核人 user_id")
    reviewed_at = Column(DateTime, nullable=True)
    model_output_sha256 = Column(String(64), nullable=True, comment="LLM 原始输出 canonical hash")
    final_content_sha256 = Column(String(64), nullable=True, comment="人审/修改后最终内容 hash")
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    finalized_at = Column(DateTime, nullable=True, comment="finalize 时间")
