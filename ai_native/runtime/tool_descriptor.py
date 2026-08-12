"""
ai_native.runtime.tool_descriptor — ToolDescriptor + ToolRegistry（Inv 15）
===========================================================================

ToolDescriptor 15 字段全量（frozen contract）：
    name / version / description / input_schema / output_schema / action /
    side_effect / required_scope / declared_output_classification /
    allowed_input_classification / approval_policy / idempotent /
    timeout_seconds / supported_roles / handler

注册必填（缺一即 registration FAIL，raise ValueError）：
    action / side_effect / required_scope / declared_output_classification /
    allowed_input_classification

approval_policy 仅 {none, always, policy_decides}（复用 governance.ApprovalPolicy）；
禁止第二套审批模型（requires_human / auto_approve_when_self 不存在）。

对应测试：tests/ai_native/test_tool_descriptor_contract.py::TestInv15*
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ai_native.governance.approval_policy import ApprovalPolicy

REQUIRED_ON_REGISTER = (
    "action",
    "side_effect",
    "required_scope",
    "declared_output_classification",
    "allowed_input_classification",
)

ALLOWED_APPROVAL_POLICIES = {p.value for p in ApprovalPolicy}


@dataclass
class ToolDescriptor:
    """Tool 元数据契约（15 字段）。构造即校验必填字段与 approval_policy 白名单。"""

    name: str = ""
    version: str = ""
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    action: str = ""
    side_effect: str = ""
    required_scope: str = ""
    declared_output_classification: str = ""
    allowed_input_classification: str = ""
    approval_policy: str = "none"
    idempotent: bool = False
    timeout_seconds: int = 0
    supported_roles: List[str] = field(default_factory=list)
    handler: Any = None

    def __post_init__(self) -> None:
        # 必填字段：缺一即 registration FAIL
        for req in REQUIRED_ON_REGISTER:
            if not getattr(self, req):
                raise ValueError(f"ToolDescriptor 缺少必填字段: {req}")
        # approval_policy 白名单（禁止第二套审批模型）
        if self.approval_policy not in ALLOWED_APPROVAL_POLICIES:
            raise ValueError(
                f"approval_policy 非法: {self.approval_policy!r}，"
                f"仅允许 {sorted(ALLOWED_APPROVAL_POLICIES)}"
            )
        if not self.name or not self.version:
            raise ValueError("ToolDescriptor 缺少 name/version")


class ToolRegistry:
    """按 name 注册/查询 ToolDescriptor（注册时双保险校验）。"""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDescriptor] = {}

    def register(self, descriptor: ToolDescriptor) -> None:
        if not isinstance(descriptor, ToolDescriptor):
            raise TypeError(
                f"期望 ToolDescriptor，得到 {type(descriptor).__name__}"
            )
        descriptor.__post_init__()  # 双保险：构造外显式校验（幂等）
        self._tools[descriptor.name] = descriptor

    def tool_names(self) -> List[str]:
        return list(self._tools)

    def get(self, name: str) -> ToolDescriptor | None:
        return self._tools.get(name)
