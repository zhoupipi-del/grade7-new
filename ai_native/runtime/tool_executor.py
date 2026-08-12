"""
ai_native.runtime.tool_executor — ToolExecutor + CallSeqAllocator（Inv 8 / 13 / 27）
====================================================================================

Inv 8 — UNKNOWN_COMMIT 完整状态机：
    UNKNOWN_COMMIT → Run: RECOVERING → reconciliation
    - confirmed executed     → Tool: EXECUTED, Run: RESUMING
    - confirmed not executed → Run: RESUMING, Tool: EXECUTING, handler 1 次 → EXECUTED
    - still unknown          → Run: RECOVERING, handler 0 次
    - retry_count 绝不因 UNKNOWN_COMMIT 自动 +1

Inv 13 — pre/post Taint 编排：
    pre-call:  declared > current → Run 先升级 → Provider routing 后发生
    post-call: ★ descriptor drift = actual > declared（与 Run current 无关！
               两个独立判断：Run taint 取峰值；drift 判决定 declared 是否被实际打破）
               actual <= declared → Run 不降低，且不产生 drift

Inv 27 — CallSeqAllocator：
    CallSeqAllocator           — 内存模式（单进程线程安全，测试用）
    TransactionScopedSeqAllocator — 生产多 worker：FOR UPDATE 锁 ai_runs 父行
                                    → COALESCE(MAX(call_seq),0) + 1 → 事务内原子。
                                    不同 session 同一 Run 并发经事务锁串行化。
                                    DB UNIQUE 是最后防线兜底，Runtime 主动保证。
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Callable, Dict, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_native.governance.data_classification import CLASSIFICATION_ORDER, TaintLogic


class CallSeqAllocator:
    """单进程线程安全分配（测试 / 单 worker 场景）。

    生产多 worker 场景 MUST 使用 TransactionScopedSeqAllocator
    （FOR UPDATE 跨进程串行化）；本类只保证进程内单调。
    """

    def __init__(self) -> None:
        self._counters: Dict[Tuple[int, int], int] = defaultdict(int)
        self._lock = threading.Lock()

    def next_seq(self, school_id: int, run_id: int) -> int:
        """同一 (school_id, run_id) 严格递增；不同 run 从 1 重新开始。"""
        key = (school_id, run_id)
        with self._lock:
            self._counters[key] += 1
            return self._counters[key]

    def rebase(self, school_id: int, run_id: int, db_max: int) -> None:
        """从 DB max(call_seq) 续接（多 worker 协调；幂等，只升不降）。"""
        key = (school_id, run_id)
        with self._lock:
            if self._counters[key] < db_max:
                self._counters[key] = db_max


class TransactionScopedSeqAllocator:
    """生产多 worker 的事务内 call_seq 分配（Inv 27）。

    FOR UPDATE 锁 ai_runs 父行 → 事务内读 max(call_seq)+1 → 原子分配。
    不同 session 同一 Run 并发经 MySQL InnoDB 行锁串行化。
    """

    @staticmethod
    async def next_seq(
        session: AsyncSession,
        school_id: int,
        run_id: int,
    ) -> int:
        # 动态 import ai_native models（避免 runtime 顶层依赖 9 表 ORM）
        from ai_native.models.ai_model_calls import AiModelCalls
        from ai_native.models.ai_runs import AiRuns

        # FOR UPDATE 锁父行 → 并发串行化
        parent = await session.execute(
            select(AiRuns.id).where(
                AiRuns.school_id == school_id,
                AiRuns.id == run_id,
            ).with_for_update(),
        )
        if parent.scalar_one_or_none() is None:
            raise ValueError(
                f"ai_runs({school_id},{run_id}) 不存在，不可分配 call_seq"
            )

        max_val = await session.scalar(
            select(func.coalesce(func.max(AiModelCalls.call_seq), 0)).where(
                AiModelCalls.school_id == school_id,
                AiModelCalls.run_id == run_id,
            ),
        )
        return max_val + 1

    @staticmethod
    def next_seq_sync(
        session,
        school_id: int,
        run_id: int,
    ) -> int:
        """同步版（conftest 提供 sync Session，用于测试）。"""
        from ai_native.models.ai_model_calls import AiModelCalls
        from ai_native.models.ai_runs import AiRuns
        from sqlalchemy import func, select

        parent = session.execute(
            select(AiRuns.id).where(
                AiRuns.school_id == school_id,
                AiRuns.id == run_id,
            ).with_for_update(),
        ).scalar_one_or_none()
        if parent is None:
            raise ValueError(f"ai_runs({school_id},{run_id}) 不存在")

        max_val = session.scalar(
            select(func.coalesce(func.max(AiModelCalls.call_seq), 0)).where(
                AiModelCalls.school_id == school_id,
                AiModelCalls.run_id == run_id,
            ),
        )
        return max_val + 1


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    """属性访问兼容：ToolDescriptor 对象 → .name；dict → .get(name)。"""
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default


class ToolExecutor:
    """执行编排：UNKNOWN_COMMIT 恢复（Inv 8）+ pre/post Taint（Inv 13）。"""

    def reconcile(
        self,
        *,
        run: Dict[str, Any],
        tool_call: Dict[str, Any],
        confirmation: Optional[Dict[str, Any]],
        handler: Callable,
    ) -> None:
        """
        UNKNOWN_COMMIT 恢复（Inv 8）——完整状态机。

        每次调用必须先进 RECOVERING（三个分支无一例外）。
        """
        if tool_call.get("status") != "UNKNOWN_COMMIT":
            return

        # ★ 第一步：Run 必须先进 RECOVERING（reconciliation 入口）
        run["status"] = "RECOVERING"

        if confirmation is None:
            # still unknown → RECOVERING 保持，handler 0 次
            return

        if confirmation.get("executed"):
            tool_call["status"] = "EXECUTED"
            run["status"] = "RESUMING"
        else:
            # confirmed not executed → RESUMING + EXECUTING → handler 1 次 → EXECUTED
            run["status"] = "RESUMING"
            tool_call["status"] = "EXECUTING"
            handler()
            tool_call["status"] = "EXECUTED"

    def execute(
        self,
        *,
        run: Dict[str, Any],
        descriptor: Any,
        provider: Optional[Callable] = None,
        incident_sink: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """pre/post Taint 编排（Inv 13）。

        descriptor 可为 ToolDescriptor 对象（主路径）或 dict（兼容旧测试）。
        """
        current = run.get("data_classification")
        declared = _get_attr(descriptor, "declared_output_classification")

        # ── pre-call：Run 先升级（peak），再 Provider routing ──
        if current is not None and declared is not None:
            run["data_classification"] = TaintLogic.classify(current, declared)
        if provider is not None:
            provider(run)  # provider 看到的 Run 已是升级后

        # ── 执行 handler ──
        handler = _get_attr(descriptor, "handler")
        result: Dict[str, Any] = {}
        if handler is not None:
            result = handler(run=run) or {}

        # ── post-call ──
        actual = result.get("actual_classification")
        current = run.get("data_classification")

        # Run taint：取峰值（与之前一致）
        if actual is not None and current is not None:
            run["data_classification"] = TaintLogic.classify(current, actual)

        # Descriptor drift：★ actual > declared（与 Run current 无关！）
        if actual is not None and declared is not None:
            if CLASSIFICATION_ORDER.index(actual) > CLASSIFICATION_ORDER.index(declared):
                if incident_sink is not None:
                    incident_sink(
                        {
                            "type": "tool_descriptor_drift",
                            "declared": declared,
                            "actual": actual,
                        }
                    )
        return result
