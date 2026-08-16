"""
ai_native.runtime.provenance — CF-05 Batch A: AI Provenance Registry service

生命周期（v2 定稿）：
    AI run starts
      ↓
    AI output generated
      ↓
    create_provenance()          → 建记录 + 锁 model_output_sha256
      ↓
    business processing / human modification
      ↓
    finalize_provenance()        → final_content_sha256 + finalized_at

对外只暴露 public_provenance_id（WAI-YYYYMMDD-XXXXXXXX），不暴露内部 run_uuid。
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_native.models.ai_provenance_records import AIProvenanceRecord

# ────────────────────────────────────────────────────────────────
# Canonical Hash（v2: JSON canonical serialization → UTF-8 → SHA256）
# ────────────────────────────────────────────────────────────────

_REVIEW_REQUIREMENTS = ("REQUIRED", "CONFIRM_BEFORE_PUBLISH", "OPTIONAL", "NONE")
_REVIEW_STATUSES = ("PENDING_REVIEW", "APPROVED", "MODIFIED", "REJECTED")


def canonical_json(obj: Any) -> str:
    """JSON canonical serialization: 排序 key + ensure_ascii=False + 紧凑分隔。"""
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def canonical_text(text: str) -> str:
    """纯文本归一化: 统一换行符 + 去行尾空白。不 trim 首尾（保留内容语义）。"""
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_structured(obj: Any) -> str:
    """结构化输出 canonical hash（JSON → UTF-8 → SHA256）。"""
    return sha256_of(canonical_json(obj).encode("utf-8"))


def hash_text(text: str) -> str:
    """纯文本 canonical hash（UTF-8 + 换行归一化）。"""
    return sha256_of(canonical_text(text).encode("utf-8"))


def hash_bytes(raw: bytes) -> str:
    """文件字节 hash（artifact_sha256 用，不归一化）。"""
    return sha256_of(raw)


def make_public_provenance_id(now: Optional[datetime] = None) -> str:
    """WAI-YYYYMMDD-XXXXXXXX（8 位随机 hex）。"""
    now = now or datetime.now()
    date_part = now.strftime("%Y%m%d")
    rand_part = uuid.uuid4().hex[:8].upper()
    return f"WAI-{date_part}-{rand_part}"


# ────────────────────────────────────────────────────────────────
# Service
# ────────────────────────────────────────────────────────────────


class ProvenanceService:
    """AI 产物溯源 Registry 生命周期管理。"""

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        business_type: str,
        business_id: Optional[int] = None,
        run_id: Optional[str] = None,
        model_output: Any = None,
        policy_version: Optional[str] = None,
        prompt_template_version: Optional[str] = None,
        review_requirement: str = "REQUIRED",
        ai_generated: bool = True,
        artifact_version: int = 1,
    ) -> AIProvenanceRecord:
        """AI 输出后创建 provenance 记录，锁定 model_output_sha256。

        原则：Provenance 可以没有 artifact，但正式 AI artifact 不能没有 provenance。
        """
        if review_requirement not in _REVIEW_REQUIREMENTS:
            raise ValueError(f"invalid review_requirement: {review_requirement}")

        model_hash = None
        if model_output is not None:
            if isinstance(model_output, (dict, list)):
                model_hash = hash_structured(model_output)
            elif isinstance(model_output, bytes):
                model_hash = hash_bytes(model_output)
            else:
                model_hash = hash_text(str(model_output))

        rec = AIProvenanceRecord(
            public_provenance_id=make_public_provenance_id(),
            run_id=run_id,
            business_type=business_type,
            business_id=business_id,
            artifact_version=artifact_version,
            ai_generated=ai_generated,
            policy_version=policy_version,
            prompt_template_version=prompt_template_version,
            review_requirement=review_requirement,
            review_status="PENDING_REVIEW",
            model_output_sha256=model_hash,
        )
        db.add(rec)
        await db.commit()
        await db.refresh(rec)
        return rec

    @staticmethod
    async def finalize(
        db: AsyncSession,
        rec: AIProvenanceRecord,
        final_content: Any,
        *,
        reviewer_id: Optional[int] = None,
        review_status: Optional[str] = None,
    ) -> AIProvenanceRecord:
        """人审/修改完成后落 final_content_sha256 + finalized_at。

        final_content 可为结构化对象或文本；哈希用对应 canonical 方法。
        """
        if isinstance(final_content, (dict, list)):
            rec.final_content_sha256 = hash_structured(final_content)
        elif isinstance(final_content, bytes):
            rec.final_content_sha256 = hash_bytes(final_content)
        else:
            rec.final_content_sha256 = hash_text(str(final_content))
        rec.finalized_at = datetime.now()
        if reviewer_id is not None:
            rec.reviewer_id = reviewer_id
            rec.reviewed_at = datetime.now()
        if review_status is not None:
            if review_status not in _REVIEW_STATUSES:
                raise ValueError(f"invalid review_status: {review_status}")
            rec.review_status = review_status
        await db.commit()
        await db.refresh(rec)
        return rec

    @staticmethod
    async def update_review(
        db: AsyncSession,
        rec: AIProvenanceRecord,
        review_status: str,
        reviewer_id: Optional[int] = None,
        final_content: Any = None,
    ) -> AIProvenanceRecord:
        """审核流转：APPROVED / MODIFIED / REJECTED（终态锁定）。"""
        if review_status not in _REVIEW_STATUSES:
            raise ValueError(f"invalid review_status: {review_status}")
        if rec.review_status not in ("PENDING_REVIEW",):
            raise ValueError(
                f"terminal state locked: cannot transition from {rec.review_status}"
            )
        rec.review_status = review_status
        if reviewer_id is not None:
            rec.reviewer_id = reviewer_id
            rec.reviewed_at = datetime.now()
        if final_content is not None and review_status in ("APPROVED", "MODIFIED"):
            await ProvenanceService.finalize(db, rec, final_content, reviewer_id=reviewer_id)
            return rec
        await db.commit()
        await db.refresh(rec)
        return rec

    @staticmethod
    async def get_by_public_id(db: AsyncSession, public_provenance_id: str) -> Optional[AIProvenanceRecord]:
        result = await db.execute(
            select(AIProvenanceRecord).where(
                AIProvenanceRecord.public_provenance_id == public_provenance_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_business(
        db: AsyncSession, business_type: str, business_id: int
    ) -> list[AIProvenanceRecord]:
        result = await db.execute(
            select(AIProvenanceRecord)
            .where(
                AIProvenanceRecord.business_type == business_type,
                AIProvenanceRecord.business_id == business_id,
            )
            .order_by(AIProvenanceRecord.artifact_version.desc())
        )
        return list(result.scalars().all())
