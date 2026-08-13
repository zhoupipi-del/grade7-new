"""
modules/ai_teacher_assistant/tools/read_behavior_summary.py — 行为/德育汇总 Tool
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict

import pydantic
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User
from ai_native.runtime.tool_descriptor import ToolDescriptor

logger = logging.getLogger(__name__)

TOOL_NAME = "read_behavior_summary"
TOOL_VERSION = "0.1.0"


class BehaviorByType(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    type: str = ""
    count: int = 0


class ReadBehaviorSummaryOutput(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    grade_id: int | None = None
    class_id: int | None = None
    period: dict = pydantic.Field(default_factory=dict)
    summary: dict = pydantic.Field(default_factory=dict)
    by_type: list = pydantic.Field(default_factory=list)
    by_category: list = pydantic.Field(default_factory=list)
    by_class: list = pydantic.Field(default_factory=list)
    sanctions_active: int = 0


def build_read_behavior_summary_descriptor() -> ToolDescriptor:
    return ToolDescriptor(
        name=TOOL_NAME, version=TOOL_VERSION,
        description="读取行为纪律汇总 — 违纪类型/类别分布 + 处分统计",
        action="read", side_effect="none", required_scope="class",
        declared_output_classification="student_pii",
        allowed_input_classification="internal",
        approval_policy="none", idempotent=True, timeout_seconds=60,
        supported_roles=["grade_leader", "class_teacher", "ms_admin"],
        handler=read_behavior_summary_handler,
    )


def read_behavior_summary_handler(run=None, **kwargs):
    from ai_native.runtime.provider_router import ProviderRouter

    ctx = (run or {}).get("aggregation") or {}
    data_classification = (run or {}).get("data_classification") or "internal"
    data_json = ctx.get("data_json", "{}")

    router = ProviderRouter()
    provider = router.route(
        model=os.environ.get("LLM_MODEL", "deepseek-v4-flash"),
        data_classification=data_classification,
    )

    messages = [
        {"role": "system", "content": (
            "你是学校德育管理助手。请根据学生违纪统计数据生成简洁分析。只输出 JSON。"
            "包含：analysis, highlights, attention, suggestions。不超过 300 字。"
        )},
        {"role": "user", "content": f"违纪统计数据：\n{data_json}"},
    ]

    usage = {}
    try:
        content, usage = provider.call(messages, json_mode=True, temperature=0.3, max_tokens=1024)
        llm_result = json.loads(content)
    except Exception as exc:
        llm_result = {"analysis": f"模型调用失败: {exc}", "highlights": "",
                      "attention": "", "suggestions": ""}

    return {
        "output": {"summary": llm_result},
        "actual_classification": "student_pii",
        "model_call": {
            "provider": "deepseek",
            "model": os.environ.get("LLM_MODEL", "deepseek-v4-flash"),
            "usage": usage, "cost_amount": "0.001", "cost_currency": "CNY",
        },
    }


class _BehaviorAggregator:
    def __init__(self, db: AsyncSession, school_id: int, user: User):
        self.db = db
        self.school_id = school_id
        self.user = user

    def _build_where(self, class_id, grade_id, days, effective_student_ids):
        cutoff = date.today() - timedelta(days=days)
        # 数据来源口径(Data Capture Audit 2026-08-13): 正式行为统计只消费可信原始事件
        # teacher_manual=老师真实登记; system_generated/legacy_unknown/test_demo 不计入
        conds = ["d.school_id = :sid", "d.incident_date >= :cutoff", "d.source = 'teacher_manual'"]
        params = {"sid": self.school_id, "cutoff": cutoff}
        if class_id is not None:
            conds.append("d.class_id = :cid")
            params["cid"] = class_id
        elif grade_id is not None:
            conds.append("d.grade_id = :gid")
            params["gid"] = grade_id
        if effective_student_ids is not None:
            conds.append("d.student_id IN :vis")
            params["vis"] = tuple(effective_student_ids)
        return " AND ".join(conds), params, cutoff

    async def aggregate(self, *, class_id=None, grade_id=None, days=30,
                        effective_student_ids=None) -> Dict[str, Any]:
        where_str, params, cutoff = self._build_where(
            class_id, grade_id, days, effective_student_ids)

        # Type distribution
        type_sql = (
            f"SELECT d.type, COUNT(1) FROM discipline_records d "
            f"WHERE {where_str} GROUP BY d.type ORDER BY COUNT(1) DESC"
        )
        type_rows = (await self.db.execute(text(type_sql), params)).all()
        by_type = [{"type": r[0] or "unknown", "count": int(r[1])} for r in type_rows]

        # Category
        cat_sql = (
            f"SELECT d.category, COUNT(1) FROM discipline_records d "
            f"WHERE {where_str} AND d.category IS NOT NULL "
            f"GROUP BY d.category ORDER BY COUNT(1) DESC"
        )
        cat_rows = (await self.db.execute(text(cat_sql), params)).all()
        by_category = [{"type": r[0] or "other", "count": int(r[1])} for r in cat_rows]

        # By class
        class_sql = (
            f"SELECT d.class_id, c.name, COUNT(1) FROM discipline_records d "
            f"JOIN classes c ON d.class_id = c.id WHERE {where_str} "
            f"GROUP BY d.class_id, c.name ORDER BY COUNT(1) DESC"
        )
        class_rows = (await self.db.execute(text(class_sql), params)).all()
        by_class = [{"class_id": int(r[0]), "class_name": r[1], "count": int(r[2])} for r in class_rows]

        # Active sanctions
        sanc_conds = "s.school_id = :sid AND s.status = 'ACTIVE'"
        if grade_id is not None:
            sanc_conds += " AND s.grade_id = :gid"
        if class_id is not None:
            sanc_conds += " AND s.class_id = :cid"
        sanc_sql = f"SELECT COUNT(1) FROM discipline_sanctions s WHERE {sanc_conds}"
        sanctions_active = (await self.db.execute(text(sanc_sql), params)).scalar_one_or_none() or 0

        total_records = sum(r["count"] for r in by_type)

        return {
            "grade_id": grade_id, "class_id": class_id,
            "period": {"days": days, "from": str(cutoff), "to": str(date.today())},
            "summary": {
                "total_records": total_records,
                "type_distribution": {r["type"]: r["count"] for r in by_type},
                "top_categories": by_category[:5],
            },
            "by_type": by_type,
            "by_category": by_category,
            "by_class": by_class,
            "sanctions_active": int(sanctions_active),
            "data_json": json.dumps({
                "summary": {"total_records": total_records, "by_type": by_type, "top_categories": by_category[:5]},
                "by_class": [
                    {"name": c["class_name"], "count": c["count"]}
                    for c in sorted(by_class, key=lambda x: x["count"], reverse=True)
                ],
                "sanctions_active": sanctions_active,
            }, ensure_ascii=False),
        }


# ═══════════════════════════════════════════════════════════════
#  Copilot handler（V2 多工具编排路径，经 ToolExecutor 执行）
#  ★ 聚合调用发生在 handler 内部，不绕过 ToolExecutor；不调 DeepSeek
# ═══════════════════════════════════════════════════════════════

async def read_behavior_summary_copilot_handler(run=None, **_) -> Dict[str, Any]:
    """V2 Copilot 执行点：经 ToolExecutor 调用，内部聚合行为纪律数据。"""
    run = run or {}
    db = run["db"]
    user = run["user"]
    school_id = run["school_id"]
    effective_student_ids = run.get("effective_student_ids")
    args = run.get("args", {}) or {}
    agg = _BehaviorAggregator(db, school_id, user)
    result = await agg.aggregate(
        class_id=args.get("class_id"),
        grade_id=args.get("grade_id"),
        days=args.get("days", 30),
        effective_student_ids=effective_student_ids,
    )
    return {
        "status": "EXECUTED",
        "domain": "behavior",
        "result": result,
        "actual_classification": "internal",
    }
