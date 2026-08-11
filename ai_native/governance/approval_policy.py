"""
ai_native.governance.approval_policy — ApprovalPolicy + PolicyAdapter（frozen contract）
========================================================================================

唯一合法值（GOVERNANCE GATE 冻结）：
    NONE           = "none"
    ALWAYS         = "always"
    POLICY_DECIDES = "policy_decides"

★ ApprovalPolicy 必须是 `str, Enum`（string enum）：后续经 Pydantic / JSON /
  ToolDescriptor / DB binding 时按字符串持久化，禁止序列化差异。

PolicyAdapter（最小接口，本 gate 只定接口不实现）：
    Runtime 下一刀（ToolExecutor）依赖本接口做 approval 判定，而不是自己发明。
    本 gate 不实现：ai_approvals workflow / CommandEnvelope / human approval API。

tenant 语义：将来若出现跨学校集团级角色，应显式设计 authorized_school_ids，
    不得拿 school_id=None 表示"所有租户"（fail-open 禁止）。
"""

from __future__ import annotations

import enum
from typing import Any, Protocol, runtime_checkable


class ApprovalPolicy(str, enum.Enum):
    NONE = "none"
    ALWAYS = "always"
    POLICY_DECIDES = "policy_decides"


@runtime_checkable
class PolicyAdapter(Protocol):
    """
    最小审批判定接口（frozen contract，实现留待后续 gate）。

    decide() -> bool：是否放行该 (user, agent, tool, resource_scope, action)。
    参数保持鸭子类型，不引具体 model，避免循环依赖。
    """

    def decide(
        self,
        *,
        policy: ApprovalPolicy,
        user: Any,
        agent: Any,
        tool: Any,
        resource_scope: Any,
        action: str,
    ) -> bool: ...
