"""
modules/approval/schemas.py — 多租户审批链 Pydantic 模型
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════
# 审批节点模板
# ═══════════════════════════════════════════════════════════════


class TimeoutConfig(BaseModel):
    """节点超时配置"""

    timeout_hours: int = Field(default=24, ge=1, le=720, description="超时小时数")
    action_on_timeout: Literal["auto_approve", "escalate", "deny"] = Field(
        default="escalate", description="超时动作"
    )
    notify_on_timeout: bool = Field(default=True, description="超时是否通知")


class ApprovalNodeSchema(BaseModel):
    """审批节点模板"""

    node_index: int = Field(default=0, ge=0, description="节点序号（从0开始）")
    node_name: str = Field(default="审批节点", max_length=50)
    approver_type: Literal["ROLE", "USER"] = Field(default="ROLE")
    approver_value: str = Field(
        default="class_teacher",
        max_length=100,
        description="角色名(class_teacher/grade_leader/dean) 或 user_id",
    )
    timeout_config: TimeoutConfig = Field(default_factory=TimeoutConfig)


# ═══════════════════════════════════════════════════════════════
# CRUD 输入输出
# ═══════════════════════════════════════════════════════════════


class TenantApprovalChainCreate(BaseModel):
    """创建审批链"""

    business_type: str = Field(..., max_length=50, description="业务类型")
    chain_name: str = Field(..., max_length=100, description="链名称")
    nodes: list[ApprovalNodeSchema] = Field(
        ..., min_length=1, max_length=10, description="审批节点列表"
    )
    description: str | None = Field(default=None, max_length=500)


class TenantApprovalChainUpdate(BaseModel):
    """更新审批链（节点变更会触发版本号自增）"""

    chain_name: str | None = Field(default=None, max_length=100)
    nodes: list[ApprovalNodeSchema] | None = Field(default=None, min_length=1, max_length=10)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = Field(default=None)


class TenantApprovalChainResponse(BaseModel):
    """审批链响应"""

    id: int
    school_id: int
    business_type: str
    chain_name: str
    version: int
    is_active: bool
    nodes: list[ApprovalNodeSchema]
    description: str | None = None
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class TenantApprovalChainListResponse(BaseModel):
    """审批链列表"""

    items: list[TenantApprovalChainResponse]
    total: int


class ChainActivateResponse(BaseModel):
    """激活结果"""

    message: str
    chain_id: int
    previous_active_id: int | None = None


# ═══════════════════════════════════════════════════════════════
# 快照转换结果 (内部使用，不对外暴露 API)
# ═══════════════════════════════════════════════════════════════


class ChainSnapshot(BaseModel):
    """从模板转换到工单快照的结果"""

    chain_config: dict
    approval_mode: str  # parallel_or / serial_and
    severity: str  # minor / major / critical
    total_timeout_hours: int
    escalation_strategy: str


# ═══════════════════════════════════════════════════════════════
# 运行时审批工单 (前端 ApprovalTicket 契约)
# ═══════════════════════════════════════════════════════════════


class ApprovalRuntimeNode(BaseModel):
    """运行时审批节点（快照格式 — 对应前端 ApprovalNode）"""

    node_id: str
    node_name: str
    assignee_role: str
    assignee_name: str | None = None
    status: str  # approved / pending / waiting / rejected
    update_time: str | None = None


class ApprovalTicketResponse(BaseModel):
    """审批工单（动态链视图 — 对应前端 ApprovalTicket）"""

    ticket_id: str
    title: str
    applicant_name: str
    tenant_school: str
    created_at: str
    deadline_at: str
    current_node_index: int
    chain_config: list[ApprovalRuntimeNode]


class PendingCountResponse(BaseModel):
    """待审批计数"""

    pending: int


class ApprovalRequestResponse(BaseModel):
    """审批请求详情"""

    id: int
    student_id: int
    student_name: str | None = None
    event_type: str
    source_type: str
    source_id: int
    severity: str
    approval_mode: str
    chain_config: dict
    current_status: str
    current_step: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None


class ApprovalRequestListResponse(BaseModel):
    """审批请求列表（分页）"""

    items: list[ApprovalRequestResponse]
    total: int
    page: int
    page_size: int


class ApproveRequestInput(BaseModel):
    """批准请求输入"""

    comment: str | None = None


class RejectRequestInput(BaseModel):
    """驳回请求输入"""

    comment: str = Field(..., min_length=1, max_length=500)


class UrgeResponse(BaseModel):
    """催办响应"""

    message: str
    ticket_id: str
    node_id: str
