"""
AI 德育处方大脑 — 数据模型
ai_prescriptions 表：持久化 LLM 生成的班级诊断书 / 学生干预话术
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from core.models import Base, SchoolMixin
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
)


class PrescriptionType(str, enum.Enum):
    """处方类型"""

    CLASS_DIAGNOSIS = "CLASS_DIAGNOSIS"  # 班级月度诊断书
    STUDENT_INTV = "STUDENT_INTV"  # 学生心理干预话术


class RiskLevel(str, enum.Enum):
    """风险等级"""

    HIGH = "HIGH"  # 高风险（需立即干预）
    MEDIUM = "MEDIUM"  # 中风险（需关注）
    LOW = "LOW"  # 低风险（正常）


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

    # 创建人（触发 AI 生成的用户，无外键约束以兼容 users.id 类型）
    creator_id = Column(
        Integer,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
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
            "prescription_type": self.prescription_type.value if self.prescription_type else None,
            "target_id": self.target_id,
            "target_type": self.target_type,
            "risk_level": self.risk_level.value if self.risk_level else None,
            "summary": self.summary,
            "full_text": self.full_text,
            "raw_snapshot": self.raw_snapshot,
            "creator_id": self.creator_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
