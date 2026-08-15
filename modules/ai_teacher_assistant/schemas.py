"""
modules/ai_teacher_assistant/schemas.py — 请求/响应 Pydantic 模型
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClassGradeSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    class_id: Optional[int] = Field(None, description="班级 ID，与 grade_id 二选一")
    grade_id: Optional[int] = Field(None, description="年级 ID")
    exam_id: Optional[int] = Field(None, description="考试 ID，默认最新已发布考试")

    @model_validator(mode="after")
    def _at_least_one_scope(self):
        if self.class_id is None and self.grade_id is None:
            raise ValueError("class_id 与 grade_id 至少填一个")
        return self


class ClassGradeSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: Optional[int] = None
    status: str = "completed"
    output: Optional[dict] = None
    error: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# Agent Copilot V1 schemas
# ═══════════════════════════════════════════════════════════════

from typing import Any as _Any


class CopilotRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=2, max_length=500)
    grade_id: int
    class_id: int | None = None
    exam_id: int | None = None
    compare_exam_ids: list[int] | None = None


class CopilotStepView(BaseModel):
    tool: str
    status: str
    reason: str


class CopilotCriticView(BaseModel):
    passed: bool
    issues: list[str]


class CopilotRunResponse(BaseModel):
    status: str
    run_id: int
    approval_id: Optional[int] = None  # FT-015: awaiting_approval 时返回
    goal: str
    plan: list[CopilotStepView]
    overview: dict[str, _Any]
    findings: list[str]
    recommendations: list[str]
    critic: CopilotCriticView
    provider: str
    model: str
    trust: dict[str, _Any]
    # V2 product semantics
    outcome: str = "success"  # success | needs_data | needs_input | denied | failed
    outcome_reason: str | None = None
    student_count: int = 0
    examined_count: int = 0
    grade_record_count: int = 0
    domain_counts: dict[str, int] | None = None
    domains: dict[str, _Any] | None = None


class AvailableScopeGrade(BaseModel):
    id: int
    name: str


class AvailableScopesResponse(BaseModel):
    school: dict[str, _Any]
    grades: list[AvailableScopeGrade]
    default_grade_id: int | None = None
