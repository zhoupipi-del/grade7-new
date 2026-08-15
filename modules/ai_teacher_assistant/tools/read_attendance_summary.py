"""
modules/ai_teacher_assistant/tools/read_attendance_summary.py — 考勤汇总 Tool

输入：class_id/grade_id + 可选 days（默认 30 天）
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict

import pydantic
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User, Student
from ai_native.runtime.tool_descriptor import ToolDescriptor

logger = logging.getLogger(__name__)

TOOL_NAME = "read_attendance_summary"
TOOL_VERSION = "0.1.0"


class DailyTrend(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    date: str = ""
    late: int = 0
    absent: int = 0
    early: int = 0
    leave: int = 0
    total: int = 0


class ClassAttendance(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    class_id: int | None = None
    class_name: str = ""
    late: int = 0
    absent: int = 0
    early: int = 0
    leave: int = 0
    present: int = 0
    total: int = 0


class ReadAttendanceSummaryOutput(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    grade_id: int | None = None
    class_id: int | None = None
    period: dict = pydantic.Field(default_factory=dict)
    summary: dict = pydantic.Field(default_factory=dict)
    daily_trends: list = pydantic.Field(default_factory=list)
    by_class: list = pydantic.Field(default_factory=list)
    leave_pending: int = 0


def build_read_attendance_summary_descriptor() -> ToolDescriptor:
    return ToolDescriptor(
        name=TOOL_NAME, version=TOOL_VERSION,
        description="读取考勤汇总 — 迟到/缺勤/早退统计 + 日趋势 + 班级分布",
        action="read", side_effect="none", required_scope="class",
        declared_output_classification="student_pii",
        allowed_input_classification="internal",
        approval_policy="none", idempotent=True, timeout_seconds=60,
        supported_roles=["grade_leader", "class_teacher", "ms_admin"],
        handler=read_attendance_summary_handler,
    )


def read_attendance_summary_handler(run=None, **kwargs):
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
            "你是学校年级管理助手。请根据考勤统计数据生成简洁分析。只输出 JSON。"
            "包含：analysis, highlights, attention, trend。不超过 300 字。"
        )},
        {"role": "user", "content": f"考勤统计数据：\n{data_json}"},
    ]

    usage = {}
    try:
        content, usage = provider.call(messages, json_mode=True, temperature=0.3, max_tokens=1024)
        llm_result = json.loads(content)
    except Exception as exc:
        llm_result = {"analysis": f"模型调用失败: {exc}", "highlights": "",
                      "attention": "", "trend": ""}

    return {
        "output": {"summary": llm_result},
        "actual_classification": "student_pii",
        "model_call": {
            "provider": "deepseek",
            "model": os.environ.get("LLM_MODEL", "deepseek-v4-flash"),
            "usage": usage,
            "cost_amount": "0.001", "cost_currency": "CNY",
        },
    }


class _AttendanceAggregator:
    ANOMALY_STATUSES = {"late", "absent", "early", "leave"}

    def __init__(self, db: AsyncSession, school_id: int, user: User):
        self.db = db
        self.school_id = school_id
        self.user = user

    def _build_where(self, class_id, grade_id, days, effective_student_ids):
        """Build WHERE clause AND params dict."""
        cutoff = date.today() - timedelta(days=days)
        conds = ["a.school_id = :sid", "a.record_date >= :cutoff"]
        params = {"sid": self.school_id, "cutoff": cutoff}
        if class_id is not None:
            conds.append("a.class_id = :cid")
            params["cid"] = class_id
        elif grade_id is not None:
            conds.append("a.grade_id = :gid")
            params["gid"] = grade_id
        if effective_student_ids is not None:
            conds.append("a.student_id IN :vis")
            params["vis"] = tuple(effective_student_ids)
        return " AND ".join(conds), params, cutoff

    async def aggregate(self, *, class_id=None, grade_id=None, days=30,
                        effective_student_ids=None) -> Dict[str, Any]:
        where_str, params, cutoff = self._build_where(
            class_id, grade_id, days, effective_student_ids)

        # Status breakdown
        status_sql = (
            f"SELECT a.status, COUNT(1) AS cnt FROM attendance_records a "
            f"WHERE {where_str} GROUP BY a.status"
        )
        status_rows = (await self.db.execute(text(status_sql), params)).all()
        status_counts: Dict[str, int] = {}
        for row in status_rows:
            status_counts[row[0]] = int(row[1])

        total_anomalies = sum(status_counts.get(s, 0) for s in self.ANOMALY_STATUSES)

        # Daily trend
        trend_sql = (
            f"SELECT a.record_date, a.status, COUNT(1) AS cnt FROM attendance_records a "
            f"WHERE {where_str} AND a.status IN ('late','absent','early','leave') "
            f"GROUP BY a.record_date, a.status ORDER BY a.record_date"
        )
        trend_rows = (await self.db.execute(text(trend_sql), params)).all()

        daily: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"late": 0, "absent": 0, "early": 0, "leave": 0})
        for row in trend_rows:
            d = str(row[0])
            st = row[1] if row[1] in self.ANOMALY_STATUSES else "late"
            daily[d][st] = int(row[2])

        daily_trends = [
            {"date": d, **stats, "total": sum(stats.values())}
            for d, stats in sorted(daily.items())
        ]

        # By class
        class_sql = (
            f"SELECT a.class_id, c.name, a.status, COUNT(1) AS cnt "
            f"FROM attendance_records a JOIN classes c ON a.class_id = c.id "
            f"WHERE {where_str} GROUP BY a.class_id, c.name, a.status ORDER BY a.class_id"
        )
        class_rows = (await self.db.execute(text(class_sql), params)).all()

        by_class_raw: Dict[int, Dict[str, Any]] = defaultdict(
            lambda: {"class_id": None, "class_name": "", "late": 0, "absent": 0,
                     "early": 0, "leave": 0, "present": 0})
        all_statuses = self.ANOMALY_STATUSES | {"present"}
        for row in class_rows:
            cid = int(row[0])
            cname = row[1]
            st = row[2] if row[2] in all_statuses else "late"
            by_class_raw[cid]["class_id"] = cid
            by_class_raw[cid]["class_name"] = cname
            by_class_raw[cid][st] = int(row[3])

        by_class = []
        for cid in sorted(by_class_raw):
            d = by_class_raw[cid]
            d["total"] = sum(d.get(s, 0) for s in self.ANOMALY_STATUSES)
            by_class.append(d)

        # Leave pending
        leave_conds = "l.school_id = :sid AND l.status = 'pending'"
        if grade_id is not None:
            leave_conds += " AND l.grade_id = :gid"
        if class_id is not None:
            leave_conds += " AND l.class_id = :cid"
        pending_sql = f"SELECT COUNT(1) FROM leave_requests l WHERE {leave_conds}"
        pending = (await self.db.execute(text(pending_sql), params)).scalar_one_or_none() or 0

        # REAL EVENT #1：数据覆盖度（区分"无数据"与"无异常"）
        total_records = sum(status_counts.values()) or 0
        coverage = {
            "total_records": total_records,
            "days_with_data": len({r[0] for r in trend_rows}),
            "first_date": str(daily_trends[0]["date"]) if daily_trends else None,
            "last_date": str(daily_trends[-1]["date"]) if daily_trends else None,
            "empty_window": total_records == 0,
        }

        return {
            "grade_id": grade_id, "class_id": class_id,
            "period": {"days": days, "from": str(cutoff), "to": str(date.today())},
            "data_coverage": coverage,
            "summary": {
                "total_anomalies": total_anomalies,
                "late": status_counts.get("late", 0),
                "absent": status_counts.get("absent", 0),
                "early": status_counts.get("early", 0),
                "leave": status_counts.get("leave", 0),
                "present": status_counts.get("present", 0),
            },
            "daily_trends": daily_trends,
            "by_class": by_class,
            "leave_pending": int(pending),
            "data_json": json.dumps({
                "summary": {
                    "total_anomalies": total_anomalies,
                    "late": status_counts.get("late", 0),
                    "absent": status_counts.get("absent", 0),
                    "early": status_counts.get("early", 0),
                    "leave": status_counts.get("leave", 0),
                },
                "daily_trends": daily_trends[-7:] if daily_trends else [],
                "by_class": [
                    {"name": c["class_name"], "anomalies": c["total"],
                     "late": c["late"], "absent": c["absent"]}
                    for c in sorted(by_class, key=lambda x: x["total"], reverse=True)
                ],
                "leave_pending": pending,
                "data_coverage": coverage,
            }, ensure_ascii=False),
        }


# ═══════════════════════════════════════════════════════════════
#  Copilot handler（V2 多工具编排路径，经 ToolExecutor 执行）
#  ★ 聚合调用发生在 handler 内部，不绕过 ToolExecutor；不调 DeepSeek
# ═══════════════════════════════════════════════════════════════

async def read_attendance_summary_copilot_handler(run=None, **_) -> Dict[str, Any]:
    """V2 Copilot 执行点：经 ToolExecutor 调用，内部聚合考勤数据。"""
    run = run or {}
    db = run["db"]
    user = run["user"]
    school_id = run["school_id"]
    effective_student_ids = run.get("effective_student_ids")
    args = run.get("args", {}) or {}
    agg = _AttendanceAggregator(db, school_id, user)
    result = await agg.aggregate(
        class_id=args.get("class_id"),
        grade_id=args.get("grade_id"),
        days=args.get("days", 30),
        effective_student_ids=effective_student_ids,
    )
    return {
        "status": "EXECUTED",
        "domain": "attendance",
        "result": result,
        "actual_classification": "internal",
    }
