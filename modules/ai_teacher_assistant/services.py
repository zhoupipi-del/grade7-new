"""
modules/ai_teacher_assistant/services.py — AI Native 纵向闭环编排（正式 Runtime 链）

冻结链路（Slice 1 VERTICAL SLICE）：
    POST /class-grade-summary
    → ClassGradeSummaryService
    → AgentRun.start()                         # ai_runs + PLANNING
    → ResourceScopeResolver                    # requested ∩ authorized（core/access 为授权事实来源）
    → PermissionChecker                        # 越权 → 403
    → PolicyAdapter                            # approval 判定（Slice 1: none）
    → ToolRegistry.get("read_class_grade_summary")
    → ToolExecutor.execute                     # pre/post taint + descriptor.handler
    → read_class_grade_summary_handler         # ProviderRouter → DeepSeekProvider（禁止直接 import）
    → 安全聚合（_Aggregator，async 数据层）
    → ai_model_calls（同 run_id，call_seq allocator）
    → Output validation（ReadClassGradeSummaryOutput）
    → AgentRun.finish() + ExecutionSnapshot    # COMPLETED + snapshot
    → response

★ services.py 禁止直接 import/call DeepSeekProvider —— LLM 只经 ProviderRouter。
"""

from __future__ import annotations

import inspect
import json
import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.access import student_id_scope
from core.models import User

from ai_native.governance.approval_policy import ApprovalPolicy
from ai_native.governance.resource_scope import ResourceScope, resolve_scope
from ai_native.runtime.agent_run import AgentRun
from ai_native.runtime.permission import PermissionChecker
from ai_native.runtime.provider_router import ProviderRouter
from ai_native.runtime.tool_descriptor import ToolRegistry
from ai_native.runtime.tool_executor import ToolExecutor, TransactionScopedSeqAllocator

from .tools.read_class_grade_summary import (
    ReadClassGradeSummaryOutput,
    SubjectSummary,
    _Aggregator,
    build_read_class_grade_summary_descriptor,
    read_class_grade_summary_handler,
)

logger = logging.getLogger(__name__)


class _SimplePolicyAdapter:
    """PolicyAdapter 最小实现（Slice 1：read-only Tool 无审批流）。"""

    def decide(self, *, policy: ApprovalPolicy, user=None, agent=None,
               tool=None, resource_scope=None, action: str = "") -> bool:
        if policy == ApprovalPolicy.NONE:
            return True
        if policy == ApprovalPolicy.ALWAYS:
            return True
        # POLICY_DECIDES 预留：Slice 1 第一刀无审批流
        return True


class ClassGradeSummaryService:
    """班级成绩摘要 —— 完整 AI Native 纵向闭环。"""

    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user
        self.school_id = user.school_id
        self._registry = ToolRegistry()
        self._registry.register(build_read_class_grade_summary_descriptor())

    async def generate_summary(
        self,
        *,
        class_id: Optional[int] = None,
        grade_id: Optional[int] = None,
        exam_id: Optional[int] = None,
    ) -> ReadClassGradeSummaryOutput:
        # ── 1. AgentRun 生命周期 ──
        agent_run = AgentRun(school_id=self.school_id, user_id=self.user.id,
                             tool_name="read_class_grade_summary")
        run_id = await agent_run.start(session=self.db)
        await agent_run.transition("POLICY_CHECK", session=self.db)

        try:
            # ── 2. ResourceScopeResolver：requested ∩ authorized ──
            # core/access.py 是授权事实来源；通过 Resolver 消费（不直接绕过）
            authorized_ids = await student_id_scope(self.db, self.user)
            authorized = ResourceScope(
                school_id=self.school_id,
                student_ids=None if authorized_ids is None else set(authorized_ids),
            )
            requested = ResourceScope(
                school_id=self.school_id,
                grade_ids={grade_id} if grade_id else None,
                class_ids={class_id} if class_id else None,
            )
            effective = resolve_scope(requested, authorized)

            # ── 3. Permission（越权 → 403，0 Tool execution）──
            descriptor = self._registry.get("read_class_grade_summary")
            checker = PermissionChecker()
            if not checker.check(
                user=self.user, agent=None, tool=descriptor,
                requested=requested, authorized=authorized, action="read",
            ):
                await agent_run.transition("FAILED", session=self.db)
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                    detail="无权访问该班级/年级成绩数据")

            # ── 4. PolicyAdapter（Slice 1: none）──
            adapter = _SimplePolicyAdapter()
            if not adapter.decide(
                policy=ApprovalPolicy.NONE, user=self.user, tool=descriptor,
                resource_scope=effective, action="read",
            ):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                    detail="审批未通过")

            await agent_run.transition("EXECUTING", session=self.db)

            # ── 5. scope coverage 检查：请求的 class/grade 必须有授权学生 ──
            # 越权 class / 跨校 class → 0 授权学生 → 403（0 Tool execution）
            coverage = await self._count_authorized(
                class_id=class_id, grade_id=grade_id,
                student_ids=effective.student_ids,
            )
            if coverage == 0:
                await agent_run.transition("FAILED", session=self.db)
                await self.db.commit()
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                    detail="无权访问该班级/年级成绩数据")

            # ── 6. 安全聚合（Tool 的 async 数据层；用 effective scope 过滤）──
            aggregator = _Aggregator(self.db, self.school_id, self.user)
            agg = await aggregator.aggregate(
                class_id=class_id, grade_id=grade_id, exam_id=exam_id,
                effective_student_ids=effective.student_ids,
            )

            # ── 6. ToolExecutor.execute → descriptor.handler → ProviderRouter → DeepSeek ──
            executor = ToolExecutor()
            incidents: list[dict] = []
            run_ctx = {
                "status": "EXECUTING",
                "data_classification": "internal",
                "school_id": self.school_id,
                "user_id": self.user.id,
                "run_id": run_id,
                "aggregation": agg,
                "exam_id": exam_id,
            }
            result = executor.execute(
                run=run_ctx,
                descriptor=descriptor,
                incident_sink=incidents.append,
            )
            await self.db.flush()

            # ── 7. ai_tool_calls + ai_model_calls（同 run_id）──
            await self._record_tool_call(
                run_id=run_id,
                result=result,
                params={"class_id": class_id, "grade_id": grade_id, "exam_id": exam_id},
            )
            model_call = result.get("model_call") or {}
            if model_call:
                await self._record_model_call(run_id=run_id, model_call=model_call)
                await self.db.flush()

            # ── 8. 组装 Output（无 PII 校验）──
            output_data = result.get("output") or {}
            output = ReadClassGradeSummaryOutput(
                class_id=agg.get("class_id"),
                grade_id=agg.get("grade_id"),
                exam=agg.get("exam"),
                subjects=[SubjectSummary(**s) for s in agg.get("subjects", [])],
                counts=agg.get("counts", {}),
                summary=output_data.get("summary", {}),
            )

            # ── 9. AgentRun.finish + ExecutionSnapshot ──
            await agent_run.finish(
                snapshot={
                    "run_id": run_id,
                    "school_id": self.school_id,
                    "tool": "read_class_grade_summary",
                    "scope_snapshot": {
                        "class_id": class_id, "grade_id": grade_id,
                        "exam_id": exam_id,
                    },
                    "classification_peak": run_ctx.get("data_classification"),
                    "model_call_refs": [model_call.get("model", "")] if model_call else [],
                },
                session=self.db,
            )
            await self.db.commit()
            return output

        except HTTPException:
            await self.db.rollback()
            raise
        except Exception as exc:
            logger.exception("class-grade-summary 失败: %s", exc)
            try:
                await agent_run.transition("FAILED", session=self.db)
                await self.db.commit()
            except Exception:  # noqa: BLE001
                await self.db.rollback()
            raise

    async def _count_authorized(self, *, class_id, grade_id, student_ids) -> int:
        """请求 class/grade 内授权学生数（越权/跨校 → 0）。"""
        from core.models import Student
        from sqlalchemy import func, select

        q = select(func.count(Student.id)).where(
            Student.school_id == self.school_id,
            Student.is_active == True,  # noqa: E712
        )
        if class_id is not None:
            q = q.where(Student.class_id == class_id)
        if grade_id is not None:
            q = q.where(Student.grade_id == grade_id)
        if student_ids is not None:
            q = q.where(Student.id.in_(student_ids))
        return await self.db.scalar(q) or 0

    async def _record_tool_call(self, *, run_id: int, result: Dict[str, Any],
                                params: Dict[str, Any]) -> None:
        """写 ai_tool_calls（同 run_id；read_class_grade_summary → EXECUTED）。"""
        import hashlib
        import json as _json
        from datetime import datetime

        from ai_native.models.ai_tool_calls import AiToolCalls

        args_hash = hashlib.sha256(
            _json.dumps(params, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        record = AiToolCalls(
            school_id=self.school_id,
            run_id=run_id,
            tool_name="read_class_grade_summary",
            tool_version="0.1.0",
            schema_version="1",
            action="read",
            side_effect="none",
            arguments_hash=args_hash,
            idempotency_key=f"cgs:{run_id}:{args_hash[:16]}",
            resource_scope={"class_id": params.get("class_id"),
                            "grade_id": params.get("grade_id")},
            declared_output_classification="student_pii",
            actual_output_classification=result.get("actual_classification", "student_pii"),
            status="EXECUTED",
            started_at=datetime.now(),
        )
        self.db.add(record)

    async def _record_model_call(self, *, run_id: int, model_call: Dict[str, Any]) -> None:
        """写 ai_model_calls（同 run_id；call_seq 由 TransactionScopedSeqAllocator 分配）。"""
        from datetime import datetime

        from ai_native.models.ai_model_calls import AiModelCalls

        seq = await TransactionScopedSeqAllocator.next_seq(
            self.db, self.school_id, run_id,
        )
        usage = model_call.get("usage") or {}
        record = AiModelCalls(
            school_id=self.school_id,
            run_id=run_id,
            call_seq=seq,
            provider=model_call.get("provider", "deepseek"),
            model=model_call.get("model", "deepseek-chat"),
            call_type="chat",
            data_classification_at_call="internal",
            cost_amount=str(model_call.get("cost_amount", "0.001")),
            cost_currency=model_call.get("cost_currency", "CNY"),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            started_at=datetime.now(),
        )
        self.db.add(record)
