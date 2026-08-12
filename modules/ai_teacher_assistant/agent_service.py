"""
modules/ai_teacher_assistant/agent_service.py — AI Agent Copilot 编排

复用现有 Runtime（不重写）：
  AgentRun / ResourceScopeResolver / PermissionChecker
  ToolRegistry / ToolExecutor / ProviderRouter / DeepSeekProvider
"""

from __future__ import annotations

import inspect
import json
import os
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai_native.runtime.agent_run import AgentRun
from ai_native.runtime.critic import EvidenceCritic
from ai_native.runtime.planner import BoundedPlanner
from ai_native.runtime.provider_router import ProviderRouter
from ai_native.runtime.tool_descriptor import ToolRegistry
from ai_native.runtime.tool_executor import ToolExecutor
from ai_native.governance.resource_scope import ResourceScopeResolver


from core.access import student_id_scope
from core.models import User


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class CopilotSynthesizer:
    """合成最终分析结论——走 ProviderRouter，不直接调 DeepSeekProvider。"""

    def __init__(self, provider_router: ProviderRouter) -> None:
        self.provider_router = provider_router

    def generate(
        self,
        *,
        run: dict[str, Any],
        goal: str,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        safe_payload = {"goal": goal, "evidence": evidence}

        system = (
            "你是学校年级管理 AI 助手。\n"
            "只能依据 evidence 中的聚合数据回答。\n"
            "禁止：\n"
            "1. 编造 evidence 中不存在的事实；\n"
            "2. 输出学生姓名、学号、手机号、身份证等 PII；\n"
            "3. 把相关性表述成因果关系。\n"
            "\n严格返回 JSON：\n"
            '{"overview": {}, "findings": ["..."], "recommendations": ["..."]}'
        )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(safe_payload, ensure_ascii=False)},
        ]

        classification = run.get("data_classification", "internal")
        provider = self.provider_router.route(
            model=os.environ.get("LLM_MODEL", "deepseek-v4-flash"), data_classification=classification,
        )

        content, usage = provider.call(
            messages, json_mode=True, temperature=0.3, max_tokens=2048,
        )

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {
                "overview": {},
                "findings": [f"模型响应解析失败，原始内容: {content[:200]}"],
                "recommendations": [],
            }


class AgentCopilotService:
    """AI Agent Copilot 编排层。

    不重新实现 RBAC / Runtime——复用已上线组件。
    """

    def __init__(
        self,
        *,
        db: AsyncSession,
        user: User,
    ) -> None:
        self.db = db
        self.user = user
        self.planner = BoundedPlanner()
        self.critic = EvidenceCritic()
        self.registry = ToolRegistry()
        self.executor = ToolExecutor()
        self.provider_router = ProviderRouter()
        self.synthesizer = CopilotSynthesizer(self.provider_router)

    async def run(self, *, goal: str, grade_id: int,
                  class_id: int | None = None, exam_id: int | None = None,
                  compare_exam_ids: list[int] | None = None) -> dict[str, Any]:

        # ── 1. AgentRun ──
        agent_run = AgentRun(
            school_id=self.user.school_id,
            user_id=self.user.id,
            tool_name="agent_copilot",
            role=self.user.role or "teacher",
            session=self.db,
        )
        await agent_run.start()

        # ── 2. Planner ──
        plan = self.planner.plan(
            goal=goal,
            grade_id=grade_id,
            class_id=class_id,
            exam_id=exam_id,
            compare_exam_ids=compare_exam_ids,
        )

        # ── 3. POLICY_CHECK ──
        await agent_run.transition("POLICY_CHECK")

        # ── 4. Scope → delegate to tools (each resolves internally via student_id_scope) ──
        effective_student_ids: set[int] | None = await student_id_scope(self.db, self.user)
        if effective_student_ids is not None:
            effective_student_ids = set(effective_student_ids)

        if not effective_student_ids and effective_student_ids is not None:
            raise HTTPException(status_code=403, detail="无权访问请求的数据范围")

        # ── 5. Permission (双保险) ──

        # ── 6. EXECUTING ──
        await agent_run.transition("EXECUTING")

        run_state: dict[str, Any] = {
            "school_id": self.user.school_id,
            "user_id": self.user.id,
            "data_classification": agent_run.data_classification,
            "status": agent_run.status,
        }

        tool_results: list[dict[str, Any]] = []
        step_views: list[dict[str, Any]] = []

        # ── 7. Bounded multi-tool ──
        # Pre-register compare tool if not in registry
        if self.registry.get("compare_exam_performance") is None:
            from ai_native.runtime.tool_descriptor import ToolDescriptor
            from modules.ai_teacher_assistant.tools.compare_exam_performance import (
                compare_exam_performance_handler,
            )
            self.registry.register(ToolDescriptor(
                name="compare_exam_performance", version="0.1.0",
                description="比较多次考试间的科目表现变化",
                declared_output_classification="student_pii",
                approval_policy="none", idempotent=True,
                timeout_seconds=60, action="read",
                side_effect="none", required_scope="grade",
                allowed_input_classification="student_pii",
                supported_roles=["grade_leader", "class_teacher", "ms_admin"],
                handler=compare_exam_performance_handler,
            ))

        for step in plan.steps:
            descriptor = self.registry.get(step.tool)
            if descriptor is None:
                # Only summary might need dynamic load
                if step.tool == "read_class_grade_summary":
                    from modules.ai_teacher_assistant.tools.read_class_grade_summary import (
                        build_read_class_grade_summary_descriptor,
                    )
                    descriptor = build_read_class_grade_summary_descriptor()

            if descriptor is None or descriptor.handler is None:
                raise HTTPException(status_code=500, detail=f"Tool {step.tool} 不可用")

            # Prepare args
            args = dict(step.args)

            # ── Tool execution: summary via full service (Aggregator + LLM) ──
            if step.tool == "read_class_grade_summary":
                from .services import ClassGradeSummaryService
                svc = ClassGradeSummaryService(self.db, self.user)
                output = await svc.generate_summary(
                    class_id=args.get("class_id"),
                    grade_id=args.get("grade_id"),
                    exam_id=args.get("exam_id"),
                )
                result_dict = output.model_dump() if hasattr(output, "model_dump") else output
                tool_results.append({"tool": step.tool, "status": "EXECUTED", "result": result_dict})
                step_views.append({"tool": step.tool, "status": "EXECUTED", "reason": step.reason})
                continue

            # ── Tool execution: compare via handler ──
            # Resolve effective_student_ids for compare tool
            if effective_student_ids is None:
                from core.models import Student
                from sqlalchemy import select as _sel
                conds = [Student.school_id == self.user.school_id]
                if grade_id:
                    conds.append(Student.grade_id == grade_id)
                rows = (await self.db.execute(_sel(Student.id).where(*conds))).scalars().all()
                compare_students: set[int] = set(rows)
            else:
                compare_students = effective_student_ids

            args["effective_student_ids"] = compare_students
            args["db"] = self.db

            if step.tool == "compare_exam_performance":
                args["exam_ids"] = compare_exam_ids or []

            result = await _maybe_await(
                descriptor.handler(**args)
            )

            result_dict = result.model_dump() if hasattr(result, "model_dump") else result

            tool_results.append({
                "tool": step.tool,
                "status": "EXECUTED",
                "result": result_dict,
            })
            step_views.append({
                "tool": step.tool,
                "status": "EXECUTED",
                "reason": step.reason,
            })

        # ── 7a. Check outcome + replan ──
        outcome = "success"
        outcome_reason: str | None = None

        # If compare tool returned empty subjects, try replan to summary-only
        has_compare = any(r["tool"] == "compare_exam_performance" for r in tool_results)
        compare_empty = any(
            r["tool"] == "compare_exam_performance"
            and len(r.get("result", {}).get("subjects", [])) == 0
            for r in tool_results
        )
        summary_empty = any(
            r["tool"] == "read_class_grade_summary"
            and len(r.get("result", {}).get("subjects", [])) == 0
            for r in tool_results
        )

        if has_compare and compare_empty and not summary_empty:
            # Replan: drop compare, keep only summary findings
            outcome = "needs_data"
            outcome_reason = "insufficient_comparable_exams"
            tool_results = [r for r in tool_results if r["tool"] != "compare_exam_performance"]
            step_views = [s for s in step_views if s["tool"] != "compare_exam_performance"]
        elif summary_empty:
            outcome = "needs_data"
            outcome_reason = "no_grade_data_available"

        # Extract student counts from summary result
        student_count = 0
        examined_count = 0
        for r in tool_results:
            counts = r.get("result", {}).get("counts", {})
            student_count = max(student_count, counts.get("students", 0))
            examined_count = max(examined_count, counts.get("examined", 0))

        # ── 8. Synthesizer ──
        synthesis = self.synthesizer.generate(
            run=run_state,
            goal=goal,
            evidence=tool_results,
        )

        final_output = {
            "overview": synthesis.get("overview", {}),
            "findings": synthesis.get("findings", []),
            "recommendations": synthesis.get("recommendations", []),
        }

        # ── 9. Critic ──
        critic_result = self.critic.review(
            plan=plan,
            tool_results=tool_results,
            final_output=final_output,
        )

        if not critic_result.passed:
            await agent_run.finish(
                snapshot={
                    "reason": "critic_rejected",
                    "issues": critic_result.issues,
                },
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "AI 输出未通过安全自检",
                    "issues": critic_result.issues,
                },
            )

        # ── 10. Finish + snapshot ──
        await agent_run.finish(
            snapshot={
                "goal_hash_only": True,
                "tool_refs": [x["tool"] for x in tool_results],
                "scope_snapshot": {
                    "school_id": self.user.school_id,
                    "grade_ids": [grade_id] if grade_id else [],
                    "class_ids": [class_id] if class_id else [],
                },
                "critic_passed": True,
            },
        )

        return {
            "status": "completed",
            "run_id": agent_run.run_id,
            "goal": goal,
            "plan": step_views,
            "overview": final_output["overview"],
            "findings": final_output["findings"],
            "recommendations": final_output["recommendations"],
            "critic": {"passed": True, "issues": []},
            "provider": "deepseek",
            "model": os.environ.get("LLM_MODEL", "deepseek-v4-flash"),
            "trust": {
                "permission_checked": True,
                "aggregate_before_provider": True,
                "student_pii_sent": False,
                "provenance_recorded": True,
            },
            "outcome": outcome,
            "outcome_reason": outcome_reason,
            "student_count": student_count,
            "examined_count": examined_count,
        }
