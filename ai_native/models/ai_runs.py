"""
ai_native.models.ai_runs — Agent Run 主表

v3.2 FINAL frozen. 锚定 Inv 1/3/16/22/23。

★ school_id 类型 = BIGINT signed（与 School.id 实证一致），但不建 REFERENCES
  schools(id) 的物理 FK（§0-E：logical reference + 运行时 WHERE school_id）。
★ uq_run_school (school_id, id) 是 composite tenant FK 在 DB 层被合法引用的
  父键唯一约束（§0-C）。
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    FetchedValue,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import CHAR, ENUM

from core.models import Base


# Run 状态机 9 态（v3.2 frozen 基线 8 态；FT-015 正式追加 CANCELLED——
# REJECTED -> CANCELLED 终态。model/migration/DB 三方对齐）
AI_RUN_STATUSES = (
    "PLANNING",
    "POLICY_CHECK",
    "EXECUTING",
    "WAITING_APPROVAL",
    "RECOVERING",
    "RESUMING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
)


class AiRuns(Base):
    """Agent Run 主表。"""

    __tablename__ = "ai_runs"

    # ── PK ──────────────────────────────────────────────
    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)

    # ── 对外 UUID ───────────────────────────────────────
    run_uuid = Column(CHAR(36), nullable=False, comment="对外 Run UUID")

    # ── 租户 + 触发者（不建物理 FK；§0-E）────────────────
    school_id = Column(
        BigInteger,
        nullable=False,
        comment="★ 租户隔离；类型须与 School.id (BigInteger signed) 一致；intentionally no FK",
    )
    user_id = Column(
        BigInteger,
        nullable=False,
        comment="触发者 User.id；类型须与 User.id (BigInteger signed) 一致；intentionally no FK",
    )

    # ── 角色上下文 ──────────────────────────────────────
    role_profile = Column(
        String(50), nullable=False,
        comment="principal/dean/head_teacher/teacher/psychologist",
    )
    role_profile_version = Column(String(20), nullable=True)
    copilot_profile = Column(String(64), nullable=True)

    # ── 输入（不存原文）─────────────────────────────────
    query_hash = Column(String(64), nullable=True, comment="用户原始输入 SHA-256")
    query_redacted = Column(String(512), nullable=True, comment="脱敏后的输入摘要")
    input_summary = Column(String(256), nullable=True, comment="Agent 理解后的任务摘要")

    # ── Run 状态机 9 态（Frozen ENUM，含 CANCELLED）──────
    status = Column(
        ENUM(*AI_RUN_STATUSES),
        nullable=False,
        server_default=text("'PLANNING'"),
        comment=f"Run 状态机，值域 {AI_RUN_STATUSES}",
    )

    # ── DataClassification（小写 Inv 23）───────────────
    data_classification = Column(
        String(30),
        nullable=False,
        server_default=text("'internal'"),
        comment="public/internal/student_pii/psych_sensitive，全小写",
    )
    data_classification_peak = Column(String(30), nullable=True)

    # ── 追踪 ───────────────────────────────────────────
    trace_id = Column(String(64), nullable=True)

    # ── Provider 摘要（明细在 ai_model_calls）──────────
    primary_provider = Column(String(50), nullable=True)
    primary_model = Column(String(80), nullable=True)

    # ── 时间 ───────────────────────────────────────────
    started_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"),
    )
    completed_at = Column(DateTime, nullable=True)

    # ── 错误（不存原文——错误栈可能含学生姓名/prompt/手机号/psych）──
    error_kind = Column(String(50), nullable=True, comment="timeout/rate_limit/...")
    error_message_hash = Column(String(64), nullable=True, comment="错误消息 SHA-256")

    # ── 时间戳 ─────────────────────────────────────────
    created_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"),
    )
    # ★ Canonical: DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    # MySQL 方言无独立 ON UPDATE 选项；官方写法 = server_default 文本带 ON UPDATE。
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        server_onupdate=FetchedValue(),
    )

    __table_args__ = (
        # uq_run_school: 父键复合 UNIQUE，供所有子表 (school_id, run_id) 复合 FK 引用
        UniqueConstraint("school_id", "id", name="uq_run_school"),
        # inline UNIQUE: run_uuid
        UniqueConstraint("run_uuid", name="uq_ai_runs_run_uuid"),
        Index("idx_ai_runs_user_id", "user_id"),
        Index("idx_ai_runs_status", "status"),
        Index("idx_ai_runs_started_at", "started_at"),
        Index(
            "idx_ai_runs_classification_peak",
            "data_classification_peak",
            "created_at",
        ),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )