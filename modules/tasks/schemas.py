"""
modules/tasks/schemas.py — Task Center Foundation V1 请求/响应模型
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── 创建 ──
class TaskCreate(BaseModel):
    """人工创建任务（V1 第一条真实任务：年级组长 → 班主任跟进）"""
    title: str = Field(..., min_length=1, max_length=200, description="任务标题")
    description: Optional[str] = Field(None, max_length=2000, description="任务说明")
    priority: str = Field("normal", description="优先级: low/normal/high/urgent")
    due_at: Optional[datetime] = Field(None, description="截止时间（可选）")

    # 责任解析目标（三选一，走 ResponsibleOwnerResolver，禁止猜人）：
    student_id: Optional[int] = Field(None, gt=0, description="学生ID → 解析班主任")
    grade_id: Optional[int] = Field(None, gt=0, description="年级ID → 解析年级组长")
    subject: Optional[str] = Field(None, max_length=32, description="学科（配合 student_id → 任课教师）")

    # 来源关联（可选；student→class→grade 由服务端派生）
    source_type: Optional[str] = Field(None, max_length=32, description="来源类型（behavior/attendance/class_affair...）")
    source_id: Optional[int] = Field(None, gt=0, description="来源记录ID")
    class_id: Optional[int] = Field(None, gt=0, description="班级ID（不填则由 student_id 派生）")


# ── 状态流转 ──
class TaskReassign(BaseModel):
    new_owner_user_id: int = Field(..., gt=0, description="新负责人用户ID（须同校且持有效岗位）")
    reason: Optional[str] = Field(None, max_length=500, description="转交原因")


# ── 证据 / 评论 ──
class EvidenceCreate(BaseModel):
    kind: str = Field("note", description="note / communication_record / file")
    content: Optional[str] = Field(None, max_length=4000)
    file_path: Optional[str] = Field(None, max_length=500)
    file_name: Optional[str] = Field(None, max_length=255)


class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


# ── 输出 ──
class TaskAssignmentOut(BaseModel):
    id: int
    assignment_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    owner_name_snapshot: Optional[str] = None
    responsibility_role: Optional[str] = None
    responsibility_scope_type: Optional[str] = None
    responsibility_scope_id: Optional[int] = None
    resolution_source: Optional[str] = None
    resolution_confidence: Optional[str] = None
    resolved_at: Optional[datetime] = None
    reassigned_from_user_id: Optional[int] = None
    assigned_by: Optional[int] = None
    assigned_at: Optional[datetime] = None
    is_current: bool = True


class TaskEventOut(BaseModel):
    id: int
    event_type: str
    actor_user_id: Optional[int] = None
    actor_name: Optional[str] = None
    detail: Optional[dict] = None
    created_at: Optional[datetime] = None


class TaskEvidenceOut(BaseModel):
    id: int
    kind: str
    content: Optional[str] = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None


class TaskCommentOut(BaseModel):
    id: int
    content: str
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None


class TaskOut(BaseModel):
    id: int
    school_id: int
    task_type: str
    title: str
    description: Optional[str] = None
    status: str
    priority: str
    due_at: Optional[datetime] = None

    # 责任快照
    owner_user_id: Optional[int] = None
    owner_name_snapshot: Optional[str] = None
    responsibility_role: Optional[str] = None
    responsibility_scope_type: Optional[str] = None
    responsibility_scope_id: Optional[int] = None
    resolution_source: Optional[str] = None
    resolution_confidence: Optional[str] = None
    resolved_at: Optional[datetime] = None
    assignment_id: Optional[int] = None
    unresolved_reason: Optional[str] = None

    # 来源关联
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    student_id: Optional[int] = None
    class_id: Optional[int] = None
    grade_id: Optional[int] = None

    # 处理时间线留痕
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None

    # closure
    closure_status: Optional[str] = None
    closed_at: Optional[datetime] = None

    created_by: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    assignments: list[TaskAssignmentOut] = []
    events: list[TaskEventOut] = []
    evidence: list[TaskEvidenceOut] = []
    comments: list[TaskCommentOut] = []


class TaskListOut(BaseModel):
    total: int
    items: list[TaskOut]


class TaskActionOut(BaseModel):
    id: int
    status: str
    message: str
