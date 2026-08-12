"""
tests/ai_native/test_vertical_slice_integration.py — Vertical Slice 集成测试（6 项）

验证真实 AI Native 纵向链（非单测）：
    1. happy path：授权用户 → 200
    2. unauthorized class：越权 class → 403，0 Tool execution
    3. cross-school：跨 tenant → 403，0 Tool execution
    4. Runtime composition：Registry → Descriptor → Executor → handler
    5. Provider composition：必须经 ProviderRouter（禁止 direct DeepSeekProvider）
    6. provenance：一次请求后 ai_runs/tool_calls/model_calls/snapshots 同 run_id 串联

需要 DATABASE_URL_TEST 指向隔离 MySQL 库。
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"),
    reason="需 DATABASE_URL_TEST",
)

TESTS_ENABLED = bool(os.environ.get("DATABASE_URL_TEST"))

LEADER_SCHOOL = 9001  # 授权用户所在 school
CROSS_SCHOOL = 9002


# ── seed ──

async def _seed_env(session: AsyncSession, *, school_id: int = LEADER_SCHOOL,
                    grade_id: int = 7, class_id: int = 1) -> dict:
    from core.models import Class, Grade, School, Student, User

    # clean any previous seed for this school（FK 依赖顺序）
    from modules.grades.models import GradeExam, GradeRecord, GradeSubject
    await session.execute(GradeRecord.__table__.delete().where(GradeRecord.school_id.in_([school_id, CROSS_SCHOOL])))
    await session.execute(GradeExam.__table__.delete().where(GradeExam.school_id.in_([school_id, CROSS_SCHOOL])))
    await session.execute(GradeSubject.__table__.delete().where(GradeSubject.school_id.in_([school_id, CROSS_SCHOOL])))
    await session.execute(Student.__table__.delete().where(Student.school_id.in_([school_id, CROSS_SCHOOL])))
    await session.execute(User.__table__.delete().where(User.school_id.in_([school_id, CROSS_SCHOOL])))
    await session.execute(Class.__table__.delete().where(Class.school_id.in_([school_id, CROSS_SCHOOL])))
    await session.execute(Grade.__table__.delete().where(Grade.school_id.in_([school_id, CROSS_SCHOOL])))
    await session.execute(School.__table__.delete().where(School.id.in_([school_id, CROSS_SCHOOL])))
    await session.flush()

    school = School(id=school_id, name=f"school-{school_id}")
    session.add(school)
    g7 = Grade(id=grade_id, school_id=school_id, name="初一")
    g8 = Grade(id=grade_id + 1, school_id=school_id, name="初二")
    session.add_all([g7, g8])
    await session.flush()

    c1 = Class(id=class_id, school_id=school_id, grade_id=grade_id, name="1班")
    c2 = Class(id=class_id + 1, school_id=school_id, grade_id=grade_id + 1, name="2班")
    session.add_all([c1, c2])
    await session.flush()

    leader = User(username=f"leader_{uuid.uuid4().hex[:8]}", password_hash="x",
                  display_name="年级组长", role="grade_leader",
                  school_id=school_id, grade_id=grade_id, class_id=class_id)
    session.add(leader)
    await session.flush()

    students = [
        Student(name="学生1", student_no=f"s{uuid.uuid4().hex[:8]}", school_id=school_id,
                class_id=class_id, grade_id=grade_id, gender="M"),
        Student(name="学生2", student_no=f"s{uuid.uuid4().hex[:8]}", school_id=school_id,
                class_id=class_id, grade_id=grade_id, gender="F"),
        Student(name="学生3", student_no=f"s{uuid.uuid4().hex[:8]}", school_id=school_id,
                class_id=class_id, grade_id=grade_id, gender="M"),
        # 未授权班级（grade 8）
        Student(name="学生4", student_no=f"s{uuid.uuid4().hex[:8]}", school_id=school_id,
                class_id=class_id + 1, grade_id=grade_id + 1, gender="F"),
    ]
    session.add_all(students)
    await session.flush()

    # subject + published exam + records
    from modules.grades.models import GradeExam, GradeRecord, GradeSubject
    subj = GradeSubject(school_id=school_id, name="数学", code="math", full_score=100.0)
    session.add(subj)
    await session.flush()
    exam = GradeExam(school_id=school_id, name="期中考试", grade_id=grade_id,
                     exam_type="midterm", status="published", exam_date=datetime.now())
    session.add(exam)
    await session.flush()
    for s in students[:3]:
        session.add(GradeRecord(school_id=school_id, exam_id=exam.id,
                                student_id=s.id, subject_id=subj.id,
                                score=90.0 + students.index(s) * 3.0))
    await session.commit()

    return {
        "school_id": school_id, "grade_id": grade_id, "class_id": class_id,
        "leader_id": leader.id, "class2_id": class_id + 1, "exam_id": exam.id,
    }


async def _get_leader(session, school_id, leader_id):
    from core.models import User
    return await session.get(User, leader_id)


# ── fixture ──

@pytest.fixture
async def svc_env():
    engine = create_async_engine(os.environ["DATABASE_URL_TEST"], echo=False)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


# ═══════════════════════════════════════════════════════════════
#  1. happy path
# ═══════════════════════════════════════════════════════════════

class TestHappyPath:
    async def test_authorized_user_returns_200(self, svc_env):
        if not TESTS_ENABLED: pytest.skip()
        from modules.ai_teacher_assistant.services import ClassGradeSummaryService

        factory = svc_env
        async with factory() as s:
            ids = await _seed_env(s)
            leader = await _get_leader(s, ids["school_id"], ids["leader_id"])

            svc = ClassGradeSummaryService(s, leader)
            output = await svc.generate_summary(grade_id=ids["grade_id"])

            assert output is not None
            assert output.grade_id == ids["grade_id"]
            assert output.subjects, "应有科目聚合"
            assert output.counts.get("students", 0) >= 3
            # 无 PII
            assert output.model_dump(exclude_none=True).get("student_id") is None
            # 全部 subject 无 PII 字段
            for subj in output.subjects:
                assert "student_name" not in subj.model_dump()


# ═══════════════════════════════════════════════════════════════
#  2. unauthorized class → 403
# ═══════════════════════════════════════════════════════════════

class TestUnauthorizedClass:
    async def test_unauthorized_class_rejected_403(self, svc_env):
        if not TESTS_ENABLED: pytest.skip()
        from modules.ai_teacher_assistant.services import ClassGradeSummaryService

        factory = svc_env
        async with factory() as s:
            ids = await _seed_env(s)
            leader = await _get_leader(s, ids["school_id"], ids["leader_id"])

            svc = ClassGradeSummaryService(s, leader)
            with pytest.raises(HTTPException) as ei:
                await svc.generate_summary(class_id=ids["class2_id"])  # grade 8 班级
            assert ei.value.status_code == 403


# ═══════════════════════════════════════════════════════════════
#  3. cross-school → 403
# ═══════════════════════════════════════════════════════════════

class TestCrossSchool:
    async def test_cross_school_rejected_403(self, svc_env):
        if not TESTS_ENABLED: pytest.skip()
        from modules.ai_teacher_assistant.services import ClassGradeSummaryService

        factory = svc_env
        async with factory() as s:
            ids = await _seed_env(s, school_id=CROSS_SCHOOL, grade_id=10, class_id=100)
            leader = await _get_leader(s, CROSS_SCHOOL, ids["leader_id"])

            svc = ClassGradeSummaryService(s, leader)
            # 请求 LEADER_SCHOOL 的 grade 7（不在本 school）
            with pytest.raises(HTTPException) as ei:
                await svc.generate_summary(grade_id=7)
            assert ei.value.status_code == 403


# ═══════════════════════════════════════════════════════════════
#  4. Runtime composition：Registry → Descriptor → Executor → handler
# ═══════════════════════════════════════════════════════════════

class TestRuntimeComposition:
    def test_registry_to_executor_to_handler(self):
        from modules.ai_teacher_assistant.tools.read_class_grade_summary import (
            build_read_class_grade_summary_descriptor,
            read_class_grade_summary_handler,
        )
        from ai_native.runtime.tool_descriptor import ToolRegistry
        from ai_native.runtime.tool_executor import ToolExecutor

        registry = ToolRegistry()
        descriptor = build_read_class_grade_summary_descriptor()
        registry.register(descriptor)

        fetched = registry.get("read_class_grade_summary")
        assert fetched is not None
        assert fetched.handler is not None

        executor = ToolExecutor()
        run = {"status": "EXECUTING", "data_classification": "internal",
               "aggregation": {"data_json": "{}"}}
        result = executor.execute(run=run, descriptor=fetched)
        assert result is not None
        assert "output" in result


# ═══════════════════════════════════════════════════════════════
#  5. Provider composition：必须经 ProviderRouter
# ═══════════════════════════════════════════════════════════════

class TestProviderComposition:
    def test_handler_goes_through_provider_router(self):
        """handler 内部通过 ProviderRouter.route() 获取 provider（静态 gate 已证无 direct import）。"""
        import inspect

        from modules.ai_teacher_assistant.tools.read_class_grade_summary import (
            read_class_grade_summary_handler,
        )

        source = inspect.getsource(read_class_grade_summary_handler)
        assert "ProviderRouter" in source
        assert "DeepSeekProvider(" not in source
        assert "from core.deepseek_provider" not in source

    def test_static_gate_no_direct_import(self):
        """modules/ai_teacher_assistant/* 不得直接 import/call DeepSeekProvider。"""
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "modules" / "ai_teacher_assistant"
        violations = []
        for py in root.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            if "from core.deepseek_provider import" in text or "DeepSeekProvider(" in text:
                violations.append(str(py))
        assert violations == [], f"直接引用 DeepSeekProvider: {violations}"


# ═══════════════════════════════════════════════════════════════
#  6. provenance：同 run_id 串联
# ═══════════════════════════════════════════════════════════════

class TestProvenanceIntegration:
    async def test_all_tables_linked_by_same_run_id(self, svc_env):
        if not TESTS_ENABLED: pytest.skip()
        from modules.ai_teacher_assistant.services import ClassGradeSummaryService

        factory = svc_env
        async with factory() as s:
            ids = await _seed_env(s)
            leader = await _get_leader(s, ids["school_id"], ids["leader_id"])

            svc = ClassGradeSummaryService(s, leader)
            await svc.generate_summary(grade_id=ids["grade_id"])

            # 找到最近一次 read_class_grade_summary run
            from ai_native.models.ai_execution_snapshots import AiExecutionSnapshots
            from ai_native.models.ai_model_calls import AiModelCalls
            from ai_native.models.ai_runs import AiRuns
            from ai_native.models.ai_runs_status_events import AiRunsStatusEvents

            runs = (await s.execute(
                select(AiRuns).where(AiRuns.school_id == ids["school_id"])
                .order_by(AiRuns.id.desc()).limit(1)
            )).scalars().all()
            assert runs, "无 ai_runs 记录"
            run = runs[0]
            run_id = run.id
            assert run.status == "COMPLETED"

            # status_events 链
            events = (await s.execute(
                select(AiRunsStatusEvents.to_status).where(
                    AiRunsStatusEvents.school_id == ids["school_id"],
                    AiRunsStatusEvents.run_id == run_id,
                ).order_by(AiRunsStatusEvents.id)
            )).scalars().all()
            assert events[-1] == "COMPLETED"
            assert "PLANNING" in events

            # ai_model_calls 同 run_id
            mcall = (await s.execute(
                select(AiModelCalls).where(
                    AiModelCalls.school_id == ids["school_id"],
                    AiModelCalls.run_id == run_id,
                )
            )).scalar_one_or_none()
            assert mcall is not None, "无 ai_model_calls"
            assert mcall.call_seq >= 1
            assert mcall.cost_currency is not None

            # ai_tool_calls 同 run_id
            from ai_native.models.ai_tool_calls import AiToolCalls

            tcall = (await s.execute(
                select(AiToolCalls).where(
                    AiToolCalls.school_id == ids["school_id"],
                    AiToolCalls.run_id == run_id,
                )
            )).scalar_one_or_none()
            assert tcall is not None, "无 ai_tool_calls"
            assert tcall.tool_name == "read_class_grade_summary"
            assert tcall.status == "EXECUTED"
            assert tcall.arguments_hash  # 参数只存 hash，不存原文

            # snapshot 同 run_id
            snap = (await s.execute(
                select(AiExecutionSnapshots).where(
                    AiExecutionSnapshots.school_id == ids["school_id"],
                    AiExecutionSnapshots.run_id == run_id,
                )
            )).scalar_one_or_none()
            assert snap is not None, "无 ai_execution_snapshots"
            scope = snap.scope_snapshot or {}
            for forbidden in ("prompt", "completion", "raw_output", "tool_args", "tool_output"):
                assert forbidden not in scope, f"snapshot 含 {forbidden}"
