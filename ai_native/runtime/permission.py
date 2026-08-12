"""
ai_native.runtime.permission — Permission 判定（纵向闭环第 4 步）
================================================================

Permission(user, agent, tool, resource, action) -> bool

复用 core/access.py 的授权语义 + governance.ResourceScopeResolver（交集），
不另起第二套 RBAC：
    - resource 可见性：authorized scope 来自 core/access.py 语义
      （None=租户内不限制 / [] = 零可见 / {..} = 白名单），本层只做交集判定
    - action 允许性：tool.action 与 tool.supported_roles 约束

Slice 1 最小实现（第一刀 read_class_grade_summary 为只读 Tool）。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ai_native.governance.resource_scope import ResourceScope, resolve_scope


def _scope_has_any(scope: ResourceScope) -> bool:
    """effective scope 是否含任何可见维度（用于 deny 判定）。"""
    return bool(
        (scope.grade_ids is not None and len(scope.grade_ids) > 0)
        or (scope.class_ids is not None and len(scope.class_ids) > 0)
        or (scope.student_ids is not None and len(scope.student_ids) > 0)
    )


class PermissionChecker:
    """最小权限判定：resource ∩ action 双层检查。"""

    def check(
        self,
        *,
        user: Any,
        agent: Any,
        tool: Any,
        requested: Any,
        authorized: Any,
        action: str,
    ) -> bool:
        """
        - requested ∩ authorized 为空（无任何可见维度）→ False
        - action 不在 tool 允许动作集 → False
        - 其余 → True
        """
        # resource 维度：交集（tenant fail-close 由 Resolver 保证）
        effective = resolve_scope(requested, authorized)
        if not _scope_has_any(effective):
            return False

        # action 维度：tool 声明的动作
        allowed_actions = getattr(tool, "action", None)
        if allowed_actions and action != allowed_actions:
            return False

        # supported_roles 约束（可选的粗粒度角色门）
        roles = getattr(tool, "supported_roles", None)
        user_role = getattr(user, "role", None)
        if roles and user_role not in roles:  # ← 缺角色 → deny，不再 allow None
            return False

        return True
