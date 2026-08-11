"""
ai_native.governance — 治理层（Slice 1, GOVERNANCE GATE 第一刀 + REVISE 轮）
============================================================================

本 gate 实现 governance 层（对应 RED 测试的 Governance 侧契约）：
    - data_classification  — DataClassification（str Enum）四级枚举 + TaintLogic（Inv 13）
    - resource_scope       — ResourceScope canonical model + Resolver（Inv 2 / Inv 14 scope 侧）
    - approval_policy      — ApprovalPolicy（str Enum）+ 最小 PolicyAdapter 接口

阶段边界（严格）：
    runtime/*（ToolDescriptor / ToolExecutor / ProviderRouter / AgentRun）
    与 modules/ai_teacher_assistant/*（业务 Tool）不在本 gate。
    本包不触碰 9 表 ORM、不新增 Alembic revision。
"""

from ai_native.governance.approval_policy import ApprovalPolicy, PolicyAdapter
from ai_native.governance.data_classification import DataClassification, TaintLogic
from ai_native.governance.resource_scope import (
    ResourceScope,
    ResourceScopeResolver,
    resolve_scope,
)

__all__ = [
    "ApprovalPolicy",
    "PolicyAdapter",
    "DataClassification",
    "TaintLogic",
    "ResourceScope",
    "ResourceScopeResolver",
    "resolve_scope",
]
