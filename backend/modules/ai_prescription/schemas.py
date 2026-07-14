"""
AI 德育处方大脑 — Pydantic Schemas
混合输出格式：summary（核心摘要）+ full_text（完整 Markdown）
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────
# 请求体
# ─────────────────────────────────────────────


class ClassDiagnosisRequest(BaseModel):
    """发起班级月度诊断"""

    class_id: int = Field(..., description="班级 ID")
    semester: str | None = Field(
        None, description="学期标签，如 '2025-2026-2'；不填则自动用当前学期"
    )
    analysis_days: int = Field(30, ge=7, le=180, description="回溯分析天数（默认 30 天）")


class StudentInterventionRequest(BaseModel):
    """发起学生心理干预话术生成"""

    student_id: int = Field(..., description="学生 ID")
    analysis_days: int = Field(30, ge=7, le=180, description="回溯分析天数（默认 30 天）")


# ─────────────────────────────────────────────
# 响应体
# ─────────────────────────────────────────────


class PrescriptionTaskOut(BaseModel):
    """异步任务提交响应（202 Accepted）"""

    task_id: str = Field(..., description="Celery 任务 ID")
    status: str = Field("PENDING", description="初始状态")
    message: str = Field("AI 处方生成任务已提交，请轮询结果", description="提示信息")


class TaskStatusOut(BaseModel):
    """任务轮询响应"""

    task_id: str
    status: str = Field(..., description="PENDING / PROGRESS / SUCCESS / FAILURE / REVOKED")
    result: dict | None = Field(None, description="SUCCESS 时返回 {record_id, risk_level, summary}")
    error: str | None = Field(None, description="FAILURE 时返回错误信息")


class PrescriptionResultOut(BaseModel):
    """处方完成结果（附带完整 Markdown）"""

    record_id: int
    prescription_type: str
    target_id: int
    target_type: str
    risk_level: str | None = None
    summary: str | None = None
    full_text: str = Field(..., description="完整 Markdown 诊断书 / 干预话术")
    raw_snapshot: Any | None = Field(None, description="原始上下文快照（JSON）")
    creator_id: int | None = None
    created_at: str | None = None


class PrescriptionHistoryItem(BaseModel):
    """历史处方列表单项"""

    id: int
    prescription_type: str
    target_id: int
    target_type: str
    risk_level: str | None = None
    summary: str | None = None
    created_at: str
    creator_name: str | None = None


class PrescriptionHistoryOut(BaseModel):
    """历史处方列表（分页）"""

    total: int
    items: list[PrescriptionHistoryItem]
