"""
modules/ai_teacher_assistant/tools/read_class_grade_summary.py — Tool 实现

Inv 14 唯一 Tool：read_class_grade_summary

输入：class_id/grade_id + exam_id（默认最新已发布考试）
流程：
    1. 查 GradeRecord [JOIN Student(school_id+grade_id/class_id 过滤)]
       → 按科目聚合 avg / median / 分布
    2. 聚合数据 → ProviderRouter / DeepSeek 生成自然语言分析
    3. 返回 ReadClassGradeSummaryOutput（★无 PII）
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from statistics import median as calc_median
from typing import Any, Dict, List, Optional

import pydantic
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.access import student_id_scope
from core.models import Class as ClassModel, Student, User
from modules.grades.models import GradeExam, GradeRecord, GradeSubject

from ai_native.runtime.tool_descriptor import ToolDescriptor

logger = logging.getLogger(__name__)

FORBIDDEN_PII_KEYS = {"student_id", "student_name", "student_no", "phone", "id_card"}
TOOL_NAME = "read_class_grade_summary"
TOOL_VERSION = "0.1.0"


# ═══════════════════════════════════════════════════════════════
#  Output Contract（Inv 14 frozen — extra=forbid，拒绝 PII 字段）
# ═══════════════════════════════════════════════════════════════

class SubjectSummary(pydantic.BaseModel):
    """单科聚合（extra=forbid：拒绝 student_id/student_name 等 PII 字段）。"""
    model_config = pydantic.ConfigDict(extra="forbid")
    code: Optional[str] = None
    name: Optional[str] = None
    avg: Optional[float] = None
    median: Optional[float] = None
    full_score: Optional[float] = None
    distribution: dict[str, int] = pydantic.Field(default_factory=dict)


class ReadClassGradeSummaryOutput(pydantic.BaseModel):
    """班级/年级成绩摘要输出（Inv 14 frozen contract）。"""
    model_config = pydantic.ConfigDict(extra="forbid")

    class_id: Optional[int] = None
    grade_id: Optional[int] = None
    exam: Optional[dict] = None
    subjects: list[SubjectSummary] = pydantic.Field(default_factory=list)
    counts: dict[str, int] = pydantic.Field(default_factory=dict)
    summary: dict = pydantic.Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
#  Tool 元数据
# ═══════════════════════════════════════════════════════════════

def build_read_class_grade_summary_descriptor() -> ToolDescriptor:
    """返回 ToolDescriptor（用于 ToolRegistry 注册）。"""
    return ToolDescriptor(
        name=TOOL_NAME, version=TOOL_VERSION,
        description="读取班级/年级成绩摘要 — 聚合统计 + AI 分析（不含学生个人信息）",
        input_schema={}, output_schema={},
        action="read", side_effect="none", required_scope="class",
        declared_output_classification="student_pii",
        allowed_input_classification="internal",
        approval_policy="none", idempotent=True, timeout_seconds=60,
        supported_roles=["grade_leader", "class_teacher", "ms_admin"],
        handler=read_class_grade_summary_handler,
    )


def read_class_grade_summary_handler(run=None, **kwargs):  # noqa: ARG001
    """Tool 真实执行点（sync）：ProviderRouter → DeepSeekProvider → LLM 分析。

    run 上下文（由 services 编排注入）：
        aggregation（_Aggregator 聚合结果）/ data_classification / exam_id
    返回：{"output": {...}, "actual_classification": ..., "model_call": {...}}
    """
    from ai_native.runtime.provider_router import ProviderRouter

    ctx = (run or {}).get("aggregation") or {}
    data_classification = (run or {}).get("data_classification") or "internal"

    # ProviderRouter（禁止直接 DeepSeekProvider）
    router = ProviderRouter()
    provider = router.route(
        model="deepseek-chat", data_classification=data_classification,
    )

    data_json = ctx.get("data_json", "{}")
    messages = [
        {"role": "system", "content": (
            "你是一位有经验的中学教学分析师。请根据班级考试成绩统计数据生成简洁分析。"
            "只输出 JSON：{\"analysis\": \"...\", \"highlights\": \"...\", "
            "\"weaknesses\": \"...\", \"suggestions\": \"...\"}。"
            "不超过 300 字，不要提及任何学生个人姓名/学号等个人信息。"
        )},
        {"role": "user", "content": f"考试成绩统计数据：\n{data_json}"},
    ]

    llm_result: Dict[str, Any] = {}
    usage: Dict[str, Any] = {}
    try:
        content, usage = provider.call(messages, json_mode=True, temperature=0.3, max_tokens=1024)
        llm_result = json.loads(content)
    except Exception as exc:  # noqa: BLE001 — LLM 失败降级
        llm_result = {"analysis": f"模型调用失败: {exc}", "highlights": "",
                      "weaknesses": "", "suggestions": ""}

    return {
        "output": {"summary": llm_result},
        "actual_classification": "student_pii",
        "model_call": {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "usage": usage,
            "cost_amount": "0.001",
            "cost_currency": "CNY",
        },
    }


# ═══════════════════════════════════════════════════════════════
#  数据聚合（纯数据，无 PII，不调 LLM）
# ═══════════════════════════════════════════════════════════════

class _Aggregator:
    DISTRIBUTION_BANDS = [(0, 60), (60, 70), (70, 80), (80, 90), (90, 101)]

    def __init__(self, db: AsyncSession, school_id: int, user: User):
        self.db = db
        self.school_id = school_id
        self.user = user

    async def _resolve_scope(self) -> set[int] | None:
        scope = await student_id_scope(self.db, self.user)
        return None if scope is None else set(scope)

    async def _latest_published_exam(self, grade_id: int) -> Optional[int]:
        return (await self.db.execute(
            select(GradeExam.id).where(
                GradeExam.school_id == self.school_id,
                GradeExam.grade_id == grade_id,
                GradeExam.status == "published",
            ).order_by(GradeExam.exam_date.desc()).limit(1)
        )).scalar_one_or_none()

    async def aggregate(self, *, class_id=None, grade_id=None, exam_id=None,
                        effective_student_ids=None) -> Dict[str, Any]:
        """聚合班级/年级成绩摘要（纯数据，无 PII，不调 LLM）。

        effective_student_ids：由编排层 ResourceScopeResolver 产出（None=全校不限制）。
        """
        visible = effective_student_ids  # 授权事实来自编排层（core/access 经 Resolver）

        if exam_id is None:
            if grade_id is None:
                raise ValueError("grade_id 缺失")
            exam_id = await self._latest_published_exam(grade_id)
            if exam_id is None:
                raise ValueError(f"年级 {grade_id} 无已发布考试")

        exam = (await self.db.execute(
            select(GradeExam).where(GradeExam.school_id == self.school_id, GradeExam.id == exam_id)
        )).scalar_one_or_none()
        if exam is None:
            raise ValueError(f"考试 {exam_id} 不存在")

        if grade_id is None:
            grade_id = exam.grade_id

        filters = []
        if class_id is not None:
            filters.append(Student.class_id == class_id)
        if grade_id is not None:
            filters.append(Student.grade_id == grade_id)
        if visible is not None:
            filters.append(Student.id.in_(visible))

        rows = (await self.db.execute(
            select(GradeSubject.code, GradeSubject.name, GradeSubject.full_score, GradeRecord.score)
            .select_from(GradeRecord)
            .join(Student, GradeRecord.student_id == Student.id)
            .join(GradeSubject, GradeRecord.subject_id == GradeSubject.id)
            .where(and_(
                GradeRecord.exam_id == exam_id,
                Student.school_id == self.school_id,
                Student.is_active == True,  # noqa: E712
                *filters,
            ))
        )).all()

        if not rows:
            return self._empty(class_id, grade_id, exam)

        subject_scores: Dict[str, list[float]] = defaultdict(list)
        for code, name, full_score, score in rows:
            if score is not None:
                subject_scores[code].append(float(score))

        subjects = []
        for code, scores_list in subject_scores.items():
            avg = round(sum(scores_list) / len(scores_list), 2) if scores_list else None
            med = round(calc_median(scores_list), 2) if scores_list else None
            dist: Dict[str, int] = {}
            for lo, hi in self.DISTRIBUTION_BANDS:
                label = f"{lo}-{hi}" if hi < 101 else f"{lo}-100"
                c = sum(1 for s in scores_list if lo <= s < hi)
                if c > 0:
                    dist[label] = c
            subjects.append({"code": code, "name": code, "avg": avg, "median": med,
                             "full_score": None, "distribution": dist})

        return {
            "class_id": class_id, "grade_id": grade_id,
            "exam": {"id": exam.id, "name": exam.name,
                     "exam_date": str(exam.exam_date) if exam.exam_date else None,
                     "exam_type": exam.exam_type},
            "subjects": subjects,
            "counts": {"students": len(rows),
                       "examined": len(subject_scores[list(subject_scores)[0]]) if subject_scores else 0},
            "data_json": json.dumps({
                "exam": exam.name,
                "subjects": [{"name": s["name"], "avg": s["avg"], "median": s["median"],
                              "distribution": s["distribution"]} for s in subjects],
                "counts": {"examined": len(subject_scores[list(subject_scores)[0]]) if subject_scores else 0},
            }, ensure_ascii=False),
        }

    @staticmethod
    def _empty(class_id, grade_id, exam):
        return {"class_id": class_id, "grade_id": grade_id,
                "exam": {"id": exam.id, "name": exam.name,
                         "exam_date": str(exam.exam_date) if exam.exam_date else None,
                         "exam_type": exam.exam_type},
                "subjects": [], "counts": {"students": 0, "examined": 0},
                "data_json": json.dumps({"exam": exam.name, "subjects": [], "counts": {"examined": 0}}, ensure_ascii=False)}
