"""
ai_native.models.ai_execution_snapshots — 审计证据快照（1:1 on run_id）

v3.2 FINAL frozen. 锚定 Inv 3/9/10/11/19/23/24/26。

★ 可审计 ≠ 永久保存可执行数据（Inv 10）。
★ 不存完整 prompt/completion/Tool 参数/Tool 输出/心理正文/学生原始数据。
★ 用引用链（refs JSON）替代 LONGBLOB payload。
★ run_id 唯一约束（1:1）+ composite tenant FK → ai_runs。
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import JSON

from core.models import Base


class AiExecutionSnapshots(Base):
    """审计证据快照（1:1 on run_id）。"""

    __tablename__ = "ai_execution_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)

    school_id = Column(BigInteger, nullable=False)
    run_id = Column(
        BigInteger, nullable=False,
        comment="FK → ai_runs.id（composite）；1:1 关系由 inline UNIQUE 强制",
    )

    # 全链路指纹
    snapshot_hash = Column(
        String(64), nullable=False,
        comment="全链路 SHA-256（所有 refs + 元数据 的 hash）",
    )

    # 版本链
    role_profile_version = Column(String(20), nullable=True)
    policy_version = Column(String(20), nullable=True)
    prompt_version = Column(
        String(20), nullable=True,
        comment="prompt 模板版本——半年后模型行为变化时可溯源",
    )
    ui_schema_version = Column(String(20), nullable=True, comment="前端渲染 schema 版本")

    # 引用链（替代 LONGBLOB payload）
    tool_versions = Column(
        JSON, nullable=True, comment="{tool_name: version} 映射",
    )
    model_call_refs = Column(
        JSON, nullable=True, comment="[ai_model_calls.id, ...] 引用链",
    )
    retrieval_refs = Column(
        JSON, nullable=True, comment="[ai_retrievals.id, ...] 引用链",
    )
    approval_refs = Column(
        JSON, nullable=True, comment="[ai_approvals.id, ...] 引用链",
    )

    # 安全
    classification_peak = Column(
        String(30), nullable=False,
        comment="Run 接触的最高数据等级（证是否碰 psych_sensitive）；小写 Inv 23",
    )
    argument_hashes = Column(
        JSON, nullable=False,
        comment="{tool_name: arg_hash}（与审批参数一致性校验）",
    )
    scope_snapshot = Column(
        JSON, nullable=True, comment="执行时完整 Scope 快照（替代裸列）",
    )

    created_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        # inline UNIQUE: run_id（1 Run : 1 Snapshot）
        UniqueConstraint("run_id", name="uq_ai_execution_snapshots_run_id"),
        # composite tenant FK: run
        ForeignKeyConstraint(
            ["school_id", "run_id"],
            ["ai_runs.school_id", "ai_runs.id"],
            name="fk_ai_execution_snapshots_run",
            ondelete="RESTRICT",
        ),
        Index("idx_ai_execution_snapshots_run", "run_id"),
        Index(
            "idx_ai_execution_snapshots_school_run",
            "school_id", "created_at",
        ),
        Index(
            "idx_ai_execution_snapshots_classification",
            "classification_peak", "created_at",
        ),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )