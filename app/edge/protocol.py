"""WINGS Edge Core — Edge↔Cloud 通信协议契约（Step 0）。

源: WINGS Secure Fabric BASELINE FINAL v1.0 FROZEN / Step 0
ERRATA-001: 补 `from .base import HealthStatus` import
ERRATA-002: TaskResult.status 锁 TaskStatus Enum（不再允许自由字符串）
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .base import HealthStatus


class TaskType(str, Enum):
    SYNC_DELTA = "sync_delta"
    FETCH_RECORD = "fetch_record"
    HEALTH_CHECK = "health_check"
    RESOLVE_IDENTITY = "resolve_identity"
    AI_CONTEXT_BUILD = "ai_context_build"
    EXECUTE_COMMAND = "execute_command"


class TaskStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class EdgeTask(BaseModel):
    task_id: UUID
    school_id: int
    task_type: TaskType
    connector_name: Optional[str] = None
    payload: dict = Field(default_factory=dict)
    created_at: datetime
    timeout_sec: int = 30


class TaskResult(BaseModel):
    task_id: UUID
    status: TaskStatus
    data: Optional[dict] = None
    error: Optional[str] = None
    started_at: datetime
    finished_at: datetime


class EdgeHeartbeat(BaseModel):
    edge_id: str
    school_id: int
    version: str
    timestamp: datetime

    cpu_percent: float
    memory_percent: float
    disk_percent: float

    connectors: dict[str, HealthStatus]
    pending_tasks: int

    # Edge Secure 状态，未安装时 None
    vault_status: Optional[str] = None
    privacy_gateway_status: Optional[str] = None

    # Fabric Network 状态，未安装时 None
    fabric_status: Optional[str] = None
