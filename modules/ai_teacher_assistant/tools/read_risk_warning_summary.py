"""
modules/ai_teacher_assistant/tools/read_risk_warning_summary.py — 风险预警汇总 Tool
约束：不输出 psych_deviation / psych_veto_triggered 等心理敏感字段
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

import pydantic
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User
from ai_native.runtime.tool_descriptor import ToolDescriptor

logger = logging.getLogger(__name__)

TOOL_NAME = "read_risk_warning_summary"
TOOL_VERSION = "0.1.0"


class RiskByLevel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    level: str = ""
    count: int = 0


class ReadRiskWarningSummaryOutput(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    grade_id: int | None = None
    class_id: int | None = None
    summary: dict = pydantic.Field(default_factory=dict)
    by_level: list = pydantic.Field(default_factory=list)
    by_class: list = pydantic.Field(default_factory=list)
    by_trigger: list = pydantic.Field(default_factory=list)
    unhandled: int = 0


def build_read_risk_warning_summary_descriptor() -> ToolDescriptor:
    return ToolDescriptor(
        name=TOOL_NAME, version=TOOL_VERSION,
        description="读取风险预警汇总 — 风险等级分布 + 触发类型 + 未处置统计（不含心理敏感数据）",
        action="read", side_effect="none", required_scope="grade",
        declared_output_classification="student_pii",
        allowed_input_classification="internal",
        approval_policy="none", idempotent=True, timeout_seconds=60,
        supported_roles=["grade_leader", "ms_admin"],
        handler=read_risk_warning_summary_handler,
    )


def read_risk_warning_summary_handler(run=None, **kwargs):
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
            "你是学校风险管理助手。请根据风险预警统计数据生成简洁分析。只输出 JSON。"
            "包含：analysis, highlights, attention, recommendations。不超过 300 字。"
            "不要提及任何心理评估具体分数或学生个人姓名。"
        )},
        {"role": "user", "content": f"风险预警统计数据：\n{data_json}"},
    ]

    usage = {}
    try:
        content, usage = provider.call(messages, json_mode=True, temperature=0.3, max_tokens=1024)
        llm_result = json.loads(content)
    except Exception as exc:
        llm_result = {"analysis": f"模型调用失败: {exc}", "highlights": "",
                      "attention": "", "recommendations": ""}

    return {
        "output": {"summary": llm_result},
        "actual_classification": "student_pii",
        "model_call": {
            "provider": "deepseek",
            "model": os.environ.get("LLM_MODEL", "deepseek-v4-flash"),
            "usage": usage, "cost_amount": "0.001", "cost_currency": "CNY",
        },
    }


class _RiskWarningAggregator:
    def __init__(self, db: AsyncSession, school_id: int, user: User):
        self.db = db
        self.school_id = school_id
        self.user = user

    def _build_where(self, class_id, grade_id, effective_student_ids):
        conds = ["r.school_id = :sid"]
        params = {"sid": self.school_id}
        if class_id is not None:
            conds.append("r.class_id = :cid")
            params["cid"] = class_id
        elif grade_id is not None:
            conds.append("r.grade_id = :gid")
            params["gid"] = grade_id
        if effective_student_ids is not None:
            conds.append("r.student_id IN :vis")
            params["vis"] = tuple(effective_student_ids)
        return " AND ".join(conds), params

    async def aggregate(self, *, class_id=None, grade_id=None,
                        effective_student_ids=None) -> Dict[str, Any]:
        where_str, params = self._build_where(class_id, grade_id, effective_student_ids)

        # Risk level
        level_sql = (
            f"SELECT r.risk_level, COUNT(1) FROM risk_warnings r "
            f"WHERE {where_str} GROUP BY r.risk_level"
        )
        level_rows = (await self.db.execute(text(level_sql), params)).all()
        by_level = [{"level": r[0], "count": int(r[1])} for r in level_rows]

        # By class
        class_sql = (
            f"SELECT r.class_id, c.name, COUNT(1) FROM risk_warnings r "
            f"JOIN classes c ON r.class_id = c.id WHERE {where_str} "
            f"GROUP BY r.class_id, c.name ORDER BY COUNT(1) DESC"
        )
        class_rows = (await self.db.execute(text(class_sql), params)).all()
        by_class = [{"class_id": int(r[0]), "class_name": r[1], "count": int(r[2])} for r in class_rows]

        # Trigger type (safe, no psych fields)
        trigger_sql = (
            f"SELECT r.trigger_event_type, COUNT(1) FROM risk_warnings r "
            f"WHERE {where_str} AND r.trigger_event_type IS NOT NULL "
            f"GROUP BY r.trigger_event_type ORDER BY COUNT(1) DESC"
        )
        trigger_rows = (await self.db.execute(text(trigger_sql), params)).all()
        by_trigger = [{"type": r[0] or "unknown", "count": int(r[1])} for r in trigger_rows]

        # Unhandled
        unhandled_sql = (
            f"SELECT COUNT(1) FROM risk_warnings r WHERE {where_str} "
            f"AND r.status = 'active' AND r.handled_by IS NULL"
        )
        unhandled = (await self.db.execute(text(unhandled_sql), params)).scalar_one_or_none() or 0

        total = sum(r["count"] for r in by_level)

        return {
            "grade_id": grade_id, "class_id": class_id,
            "summary": {
                "total": total, "unhandled": int(unhandled),
                "intervention": sum(r["count"] for r in by_level if r["level"] == "intervention"),
                "attention": sum(r["count"] for r in by_level if r["level"] == "attention"),
            },
            "by_level": by_level, "by_class": by_class, "by_trigger": by_trigger,
            "unhandled": int(unhandled),
            "data_json": json.dumps({
                "summary": {
                    "total": total, "unhandled": unhandled,
                    "intervention": sum(r["count"] for r in by_level if r["level"] == "intervention"),
                    "attention": sum(r["count"] for r in by_level if r["level"] == "attention"),
                },
                "by_trigger": by_trigger[:5],
                "by_class": [
                    {"name": c["class_name"], "count": c["count"]}
                    for c in sorted(by_class, key=lambda x: x["count"], reverse=True)
                ],
                "note": "心理敏感字段(psych_deviation等)已在此层滤除",
            }, ensure_ascii=False),
        }


# ═══════════════════════════════════════════════════════════════
#  Copilot handler（V2 多工具编排路径，经 ToolExecutor 执行）
#  ★ 聚合调用发生在 handler 内部，不绕过 ToolExecutor；不调 DeepSeek
#  ★ 仅返回聚合计数（level/class/trigger），绝不携带 student PII / 心理原文
# ═══════════════════════════════════════════════════════════════

async def read_risk_warning_summary_copilot_handler(run=None, **_) -> Dict[str, Any]:
    """V2 Copilot 执行点：经 ToolExecutor 调用，内部聚合风险预警数据。

    返回结果只含计数分布（total/attention/intervention/by_class/by_trigger），
    不携带 student_id / student_name / warning_detail / 心理敏感字段。
    """
    run = run or {}
    db = run["db"]
    user = run["user"]
    school_id = run["school_id"]
    effective_student_ids = run.get("effective_student_ids")
    args = run.get("args", {}) or {}
    agg = _RiskWarningAggregator(db, school_id, user)
    result = await agg.aggregate(
        class_id=args.get("class_id"),
        grade_id=args.get("grade_id"),
        effective_student_ids=effective_student_ids,
    )
    return {
        "status": "EXECUTED",
        "domain": "risk",
        "result": result,
        "actual_classification": "internal",
    }
