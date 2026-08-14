"""
AI 德育处方大脑 — 数据模型
ai_prescriptions 表：持久化 LLM 生成的班级诊断书 / 学生干预话术
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from core.models import Base, SchoolMixin


class PrescriptionType(str, enum.Enum):
    """处方类型"""
    CLASS_DIAGNOSIS = "CLASS_DIAGNOSIS"   # 班级月度诊断书
    STUDENT_INTV = "STUDENT_INTV"         # 学生心理干预话术


class RiskLevel(str, enum.Enum):
    """风险等级"""
    HIGH = "HIGH"       # 高风险（需立即干预）
    MEDIUM = "MEDIUM"   # 中风险（需关注）
    LOW = "LOW"         # 低风险（正常）


class ReviewStatus(str, enum.Enum):
    """CF-04 人工复核状态机（Human Review Gate）

    铁律：AI generate 永远只能落 PENDING_REVIEW；
    只有人工 CONFIRMED / MODIFIED 之后才允许 bridge 进正式业务；
    REJECTED 永不 bridge。CONFIRMED/MODIFIED/REJECTED 为终态，不可重复复核。
    """
    PENDING_REVIEW = "PENDING_REVIEW"   # 待人工复核（默认，AI 建议非正式事实）
    CONFIRMED = "CONFIRMED"             # 人工确认采用 AI 原输出
    MODIFIED = "MODIFIED"               # 人工修改后采用
    REJECTED = "REJECTED"               # 人工驳回，永不进入业务


class AIPrescription(Base, SchoolMixin):
    """
    AI 处方记录表
    同时支持班级诊断（target_type='class'）和学生干预（target_type='student'）
    """
    __tablename__ = "ai_prescriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 处方类型 + 目标
    prescription_type = Column(Enum(PrescriptionType), nullable=False, index=True)
    target_id = Column(Integer, nullable=False, index=True)
    # target_type 冗余字段，避免 JOIN：'class' | 'student'
    target_type = Column(String(20), nullable=False, index=True)

    # 风险评级（LLM 输出）
    risk_level = Column(Enum(RiskLevel), nullable=True, index=True)

    # 混合输出：2-3句摘要 + 完整 Markdown
    summary = Column(String(500), nullable=True)
    full_text = Column(Text, nullable=False)

    # 原始快照（JSON，用于溯源 / 复现 / 审计）
    raw_snapshot = Column(JSON, nullable=True)

    # ── CF-04 人工复核状态机（Human Review Gate）──
    # AI generate 永远只能落 PENDING_REVIEW；只有人工 CONFIRMED/MODIFIED
    # 才能 bridge 进正式业务；REJECTED 永不 bridge。
    review_status = Column(
        Enum(ReviewStatus),
        # CF-04 V1：历史记录 review_status=NULL（legacy_unreviewed，不可 activate）；
        # 新记录由业务代码显式写 PENDING_REVIEW（见 tasks.py 各生成点）。
        # 不带 server_default，避免把历史 163 行假造成"待审核"。
        nullable=True,
        default=ReviewStatus.PENDING_REVIEW,
        index=True,
    )
    reviewed_by = Column(Integer, nullable=True)          # 复核人（users.id）
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_note = Column(Text, nullable=True)            # 复核意见
    modified_content = Column(Text, nullable=True)       # 人工修改后的完整文本（不覆盖 AI 原文）
    modified_payload = Column(JSON, nullable=True)       # 人工修改后的结构化载荷

    # 创建人（触发 AI 生成的用户，无外键约束以兼容 users.id 类型）
    creator_id = Column(
        Integer,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        # 复合索引：按学校 + 类型 + 目标 快速查询历史
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
        },
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "school_id": self.school_id,
            "prescription_type": self.prescription_type.value
            if self.prescription_type else None,
            "target_id": self.target_id,
            "target_type": self.target_type,
            "risk_level": self.risk_level.value if self.risk_level else None,
            "summary": self.summary,
            "full_text": self.full_text,
            "raw_snapshot": self.raw_snapshot,
            "review_status": self.review_status.value if self.review_status else None,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "review_note": self.review_note,
            "modified_content": self.modified_content,
            "modified_payload": self.modified_payload,
            "creator_id": self.creator_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
