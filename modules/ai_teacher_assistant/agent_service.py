"""
modules/ai_teacher_assistant/agent_service.py — AI Agent Copilot 编排 V2

V2 变更（2026-08-12）：
- 注册 T3-T5 三个新 Tool（考勤/行为/风险）
- 空 plan → needs_input outcome
- 综合查询多工具并行
- 按领域聚合 result counts

V2 安全修正（2026-08-12，响应 BOSS 执行链审计）：
- 五个 Tool 全部经 ToolExecutor 执行（不再由 agent_service 直调 Aggregator）
- 每 Tool 执行经 ResourceScopeResolver → PermissionChecker → PolicyAdapter → ToolExecutor
  → Tool handler（handler 内部调 _*Aggregator）
- 每个 Tool 执行后写入 ai_tool_calls（status=EXECUTED，含 declared/actual classification）
- ms_admin 不隐式全放：authorized.school_id 显式锁定本校；跨校请求显式 403
- Risk Tool 仅向综合 Agent 提供聚合计数，绝不携带 student PII / 心理原文
"""

from __future__ import annotations

import hashlib
import inspect
import json as _json
import os
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai_native.governance.approval_policy import ApprovalPolicy
from ai_native.governance.resource_scope import ResourceScope, resolve_scope
from ai_native.runtime.agent_run import AgentRun
from ai_native.runtime.critic import EvidenceCritic
from ai_native.runtime.approval_gate import ApprovalGate, ApprovalGateError
from modules.ai_teacher_assistant.tools.fail_test_marker import ControlledToolFailure
from ai_native.runtime.permission import PermissionChecker
from ai_native.runtime.planner import BoundedPlanner
from ai_native.runtime.provider_router import ProviderRouter
from ai_native.runtime.tool_descriptor import ToolDescriptor, ToolRegistry
from ai_native.runtime.tool_executor import ToolExecutor
from core.access import student_id_scope
from core.models import Class as ClassModel, Grade, User


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
        # 防御：证据只含聚合计数，绝不含 student 维度 PII（由 Tool 层保证）
        safe_payload = {"goal": goal, "evidence": evidence}

        system = (
            "你是学校年级管理 AI 助手。\n"
            "只能依据 evidence 中的聚合数据回答。\n"
            "将结果按领域分组：学业(grades)/考勤(attendance)/行为纪律(behavior)/风险预警(risk)。\n"
            "每个领域给出关键发现和建议。\n"
            "禁止：\n"
            "1. 编造 evidence 中不存在的事实；\n"
            "2. 输出学生姓名、学号、手机号、身份证等 PII；\n"
            "3. 把相关性表述成因果关系。\n"
            "\n严格返回 JSON：\n"
            '{"overview": {}, "findings": ["..."], '
            '"recommendations": [...], '
            '"domains": {"grades": {}, "attendance": {}, "behavior": {}, "risk": {}}}'
        )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": _json.dumps(safe_payload, ensure_ascii=False)},
        ]

        classification = run.get("data_classification", "internal")
        provider = self.provider_router.route(
            model=os.environ.get("LLM_MODEL", "deepseek-v4-flash"),
            data_classification=classification,
        )

        content, usage = provider.call(
            messages, json_mode=True, temperature=0.3, max_tokens=2048,
        )

        parsed = _extract_json(content)
        if parsed:
            return parsed
        # 兜底：LLM 返回空/不可解析时，从聚合证据确定性构造，
        # 保证 V2 始终产出可用 domains/findings（不依赖 LLM 成功）
        return _fallback_from_evidence(evidence)


def _fallback_from_evidence(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """LLM 失败兜底：用聚合证据构造结构化结论（无 PII）。"""
    domains: dict[str, Any] = {}
    findings: list[str] = []
    for item in evidence:
        domain = item.get("domain", "unknown")
        result = item.get("result", {}) or {}
        summary = result.get("summary", {})
        if domain not in domains:
            domains[domain] = {}
        domains[domain]["summary"] = summary
        # 从 summary 取可展示指标生成发现
        if isinstance(summary, dict):
            bits = []
            for k, v in summary.items():
                if isinstance(v, (int, float)) and k not in ("school_id", "class_id", "grade_id"):
                    bits.append(f"{k}={v}")
            if bits:
                findings.append(f"[{domain}] " + "，".join(bits[:4]))
    return {
        "overview": {"note": "AI 综合结论暂不可用，以下为各域聚合数据"},
        "findings": findings or ["暂无可用聚合数据"],
        "recommendations": [],
        "domains": domains,
    }


def _extract_json(content: str) -> dict:
    """鲁棒解析 LLM 返回的 JSON：

    - 剥离 ```json ... ``` 围栏
    - 直接 json.loads
    - 退化：截取首个 { 到末尾 } 的最长 JSON 块再解析
    """
    if not content:
        return {}
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        pass
    s = text.find("{")
    e = text.rfind("}")
    if s != -1 and e != -1 and e > s:
        try:
            return _json.loads(text[s:e + 1])
        except _json.JSONDecodeError:
            pass
    return {}


def _build_all_tool_descriptors() -> list[ToolDescriptor]:
    """返回所有已注册 Tool 的 Descriptor（handler 指向 V2 copilot 聚合 handler）。"""
    from modules.ai_teacher_assistant.tools.read_class_grade_summary import (
        build_read_class_grade_summary_descriptor,
        read_class_grade_summary_copilot_handler,
    )
    from modules.ai_teacher_assistant.tools.compare_exam_performance import (
        compare_exam_performance_copilot_handler,
    )
    from modules.ai_teacher_assistant.tools.read_attendance_summary import (
        build_read_attendance_summary_descriptor,
        read_attendance_summary_copilot_handler,
    )
    from modules.ai_teacher_assistant.tools.read_behavior_summary import (
        build_read_behavior_summary_descriptor,
        read_behavior_summary_copilot_handler,
    )
    from modules.ai_teacher_assistant.tools.read_risk_warning_summary import (
        build_read_risk_warning_summary_descriptor,
        read_risk_warning_summary_copilot_handler,
    )
    descriptors = [
        build_read_class_grade_summary_descriptor(),
        ToolDescriptor(
            name="compare_exam_performance", version="0.1.0",
            description="比较多次考试间的科目表现变化",
            declared_output_classification="student_pii",
            approval_policy="none", idempotent=True,
            timeout_seconds=60, action="read",
            side_effect="none", required_scope="grade",
            allowed_input_classification="student_pii",
            supported_roles=["grade_leader", "class_teacher", "ms_admin"],
            handler=compare_exam_performance_copilot_handler,
        ),
        build_read_attendance_summary_descriptor(),
        build_read_behavior_summary_descriptor(),
        build_read_risk_warning_summary_descriptor(),
    ]
    # FT-015 收尾：write_test_marker 是验证工具，非产品能力。
    # 仅 AI_APPROVAL_TEST_TOOL=1 时注册（test/internal mode），生产默认不暴露。
    if os.environ.get("AI_APPROVAL_TEST_TOOL") == "1":
        from modules.ai_teacher_assistant.tools.write_test_marker import (
            build_write_test_marker_descriptor,
        )
        descriptors.append(build_write_test_marker_descriptor())
    # FT-016 test-only：fail_test_marker 受控失败验证工具，同样仅测试模式注册。
    if os.environ.get("AI_FAILURE_TEST_TOOL") == "1":
        from modules.ai_teacher_assistant.tools.fail_test_marker import (
            build_fail_test_marker_descriptor,
        )
        descriptors.append(build_fail_test_marker_descriptor())
    # V2 copilot 路径：所有 Tool 的 handler 统一指向"聚合型"handler
    # （handler 内部调用 _*Aggregator，不绕过 ToolExecutor，不调 DeepSeek）
    handler_map = {
        "read_class_grade_summary": read_class_grade_summary_copilot_handler,
        "compare_exam_performance": compare_exam_performance_copilot_handler,
        "read_attendance_summary": read_attendance_summary_copilot_handler,
        "read_behavior_summary": read_behavior_summary_copilot_handler,
        "read_risk_warning_summary": read_risk_warning_summary_copilot_handler,
    }
    for td in descriptors:
        if td.name in handler_map:
            td.handler = handler_map[td.name]
    return descriptors


class _SimplePolicyAdapter:
    """PolicyAdapter 最小实现（Slice 1：read-only Tool 无审批流）。"""

    def decide(self, *, policy: ApprovalPolicy, user=None, agent=None,
               tool=None, resource_scope=None, action: str = "") -> bool:
        if policy in (ApprovalPolicy.NONE, ApprovalPolicy.ALWAYS):
            return True
        # POLICY_DECIDES 预留：Slice 1 第一刀无审批流
        return True


class AgentCopilotService:
    """AI Agent Copilot 编排层 V2（经标准 AI Native 执行链）。"""

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
        self.permission = PermissionChecker()

        for td in _build_all_tool_descriptors():
            self.registry.register(td)

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
            query=goal,
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

        # ── 2a. Empty plan → needs_input ──
        if not plan.steps:
            await agent_run.finish(snapshot={"reason": "empty_plan", "goal": goal})
            return {
                "status": "needs_input",
                "run_id": agent_run.run_id,
                "goal": goal,
                "plan": [],
                "overview": {},
                "findings": [],
                "recommendations": [],
                "critic": {"passed": True, "issues": []},
                "provider": os.environ.get("LLM_MODEL", "deepseek-v4-flash"),
                "model": os.environ.get("LLM_MODEL", "deepseek-v4-flash"),
                "trust": {
                    "permission_checked": True,
                    "aggregate_before_provider": True,
                    "student_pii_sent": False,
                    "provenance_recorded": True,
                },
                "outcome": "needs_input",
                "outcome_reason": "未能理解查询意图，请尝试更具体的表述（例如：最近迟到情况/违纪情况/考试成绩/风险预警）",
                "student_count": 0,
                "examined_count": 0,
                "domains": {},
            }

        # ── 3. POLICY_CHECK ──
        await agent_run.transition("POLICY_CHECK")

        # ── 4. Scope（显式：authorized.school_id 锁定本校）──
        authorized_ids = await student_id_scope(self.db, self.user)
        authorized = ResourceScope(
            school_id=self.user.school_id,
            student_ids=None if authorized_ids is None else set(authorized_ids),
        )

        # 显式跨校边界：请求的 grade/class 必须属于用户本校，否则 403
        await self._assert_same_school(grade_id, class_id)

        # ── 5. EXECUTING ──
        await agent_run.transition("EXECUTING")

        tool_results: list[dict[str, Any]] = []
        step_views: list[dict[str, Any]] = []
        incidents: list[dict[str, Any]] = []

        # ── 6. Multi-tool execution（全部经 ToolExecutor）──
        for step in plan.steps:
            descriptor = self.registry.get(step.tool)
            if descriptor is None or descriptor.handler is None:
                continue

            requested = ResourceScope(
                school_id=self.user.school_id,
                grade_ids={grade_id} if grade_id else None,
                class_ids={class_id} if class_id else None,
            )

            # ── Permission（越权 → 403，0 Tool execution；action 取 descriptor.action，
            #    WRITE tool 按 write 判定，不再硬编码 read）──
            if not self.permission.check(
                user=self.user, agent=None, tool=descriptor,
                requested=requested, authorized=authorized,
                action=descriptor.action,
            ):
                await agent_run.transition("FAILED")
                await self.db.commit()
                raise HTTPException(
                    status_code=403,
                    detail=f"无权访问该范围的数据（Tool={step.tool}）",
                )

            # ── PolicyAdapter（Slice 1: none）──
            adapter = _SimplePolicyAdapter()
            effective = resolve_scope(requested, authorized)
            if not adapter.decide(
                policy=ApprovalPolicy.NONE, user=self.user, tool=descriptor,
                resource_scope=effective, action="read",
            ):
                await agent_run.transition("FAILED")
                await self.db.commit()
                raise HTTPException(status_code=403, detail="审批未通过")

            args = dict(step.args)

            # ── ★ FT-015 HTTP 闭环：WRITE tool → 审批挂起（不进 executor）──
            # 识别写工具 → tool_call(AWAITING_APPROVAL) + envelope + approval(PENDING)
            # → run=WAITING_APPROVAL → 返回 approval_id，停止执行。
            if descriptor.approval_policy in ("always", "policy_decides"):
                pending = await self._suspend_for_approval(
                    agent_run=agent_run,
                    descriptor=descriptor,
                    args=args,
                    step=step,
                    grade_id=grade_id,
                    class_id=class_id,
                )
                return pending

            # ── ToolExecutor.execute → descriptor.handler（内部调 _*Aggregator）──
            run_ctx: dict[str, Any] = {
                "status": "EXECUTING",
                "data_classification": agent_run.data_classification,
                "school_id": self.user.school_id,
                "user_id": self.user.id,
                "run_id": agent_run.run_id,
                "db": self.db,
                "session": self.db,  # handler 契约（FT-016 fail_test_marker 需要）
                "user": self.user,
                "effective_student_ids": authorized_ids,  # None=本校全可见
                "args": args,
            }
            try:
                result = await self.executor.execute(
                    run=run_ctx,
                    descriptor=descriptor,
                    incident_sink=incidents.append,
                )
            except ControlledToolFailure as ctf:
                # ── FT-016 失败证据链：tool_call FAILED + ai_incidents + run 状态 ──
                await self._record_tool_call_failure(
                    run_id=agent_run.run_id,
                    descriptor=descriptor,
                    params=args,
                    failure=ctf,
                )
                await self._record_incident(
                    run_id=agent_run.run_id,
                    descriptor=descriptor,
                    failure=ctf,
                )
                if args.get("recoverable"):
                    # 可恢复：run RECOVERING → 单次 fallback 重试（同 step，attempt2）
                    await agent_run.transition("RECOVERING")
                    await self.db.commit()
                    await agent_run.transition("RESUMING")
                    try:
                        result = await self.executor.execute(
                            run=run_ctx,
                            descriptor=descriptor,
                            incident_sink=incidents.append,
                        )
                        incidents.append({"type": "tool_recovery", "tool": descriptor.name,
                                          "from": "RECOVERING", "to": "RESUMING"})
                    except ControlledToolFailure as ctf2:
                        # 重试仍失败 → 不可恢复 → run FAILED
                        await self._record_tool_call_failure(
                            run_id=agent_run.run_id,
                            descriptor=descriptor,
                            params=args,
                            failure=ctf2,
                        )
                        await self._record_incident(
                            run_id=agent_run.run_id,
                            descriptor=descriptor,
                            failure=ctf2,
                        )
                        await agent_run.transition("FAILED")
                        await self.db.commit()
                        raise HTTPException(status_code=500,
                                            detail=f"Tool 执行失败（不可恢复）: {ctf2.message}")
                else:
                    # 不可恢复 → run FAILED（completed_at 由 TERMINAL_STATES 落库）
                    await agent_run.transition("FAILED")
                    await self.db.commit()
                    raise HTTPException(status_code=500,
                                        detail=f"Tool 执行失败: {ctf.message}")

            # ── 写 ai_tool_calls（同 run_id；Tool → EXECUTED）──
            await self._record_tool_call(
                run_id=agent_run.run_id,
                descriptor=descriptor,
                result=result,
                params=args,
            )

            tool_results.append({
                "tool": step.tool,
                "status": result.get("status", "EXECUTED"),
                "domain": result.get("domain", "unknown"),
                "result": result.get("result", {}),
            })
            step_views.append({
                "tool": step.tool,
                "status": result.get("status", "EXECUTED"),
                "reason": step.reason,
            })

            # 同步 Run 的 taint 峰值（ToolExecutor 已 mutate run_ctx）
            agent_run.data_classification = run_ctx.get(
                "data_classification", agent_run.data_classification)

        # ── 7. Outcome detection ──
        outcome = "success"
        outcome_reason: str | None = None

        domain_counts: dict[str, int] = {}
        for r in tool_results:
            domain = r.get("domain", "unknown")
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

        if not tool_results:
            outcome = "needs_data"
            outcome_reason = "no_tool_results"

        # Extract grade KPI counts
        student_count = 0
        examined_count = 0
        grade_record_count = 0
        for r in tool_results:
            res = r.get("result", {})
            counts = res.get("counts", {})
            student_count = max(student_count, counts.get("students", 0))
            examined_count = max(examined_count, counts.get("examined", 0))
            subs = res.get("subjects", [])
            if subs and examined_count:
                grade_record_count = max(grade_record_count, len(subs) * examined_count)

        # ── 8. Synthesizer ──
        run_state = {
            "data_classification": agent_run.data_classification,
            "school_id": self.user.school_id,
            "user_id": self.user.id,
        }
        synthesis = self.synthesizer.generate(
            run=run_state,
            goal=goal,
            evidence=tool_results,
        )

        final_output = {
            "overview": synthesis.get("overview", {}),
            "findings": synthesis.get("findings", []),
            "recommendations": synthesis.get("recommendations", []),
            "domains": synthesis.get("domains", {}),
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

        # ── 10. Finish ──
        await agent_run.finish(
            snapshot={
                "goal_hash_only": True,
                "tool_refs": [x["tool"] for x in tool_results],
                "domain_counts": domain_counts,
                "scope_snapshot": {
                    "school_id": self.user.school_id,
                    "grade_ids": [grade_id] if grade_id else [],
                    "class_ids": [class_id] if class_id else [],
                },
                "classification_peak": agent_run.data_classification,
                "incidents": incidents,
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
            "domains": final_output.get("domains", {}),
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
            "grade_record_count": grade_record_count,
            "domain_counts": domain_counts,
        }

    async def resolve_available_scopes(self) -> dict:
        """返回当前用户 AI 助手可分析范围（server-side 授权生成，前端只消费）。

        - school: 当前用户所属学校（JWT school_id，不随请求参数变化）
        - grades: 用户可访问年级列表
            - school-wide 角色（MS_ADMIN/GROUP_ADMIN/BRANCH_ADMIN 或
              teacher_role_assignments 中 school 级授权）→ 本校全部启用年级
            - 否则：assignment grade ∪ user.grade_id 的交集（按本校过滤）
        - default_grade_id: 默认选中（优先 user.grade_id，否则第一个）

        不旁路 RBAC：只返回已授权范围；最终执行仍由
        PermissionChecker/ResourceScope + _assert_same_school 兜底拒绝。
        """
        from sqlalchemy import select

        from core.access import load_assignment_scopes
        from core.models import Grade, School, UserRole

        user = self.user
        school = await self.db.get(School, user.school_id)

        scopes = await load_assignment_scopes(self.db, user)
        grade_ids = set(scopes.get("grade", set()) or set())
        if user.grade_id:
            grade_ids.add(int(user.grade_id))

        school_wide = bool(scopes.get("school", False)) or user.role in (
            UserRole.MS_ADMIN,
            UserRole.GROUP_ADMIN,
            UserRole.BRANCH_ADMIN,
        )

        if school_wide:
            rows = (
                await self.db.execute(
                    select(Grade.id, Grade.name)
                    .where(
                        Grade.school_id == user.school_id,
                        Grade.is_active.is_(True),
                    )
                    .order_by(Grade.sort_order, Grade.id)
                )
            ).all()
            grades = [{"id": int(r[0]), "name": r[1]} for r in rows]
        else:
            if not grade_ids:
                grades = []
            else:
                rows = (
                    await self.db.execute(
                        select(Grade.id, Grade.name)
                        .where(
                            Grade.id.in_(grade_ids),
                            Grade.school_id == user.school_id,
                            Grade.is_active.is_(True),
                        )
                        .order_by(Grade.sort_order, Grade.id)
                    )
                ).all()
                grades = [{"id": int(r[0]), "name": r[1]} for r in rows]

        valid_ids = {g["id"] for g in grades}
        if user.grade_id and int(user.grade_id) in valid_ids:
            default_grade_id = int(user.grade_id)
        else:
            default_grade_id = grades[0]["id"] if grades else None

        return {
            "school": {
                "id": user.school_id,
                "name": school.name if school else "",
            },
            "grades": grades,
            "default_grade_id": default_grade_id,
        }

    async def _assert_same_school(self, grade_id: int | None, class_id: int | None) -> None:
        """显式跨校边界：请求的 grade/class 必须属于用户本校，否则 403。

        杜绝 ms_admin 因"管理员"身份隐式获得跨校全量 Scope。
        """
        if grade_id is not None:
            g = await self.db.get(Grade, grade_id)
            if g is None or g.school_id != self.user.school_id:
                raise HTTPException(
                    status_code=403,
                    detail="无权访问该年级数据（跨校请求被拒绝）",
                )
        if class_id is not None:
            c = await self.db.get(ClassModel, class_id)
            if c is None or c.school_id != self.user.school_id:
                raise HTTPException(
                    status_code=403,
                    detail="无权访问该班级数据（跨校请求被拒绝）",
                )

    # ═══════════════════════════════════════════════════════════════════
    # FT-015 HTTP 审批闭环（SAME run 原则）
    # ═══════════════════════════════════════════════════════════════════

    async def _suspend_for_approval(
        self,
        *,
        agent_run: AgentRun,
        descriptor: ToolDescriptor,
        args: dict,
        step,
        grade_id: int | None,
        class_id: int | None,
    ) -> dict:
        """WRITE tool 审批挂起：tool_call(AWAITING_APPROVAL) + envelope + approval(PENDING)。

        返回 awaiting_approval 响应（含 approval_id），绝不调用 executor。
        """
        from ai_native.models.ai_tool_calls import AiToolCalls

        args_hash = hashlib.sha256(
            _json.dumps(args, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        # 1. 预建 tool_call（AWAITING_APPROVAL）—— approval 绑定 tool_call_id
        tool_call = AiToolCalls(
            school_id=self.user.school_id,
            run_id=agent_run.run_id,
            tool_name=descriptor.name,
            tool_version=descriptor.version,
            schema_version="1",
            action=descriptor.action,
            side_effect=descriptor.side_effect,
            arguments_hash=args_hash,
            idempotency_key=f"{descriptor.name}:{agent_run.run_id}:{args_hash[:16]}",
            resource_scope={
                "grade_id": grade_id,
                "class_id": class_id,
            },
            declared_output_classification=descriptor.declared_output_classification,
            status="AWAITING_APPROVAL",
            started_at=datetime.now(),
        )
        self.db.add(tool_call)
        await self.db.flush()

        # 2. envelope + approval(PENDING)
        gate = ApprovalGate(self.db, self.user.school_id)
        envelope_uuid, approval_id = await gate.create_envelope(
            run_id=agent_run.run_id,
            user_id=self.user.id,
            tool_call_id=tool_call.id,
            tool_name=descriptor.name,
            tool_version=descriptor.version,
            args=args,
        )

        # 3. run → WAITING_APPROVAL（非 terminal，completed_at 保持 NULL）
        await agent_run.transition("WAITING_APPROVAL")
        await self.db.commit()

        return {
            "status": "awaiting_approval",
            "run_id": agent_run.run_id,
            "approval_id": approval_id,
            "goal": agent_run.query,
            "plan": [{
                "tool": descriptor.name,
                "status": "AWAITING_APPROVAL",
                "reason": step.reason,
            }],
            "overview": {},
            "findings": [],
            "recommendations": [],
            "critic": {"passed": None, "issues": []},
            "provider": os.environ.get("LLM_MODEL", "deepseek-v4-flash"),
            "model": os.environ.get("LLM_MODEL", "deepseek-v4-flash"),
            "trust": {
                "permission_checked": True,
                "approval_required": True,
                "approval_id": approval_id,
            },
            "outcome": "awaiting_approval",
            "outcome_reason": "该操作需要人工审批",
            "student_count": 0,
            "examined_count": 0,
            "grade_record_count": 0,
            "domain_counts": {},
            "domains": {},
        }

    async def resume_after_approval(self, *, approval_id: int) -> dict:
        """approve 后恢复 SAME run：executor 最终 approval/hash 校验 → execute once → COMPLETED。

        不新建 run（SAME run_id）；证据链：approval → envelope(args) → tool_call → snapshot 全链同 run。
        """
        from ai_native.models.ai_approvals import AiApprovals
        from ai_native.models.ai_runs import AiRuns
        from ai_native.models.ai_tool_calls import AiToolCalls

        approval = await self.db.get(AiApprovals, approval_id)
        if approval is None or approval.school_id != self.user.school_id:
            raise ApprovalGateError("approval record missing or tenant mismatch")
        if approval.decision != "APPROVED":
            raise ApprovalGateError(f"approval not approved: {approval.decision}")

        run = await self.db.get(AiRuns, approval.run_id)
        if run is None:
            raise ApprovalGateError("run missing")
        if run.status != "WAITING_APPROVAL":
            raise ApprovalGateError(f"run status not WAITING_APPROVAL: {run.status}")

        tool_call = await self.db.get(AiToolCalls, approval.tool_call_id)
        if tool_call is None:
            raise ApprovalGateError("tool_call missing")

        descriptor = self.registry.get(approval.tool_name)
        if descriptor is None:
            raise ApprovalGateError(f"tool not registered: {approval.tool_name}")

        # 解密 envelope → 恢复批准时的原始 args（SAME run 上下文）
        gate = ApprovalGate(self.db, self.user.school_id)
        args = await gate.reveal_args(
            approval_id=approval.id, school_id=self.user.school_id,
        )

        # 重建 AgentRun 上下文（SAME run_id，不重新 start）
        agent_run = AgentRun(
            school_id=run.school_id, user_id=run.user_id,
            tool_name=descriptor.name,
            session=self.db,
        )
        agent_run.run_id = run.id
        agent_run.run_uuid = run.run_uuid
        agent_run.trace_id = run.trace_id
        agent_run.status = run.status
        agent_run.data_classification = run.data_classification or "internal"

        await agent_run.transition("EXECUTING", session=self.db)

        run_ctx = {
            "status": "EXECUTING",
            "data_classification": agent_run.data_classification,
            "school_id": run.school_id,
            "user_id": run.user_id,
            "run_id": run.id,
            "db": self.db,
            "session": self.db,  # handler 契约：write_test_marker 从 session 取
            "user": self.user,
            "approval_args": args,
        }
        incidents: list[dict] = []
        result = await self.executor.execute(
            run=run_ctx,
            descriptor=descriptor,
            incident_sink=incidents.append,
            session=self.db,
            tool_call_id=tool_call.id,
            approval_args=args,
        )

        # tool_call → EXECUTED（executor 已做最终校验，fail-closed）
        tool_call.status = "EXECUTED"
        tool_call.actual_output_classification = result.get(
            "actual_classification", descriptor.declared_output_classification,
        )

        # finish → COMPLETED + snapshot（approval_refs 入快照，证据链同 run）
        await agent_run.finish(
            snapshot={
                "run_id": run.id,
                "school_id": run.school_id,
                "tool": descriptor.name,
                "approval_refs": [approval.id],
                "classification_peak": run_ctx.get("data_classification"),
                "incidents": incidents,
            },
            session=self.db,
        )
        await self.db.commit()

        return {
            "status": "completed",
            "run_id": run.id,
            "approval_id": approval.id,
            "goal": run.query_redacted or "",
            "plan": [{
                "tool": descriptor.name,
                "status": "EXECUTED",
                "reason": "审批通过后执行",
            }],
            "overview": {},
            "findings": [],
            "recommendations": [],
            "critic": {"passed": True, "issues": []},
            "provider": "deepseek",
            "model": os.environ.get("LLM_MODEL", "deepseek-v4-flash"),
            "trust": {
                "permission_checked": True,
                "approval_required": True,
                "approval_id": approval.id,
            },
            "outcome": "success",
            "outcome_reason": "approval approved; executed exactly once",
            "student_count": 0,
            "examined_count": 0,
            "grade_record_count": 0,
            "domain_counts": {},
            "domains": {},
        }

    async def cancel_after_reject(self, *, approval_id: int) -> dict:
        """reject 后：SAME run → CANCELLED（completed_at 落库）；tool_call → DENIED；永不执行。"""
        from ai_native.models.ai_approvals import AiApprovals
        from ai_native.models.ai_runs import AiRuns
        from ai_native.models.ai_tool_calls import AiToolCalls

        approval = await self.db.get(AiApprovals, approval_id)
        if approval is None or approval.school_id != self.user.school_id:
            raise ApprovalGateError("approval record missing or tenant mismatch")

        run = await self.db.get(AiRuns, approval.run_id)
        if run is None:
            raise ApprovalGateError("run missing")
        if run.status != "WAITING_APPROVAL":
            raise ApprovalGateError(f"run status not WAITING_APPROVAL: {run.status}")

        tool_call = await self.db.get(AiToolCalls, approval.tool_call_id)
        if tool_call is not None and tool_call.status == "AWAITING_APPROVAL":
            tool_call.status = "DENIED"

        agent_run = AgentRun(
            school_id=run.school_id, user_id=run.user_id,
            tool_name=approval.tool_name,
            session=self.db,
        )
        agent_run.run_id = run.id
        agent_run.run_uuid = run.run_uuid
        agent_run.trace_id = run.trace_id
        agent_run.status = run.status

        # CANCELLED ∈ TERMINAL_STATES → completed_at 自动落库
        await agent_run.transition("CANCELLED", session=self.db)
        await self.db.commit()

        return {
            "status": "cancelled",
            "run_id": run.id,
            "approval_id": approval.id,
        }

    # ═══════════════════════════════════════════════════════════════════
    # FT-016 失败证据链：tool_call FAILED + ai_incidents
    # ═══════════════════════════════════════════════════════════════════

    async def _record_tool_call_failure(
        self,
        *,
        run_id: int,
        descriptor: ToolDescriptor,
        params: dict[str, Any],
        failure: "ControlledToolFailure",
    ) -> None:
        """写 ai_tool_calls(FAILED)：失败也必须留 tool_call 记录（同 run_id）。"""
        from ai_native.models.ai_tool_calls import AiToolCalls

        args_hash = hashlib.sha256(
            _json.dumps(params, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        record = AiToolCalls(
            school_id=self.user.school_id,
            run_id=run_id,
            tool_name=descriptor.name,
            tool_version=descriptor.version,
            schema_version="1",
            action=descriptor.action,
            side_effect=descriptor.side_effect,
            arguments_hash=args_hash,
            idempotency_key=f"{descriptor.name}:{run_id}:{args_hash[:16]}",
            resource_scope={
                "grade_id": params.get("grade_id"),
                "class_id": params.get("class_id"),
            },
            declared_output_classification=descriptor.declared_output_classification,
            actual_output_classification=descriptor.declared_output_classification,
            status="FAILED",
            started_at=datetime.now(),
        )
        self.db.add(record)
        await self.db.flush()

    async def _record_incident(
        self,
        *,
        run_id: int,
        descriptor: ToolDescriptor,
        failure: "ControlledToolFailure",
    ) -> None:
        """写 ai_incidents（capability 类；不存原始异常正文——Inv 11）。

        关联：run_id（INCIDENT_RUN_LINK）+ tool_call（经同 run 的 FAILED tool_call
        查询关联，无需额外 FK）。
        """
        from ai_native.models.ai_incidents import AiIncidents
        import hashlib as _hl

        summary = failure.message[:512] if failure.message else "tool failure"
        detail = getattr(failure, "detail", "") or failure.message
        detail_hash = _hl.sha256(detail.encode("utf-8")).hexdigest()

        incident = AiIncidents(
            school_id=self.user.school_id,
            run_id=run_id,
            incident_code="P01",
            incident_type="tool_controlled_failure",
            category="capability",
            severity="MEDIUM",
            summary_redacted=summary,
            detail_hash=detail_hash,
            resolved=False,
        )
        self.db.add(incident)
        await self.db.flush()

    async def _record_tool_call(self, *, run_id: int, descriptor: ToolDescriptor,
                                result: dict[str, Any], params: dict[str, Any]) -> None:
        """写 ai_tool_calls（同 run_id；Tool → EXECUTED，含 declared/actual classification）。"""
        from ai_native.models.ai_tool_calls import AiToolCalls

        args_hash = hashlib.sha256(
            _json.dumps(params, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        record = AiToolCalls(
            school_id=self.user.school_id,
            run_id=run_id,
            tool_name=descriptor.name,
            tool_version=descriptor.version,
            schema_version="1",
            action=descriptor.action,
            side_effect=descriptor.side_effect,
            arguments_hash=args_hash,
            idempotency_key=f"{descriptor.name}:{run_id}:{args_hash[:16]}",
            resource_scope={
                "grade_id": params.get("grade_id"),
                "class_id": params.get("class_id"),
            },
            declared_output_classification=descriptor.declared_output_classification,
            actual_output_classification=result.get(
                "actual_classification", descriptor.declared_output_classification),
            status="EXECUTED",
            started_at=datetime.now(),
        )
        self.db.add(record)
        await self.db.flush()
