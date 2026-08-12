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
