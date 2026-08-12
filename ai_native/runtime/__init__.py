"""
ai_native.runtime — 运行时层（Slice 1, RUNTIME GATE）
====================================================

本 gate 实现 runtime 层（对应 RED 测试的 Runtime 侧契约）：
    - tool_descriptor  — ToolDescriptor（15 字段）+ ToolRegistry（Inv 15）
    - provider_router  — ModelCallRecord cost_currency 强制 + Provider 路由（Inv 21，复用 core/deepseek_provider）
    - tool_executor    — ToolExecutor（Inv 8 UNKNOWN_COMMIT / Inv 13 pre/post Taint 编排）+ CallSeqAllocator（Inv 27）
    - permission       — Permission 判定（复用 governance.ResourceScopeResolver）
    - agent_run        — AgentRun 最小闭环（状态机写入接口，对齐 9 表 ENUM）

阶段边界（严格）：
    modules/ai_teacher_assistant/*（业务 Tool，含 read_class_grade_summary）
    不在本 gate；不触碰 9 表 ORM、不新增 Alembic revision。
"""

from ai_native.runtime.agent_run import AgentRun
from ai_native.runtime.permission import PermissionChecker
from ai_native.runtime.provider_router import ModelCallRecord, ProviderRouter
from ai_native.runtime.tool_descriptor import ToolDescriptor, ToolRegistry
from ai_native.runtime.tool_executor import CallSeqAllocator, ToolExecutor, TransactionScopedSeqAllocator

__all__ = [
    "AgentRun",
    "PermissionChecker",
    "ModelCallRecord",
    "ProviderRouter",
    "ToolDescriptor",
    "ToolRegistry",
    "CallSeqAllocator",
    "TransactionScopedSeqAllocator",
    "ToolExecutor",
]
