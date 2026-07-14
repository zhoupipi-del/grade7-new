"""
Data Adapter Pydantic 模型
"""

from typing import Any

from pydantic import BaseModel

# ============================================================
# 错误输出
# ============================================================


class CleanErrorOut(BaseModel):
    row: int
    column: str
    raw_value: str
    error_type: str
    message: str


# ============================================================
# 上传成绩响应
# ============================================================


class UploadScoresResponse(BaseModel):
    status: str  # completed / completed_with_errors / failed
    phase: str  # primary / junior / senior / integrated
    template_code: str
    template_name: str
    total_rows: int
    success_rows: int
    failed_rows: int
    skipped_rows: int
    errors: list[CleanErrorOut] = []
    preview_data: list[dict[str, Any]] = []
    message: str = ""
    task_id: int | None = None
    pipeline_summary: dict[str, Any] | None = None  # 高中赋分管道反馈
    sync_status: str | None = "imported"  # native/legacy/imported


class TaskOut(BaseModel):
    """导入任务详情"""

    id: int
    filename: str
    status: str
    phase: str
    template_code: str | None = None
    total_rows: int
    success_rows: int
    failed_rows: int
    skipped_rows: int
    sync_status: str | None = "imported"
    errors_summary: Any | None = None
    created_by: int | None = None
    created_at: Any | None = None

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    """导入任务列表"""

    tasks: list[TaskOut]
    total: int
    page: int
    page_size: int


# ============================================================
# 模板列表
# ============================================================


class TemplateSubjectOut(BaseModel):
    raw_name: str  # Excel 中的列名
    standard_name: str  # 标准学科名


class TemplateOut(BaseModel):
    code: str
    name: str
    source_type: str
    phase: str
    subjects: list[TemplateSubjectOut] = []


class TemplateListResponse(BaseModel):
    templates: list[TemplateOut] = []
    total: int = 0


# ============================================================
# 预览响应
# ============================================================


class PreviewResponse(BaseModel):
    phase: str
    template_code: str
    template_name: str
    total_previewed: int
    success_count: int
    failed_count: int
    skipped_count: int
    rows: list[dict[str, Any]] = []
    errors: list[CleanErrorOut] = []
