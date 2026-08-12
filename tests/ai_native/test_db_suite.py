"""
tests/ai_native/test_db_suite.py — DB 级集成测试（A/E + 负向）

自建 async engine+session，不依赖 conftest。
生产 session 模型 = AsyncSession（core/routers.py），Runtime 对齐 async。

需 DATABASE_URL_TEST=mysql+aiomysql://slice1_test:pw@host:port/db
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"),
    reason="需 DATABASE_URL_TEST 指向隔离 MySQL 库",
)

TESTS_ENABLED = bool(os.environ.get("DATABASE_URL_TEST"))


# ── async helpers ──

def _test_url() -> str:
    return os.environ["DATABASE_URL_TEST"]


def _make_engine():
    return create_async_engine(_test_url(), echo=False, pool_size=5, max_overflow=5)


def _make_session_factory(engine):
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_run(session):
    from ai_native.models.ai_runs import AiRuns

    run = AiRuns(school_id=1, user_id=1, run_uuid=str(uuid4()),
                 role_profile="teacher", input_summary="test",
                 status="EXECUTING", data_classification="internal",
                 started_at=datetime.now())
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run.id


# ═══════════════════════════════════════════════════════════════
#  A. call_seq FOR UPDATE — 双 session 竞争
# ═══════════════════════════════════════════════════════════════

class TestCallSeqForUpdate:
    async def test_two_sessions_competitive(self):
        """Session A FOR UPDATE hold → B waits → A=1 B=2，无重复。"""
        if not TESTS_ENABLED: pytest.skip()
        from ai_native.models.ai_model_calls import AiModelCalls
        from ai_native.runtime.tool_executor import TransactionScopedSeqAllocator

        engine = _make_engine()
        factory = _make_session_factory(engine)
        try:
            # seed run row
            async with factory() as s:
                rid = await _seed_run(s)

            allocator = TransactionScopedSeqAllocator()

            async def worker(label):
                async with factory() as s:
                    async with s.begin():
                        seq = await allocator.next_seq(s, school_id=1, run_id=rid)
                        s.add(AiModelCalls(school_id=1, run_id=rid, call_seq=seq,
                                           model="test", provider="deepseek",
                                           call_type="chat",
                                           data_classification_at_call="internal",
                                           cost_amount="0.01",
                                           cost_currency="CNY", started_at=datetime.now()))
                        return seq

            r = await asyncio.gather(worker("A"), worker("B"))
            assert len(set(r)) == 2, f"duplicates: {r}"
            assert sorted(r) == [1, 2]

            # verify DB: no duplicates, exactly [1,2]
            async with factory() as s:
                rows = (await s.execute(
                    select(AiModelCalls.call_seq).where(
                        AiModelCalls.school_id == 1, AiModelCalls.run_id == rid,
                    ).order_by(AiModelCalls.call_seq)
                )).scalars().all()
                assert rows == [1, 2], f"DB call_seq: {rows}"
        finally:
            await engine.dispose()

    async def test_ten_sessions_1_to_n(self):
        """10 个独立 session 同一 Run → call_seq=1..10，无重复，DB 回查。"""
        if not TESTS_ENABLED: pytest.skip()
        from ai_native.models.ai_model_calls import AiModelCalls
        from ai_native.runtime.tool_executor import TransactionScopedSeqAllocator

        engine = _make_engine()
        factory = _make_session_factory(engine)
        try:
            async with factory() as s:
                rid = await _seed_run(s)

            allocator = TransactionScopedSeqAllocator()

            async def worker():
                async with factory() as s:
                    async with s.begin():
                        seq = await allocator.next_seq(s, school_id=1, run_id=rid)
                        s.add(AiModelCalls(school_id=1, run_id=rid, call_seq=seq,
                                           model="test", provider="deepseek",
                                           call_type="chat",
                                           data_classification_at_call="internal",
                                           cost_amount="0.01",
                                           cost_currency="CNY", started_at=datetime.now()))
                        return seq

            results = await asyncio.gather(*[worker() for _ in range(10)])
            assert len(set(results)) == 10, f"duplicates: {sorted(results)}"
            assert sorted(results) == list(range(1, 11))

            # DB 回查
            async with factory() as s:
                rows = (await s.execute(
                    select(AiModelCalls.call_seq).where(
                        AiModelCalls.school_id == 1, AiModelCalls.run_id == rid,
                    ).order_by(AiModelCalls.call_seq)
                )).scalars().all()
                assert rows == list(range(1, 11)), f"DB: {rows}"
        finally:
            await engine.dispose()


# ═══════════════════════════════════════════════════════════════
#  E. AgentRun 持久化
# ═══════════════════════════════════════════════════════════════

class TestAgentRunPersistence:
    async def test_start_creates_run_and_event(self):
        if not TESTS_ENABLED: pytest.skip()
        from ai_native.models.ai_runs import AiRuns
        from ai_native.models.ai_runs_status_events import AiRunsStatusEvents
        from ai_native.runtime.agent_run import AgentRun

        engine = _make_engine()
        factory = _make_session_factory(engine)
        try:
            async with factory() as s:
                ar = AgentRun(school_id=1, user_id=1, tool_name="test_tool")
                run_id = await ar.start(session=s)
                await s.commit()

                assert ar.status == "PLANNING"

                run = await s.get(AiRuns, run_id)
                assert run is not None
                assert run.status == "PLANNING"
                assert run.input_summary == "test_tool"
                assert run.school_id == 1
                assert run.user_id == 1
                assert run.data_classification == "internal"

                cnt = await s.scalar(
                    select(func.count()).where(
                        AiRunsStatusEvents.school_id == 1,
                        AiRunsStatusEvents.run_id == run_id,
                    )
                )
                assert cnt >= 1
        finally:
            await engine.dispose()

    async def test_transition_appends_events(self):
        if not TESTS_ENABLED: pytest.skip()
        from ai_native.models.ai_runs import AiRuns
        from ai_native.models.ai_runs_status_events import AiRunsStatusEvents
        from ai_native.runtime.agent_run import AgentRun

        engine = _make_engine()
        factory = _make_session_factory(engine)
        try:
            async with factory() as s:
                ar = AgentRun(school_id=1, user_id=1, tool_name="test_tool")
                await ar.start(session=s)
                await s.commit()

                await ar.transition("POLICY_CHECK", session=s)
                await ar.transition("EXECUTING", session=s)
                await s.commit()
                assert ar.status == "EXECUTING"

                run = await s.get(AiRuns, ar.run_id)
                assert run.status == "EXECUTING"

                events = (await s.execute(
                    select(AiRunsStatusEvents.to_status).where(
                        AiRunsStatusEvents.school_id == 1,
                        AiRunsStatusEvents.run_id == ar.run_id,
                    ).order_by(AiRunsStatusEvents.id)
                )).scalars().all()
                assert events == ["PLANNING", "POLICY_CHECK", "EXECUTING"], \
                    f"event chain: {events}"
        finally:
            await engine.dispose()

    async def test_finish_writes_snapshot(self):
        if not TESTS_ENABLED: pytest.skip()
        from ai_native.models.ai_runs import AiRuns
        from ai_native.models.ai_execution_snapshots import AiExecutionSnapshots
        from ai_native.runtime.agent_run import AgentRun

        engine = _make_engine()
        factory = _make_session_factory(engine)
        try:
            async with factory() as s:
                ar = AgentRun(school_id=1, user_id=1, tool_name="test_tool")
                await ar.start(session=s)
                await s.commit()

                snapshot_data = {"result": "aggregated", "model_used": "deepseek-chat"}
                await ar.finish(snapshot=snapshot_data, session=s)
                await s.commit()
                assert ar.status == "COMPLETED"

                run = await s.get(AiRuns, ar.run_id)
                assert run.status == "COMPLETED"

                snap = (await s.execute(
                    select(AiExecutionSnapshots).where(
                        AiExecutionSnapshots.school_id == 1,
                        AiExecutionSnapshots.run_id == ar.run_id,
                    )
                )).scalar_one_or_none()
                assert snap is not None
                assert snap.scope_snapshot == snapshot_data

                # snapshot 无 raw text
                scope = snap.scope_snapshot or {}
                forbidden = {"prompt", "completion", "raw_output", "tool_args",
                             "tool_output", "psych_text"}
                for key in forbidden:
                    assert key not in scope, f"snapshot 含禁止字段: {key}"
        finally:
            await engine.dispose()


# ═══════════════════════════════════════════════════════════════
#  E4. 负向约束
# ═══════════════════════════════════════════════════════════════

class TestDBNegativeConstraints:
    async def test_cross_tenant_model_call_rejected(self):
        if not TESTS_ENABLED: pytest.skip()
        from ai_native.models.ai_model_calls import AiModelCalls

        engine = _make_engine()
        factory = _make_session_factory(engine)
        try:
            async with factory() as s:
                rid = await _seed_run(s)

            async with factory() as s:
                bad = AiModelCalls(school_id=2, run_id=rid, call_seq=1,
                                   model="deepseek", provider="deepseek",
                                   call_type="chat",
                                   data_classification_at_call="internal",
                                   cost_amount="0.01",
                                   cost_currency="CNY", started_at=datetime.now())
                s.add(bad)
                with pytest.raises(IntegrityError):
                    await s.commit()
                await s.rollback()
        finally:
            await engine.dispose()

    async def test_duplicate_call_seq_rejected(self):
        if not TESTS_ENABLED: pytest.skip()
        from ai_native.models.ai_model_calls import AiModelCalls

        engine = _make_engine()
        factory = _make_session_factory(engine)
        try:
            async with factory() as s:
                rid = await _seed_run(s)

            async with factory() as s:
                c1 = AiModelCalls(school_id=1, run_id=rid, call_seq=1,
                                  model="d", provider="deepseek",
                                  call_type="chat",
                                  data_classification_at_call="internal",
                                  cost_amount="0.01",
                                  cost_currency="CNY", started_at=datetime.now())
                s.add(c1)
                await s.commit()

            async with factory() as s:
                c2 = AiModelCalls(school_id=1, run_id=rid, call_seq=1,
                                  model="d", provider="deepseek",
                                  call_type="chat",
                                  data_classification_at_call="internal",
                                  cost_amount="0.02",
                                  cost_currency="CNY", started_at=datetime.now())
                s.add(c2)
                with pytest.raises(IntegrityError):
                    await s.commit()
                await s.rollback()
        finally:
            await engine.dispose()
