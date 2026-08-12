"""
ai_native/runtime/critic.py — V1 确定性安全 Critic

不做模型自评。检查：
1. 输出无 PII
2. Tool 执行覆盖度
3. Tool 失败检测
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


FORBIDDEN_KEYS = {
    "student_id",
    "student_name",
    "student_no",
    "phone",
    "id_card",
    "identity_card",
}


class CriticResult(BaseModel):
    passed: bool
    issues: list[str]
    correction: str | None = None


def _scan_forbidden(value: Any, path: str = "$") -> list[str]:
    issues: list[str] = []

    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_KEYS:
                issues.append(f"forbidden field: {path}.{key}")
            issues.extend(_scan_forbidden(child, f"{path}.{key}"))

    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            issues.extend(_scan_forbidden(child, f"{path}[{index}]"))

    return issues


class EvidenceCritic:
    """V1 确定性安全 Critic。"""

    def review(
        self,
        *,
        plan,
        tool_results: list[dict[str, Any]],
        final_output: dict[str, Any],
    ) -> CriticResult:
        issues: list[str] = []

        # 1. PII scan
        issues.extend(_scan_forbidden(final_output))

        # 2. Tool execution coverage
        executed = {
            item.get("tool")
            for item in tool_results
            if item.get("status") == "EXECUTED"
        }
        planned = {step.tool for step in plan.steps}
        missing = planned - executed
        if missing:
            issues.append("planned tools not executed: " + ", ".join(sorted(missing)))

        # 3. Evidence
        if not tool_results:
            issues.append("no tool evidence")

        # 4. Tool failures
        failures = [
            x.get("tool")
            for x in tool_results
            if x.get("status") != "EXECUTED"
        ]
        if failures:
            issues.append("tool execution failed: " + ", ".join(str(x) for x in failures))

        if issues:
            return CriticResult(
                passed=False,
                issues=issues,
                correction="删除无证据/越权/PII内容后重新生成最终答案",
            )

        return CriticResult(passed=True, issues=[], correction=None)
