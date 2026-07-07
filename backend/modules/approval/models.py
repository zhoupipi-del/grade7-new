"""
modules/approval/models.py — 多租户动态审批链模型

TenantApprovalChain 是审批链的"配置模板"，存储各学校对各业务类型的审批规则。
运行时创建 ApprovalRequest 时，从模板快照 nodes → chain_config 字段。

三层隔离:
  L1 数据层 — school_id 行级隔离 + 复合索引
  L2 控制层 — FastAPI 依赖注入 (current_user.school_id)
  L3 执行层 — 快照拷贝 (工单创建时冻结规则，不受后续模板变更影响)
"""

from sqlalchemy import (
    Column, BigInteger, Integer, String, Boolean, DateTime, JSON,
    UniqueConstraint, Index,
)

from core.models import Base, SchoolMixin, get_local_now


class TenantApprovalChain(Base, SchoolMixin):
    """
    多租户动态审批链模板 — 按学校+业务类型存储审批规则。

    nodes JSON 格式:
    [
      {
        "node_index": 0,
        "node_name": "班主任审批",
        "approver_type": "ROLE",        // ROLE 或 USER
        "approver_value": "class_teacher",  // 角色名 或 user_id
        "timeout_config": {
          "timeout_hours": 24,
          "action_on_timeout": "auto_approve",  // auto_approve | escalate | deny
          "notify_on_timeout": true
        }
      }
    ]

    唯一约束: (school_id, business_type, version)
    激活约束: 同一 (school_id, business_type) 只有一个 is_active=True
    """
    __tablename__ = "tenant_approval_chains"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # 业务类型: behavior_minor, behavior_major, behavior_critical,
    #           attendance_leave, attendance_absence, ai_intervention
    business_type = Column(String(50), nullable=False, index=True)
    chain_name = Column(String(100), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)

    # 审批节点配置 (JSON Array)
    nodes = Column(JSON, nullable=False)

    # 备注
    description = Column(String(500), nullable=True)

    created_by = Column(BigInteger, nullable=True, comment="创建人 user_id")
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        UniqueConstraint("school_id", "business_type", "version",
                         name="uq_tac_business_version"),
        Index("idx_tac_active", "school_id", "business_type", "is_active"),
    )
