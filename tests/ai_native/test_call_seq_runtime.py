"""
tests/ai_native/test_call_seq_runtime.py — Inv 27: call_seq Runtime 单调分配

RED GATE 测试（Phase E Slice 1）：组件 `ai_native.runtime.tool_executor`
（CallSeqAllocator）尚未实现，全部测试预期 FAIL（需求未实现导致的正确失败）。

契约（未来实现必须满足）：
    - 同一 (school_id, run_id) 内：Runtime 主动分配严格递增序号 1, 2, 3, …
    - 不同 Run：各自从 1 重新开始
    - 并发分配不得产生重复序号（DB UNIQUE 是最后防线；
      Runtime 必须主动分配严格递增序号，不能只依赖 DB）

    实现形态：
        CallSeqAllocator.next_seq(school_id, run_id) -> int
        （线程安全；同 key 单调递增，不同 key 独立从 1 开始）
"""

from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor

import pytest


def _require_allocator():
    try:
        return importlib.import_module("ai_native.runtime.tool_executor")
    except ModuleNotFoundError as exc:  # pragma: no cover - RED 分支
        pytest.fail(
            f"RED: ai_native/runtime/tool_executor.py 尚未实现（Slice 1 需求未落地）: {exc}"
        )


class TestInv27CallSeqRuntime:
    def test_sequence_increments_within_same_run(self):
        mod = _require_allocator()
        alloc = mod.CallSeqAllocator()
        run_key = (1, 42)  # (school_id, run_id)
        seqs = [alloc.next_seq(*run_key) for _ in range(3)]
        assert seqs == [1, 2, 3]

    def test_new_run_restarts_from_one(self):
        mod = _require_allocator()
        alloc = mod.CallSeqAllocator()
        assert alloc.next_seq(1, 42) == 1
        assert alloc.next_seq(1, 42) == 2
        # Run #B（另一个 run_id）→ 可以重新从 1 开始
        assert alloc.next_seq(1, 43) == 1

    def test_concurrent_allocations_no_duplicate(self):
        mod = _require_allocator()
        alloc = mod.CallSeqAllocator()
        run_key = (1, 42)
        with ThreadPoolExecutor(max_workers=8) as pool:
            seqs = list(
                pool.map(lambda _: alloc.next_seq(*run_key), range(20))
            )
        # 同一 (school_id, run_id) 并发分配：无重复、覆盖 1..20
        assert len(seqs) == len(set(seqs)) == 20
        assert min(seqs) == 1
        assert max(seqs) == 20

    def test_strictly_monotonic_without_db(self):
        mod = _require_allocator()
        alloc = mod.CallSeqAllocator()
        prev = 0
        for _ in range(10):
            cur = alloc.next_seq(1, 42)
            assert cur > prev  # 严格递增
            prev = cur
