"""real_wire_slice1.py — SLICE 1 REAL-WIRE 证据脚本

一次真实请求：Grade7 授权用户 → 真实 GradeRecord → 聚合 → ProviderRouter →
真实 DeepSeekProvider → 同一 run_id 五表 provenance。

运行：python real_wire_slice1.py
要求：SSH tunnel 33071 → 隔离 MySQL；生产 .env 含 LLM_API_KEY（脚本内部读取，不打印）。
"""

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime

# ── 从生产 .env 提取 LLM 配置（不打印明文）──
def _load_llm_env():
    out = subprocess.run(
        ["ssh", "dev-mgmt", "cd /opt/wings3/current/backend && set -a && . ./.env && set +a && "
         "echo LLM_API_KEY=$LLM_API_KEY && echo LLM_API_URL=$LLM_API_URL && echo LLM_MODEL=$LLM_MODEL"],
        capture_output=True, text=True, check=True,
    ).stdout
    for line in out.strip().splitlines():
        k, _, v = line.partition("=")
        if v:
            os.environ[k] = v
    return {"key": bool(os.environ.get("LLM_API_KEY")),
            "url": os.environ.get("LLM_API_URL", "default"),
            "model": os.environ.get("LLM_MODEL", "deepseek-chat")}


def _async_main():
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    URL = os.environ["DATABASE_URL_TEST"]
    engine = create_async_engine(URL, echo=False)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def seed(s):
        from core.models import Class, Grade, School, Student, User
        from modules.grades.models import GradeExam, GradeRecord, GradeSubject

        sid = 9001
        # clean
        await s.execute(GradeRecord.__table__.delete().where(GradeRecord.school_id == sid))
        await s.execute(GradeExam.__table__.delete().where(GradeExam.school_id == sid))
        await s.execute(GradeSubject.__table__.delete().where(GradeSubject.school_id == sid))
        await s.execute(Student.__table__.delete().where(Student.school_id == sid))
        await s.execute(User.__table__.delete().where(User.school_id == sid))
        await s.execute(Class.__table__.delete().where(Class.school_id == sid))
        await s.execute(Grade.__table__.delete().where(Grade.school_id == sid))
        await s.execute(School.__table__.delete().where(School.id == sid))
        await s.flush()

        s.add(School(id=sid, name="real-wire-school"))
        g7 = Grade(id=7, school_id=sid, name="初一")
        s.add(g7)
        await s.flush()
        c1 = Class(id=1, school_id=sid, grade_id=7, name="初一1班")
        s.add(c1)
        await s.flush()

        leader = User(username=f"grade7_leader_rw", password_hash="x",
                      display_name="真实年级组长", role="grade_leader",
                      school_id=sid, grade_id=7, class_id=1)
        s.add(leader)
        await s.flush()

        students = [
            Student(name=f"真实学生{i}", student_no=f"rw{i:04d}", school_id=sid,
                    class_id=1, grade_id=7, gender="M" if i % 2 else "F")
            for i in range(1, 31)
        ]
        s.add_all(students)
        await s.flush()

        subj = GradeSubject(school_id=sid, name="数学", code="math", full_score=100.0)
        subj_cn = GradeSubject(school_id=sid, name="语文", code="chinese", full_score=120.0)
        subj_en = GradeSubject(school_id=sid, name="英语", code="english", full_score=120.0)
        s.add_all([subj, subj_cn, subj_en])
        await s.flush()

        exam = GradeExam(school_id=sid, name="2025-1 期中", grade_id=7,
                         exam_type="midterm", status="published", exam_date=datetime.now())
        s.add(exam)
        await s.flush()

        import random
        random.seed(42)
        for stu in students:
            s.add(GradeRecord(school_id=sid, exam_id=exam.id, student_id=stu.id,
                              subject_id=subj.id, score=round(random.uniform(50, 100), 1)))
            s.add(GradeRecord(school_id=sid, exam_id=exam.id, student_id=stu.id,
                              subject_id=subj_cn.id, score=round(random.uniform(50, 120), 1)))
            s.add(GradeRecord(school_id=sid, exam_id=exam.id, student_id=stu.id,
                              subject_id=subj_en.id, score=round(random.uniform(50, 120), 1)))
        await s.commit()
        return {"leader_id": leader.id, "exam_id": exam.id, "student_ids": [x.id for x in students]}

    async def main():
        llm = _load_llm_env()
        evidence = {"llm_env": {"key_present": llm["key"], "url": llm["url"], "model": llm["model"]}}
        async with factory() as s:
            seeded = await seed(s)
            from modules.ai_teacher_assistant.services import ClassGradeSummaryService
            from core.models import User

            leader = await s.get(User, seeded["leader_id"])

            # 真实请求（走完整 Runtime 链）
            svc = ClassGradeSummaryService(s, leader)
            output = await svc.generate_summary(grade_id=7)

            # 聚合证据
            grade_records = (await s.execute(
                select(func.count()).select_from(__import__("modules.grades.models", fromlist=["GradeRecord"]).GradeRecord)
                .where(__import__("modules.grades.models", fromlist=["GradeRecord"]).GradeRecord.school_id == 9001)
            )).scalar()
            evidence["input"] = {
                "user_id": leader.id, "role": leader.role,
                "school_id": 9001, "grade_id": 7, "class_id": 1,
                "exam_id": seeded["exam_id"],
            }
            evidence["aggregate"] = {
                "grade_records_total": grade_records,
                "subjects_aggregated": len(output.subjects),
                "counts": output.counts,
                "student_ids_in_output": None,  # 无 PII
            }
            evidence["output_ok"] = output is not None and output.summary != {}

            # 五表 provenance（同 run_id）
            from ai_native.models.ai_execution_snapshots import AiExecutionSnapshots
            from ai_native.models.ai_model_calls import AiModelCalls
            from ai_native.models.ai_runs import AiRuns
            from ai_native.models.ai_runs_status_events import AiRunsStatusEvents
            from ai_native.models.ai_tool_calls import AiToolCalls

            run = (await s.execute(
                select(AiRuns).where(AiRuns.school_id == 9001).order_by(AiRuns.id.desc()).limit(1)
            )).scalars().first()
            rid = run.id
            n_runs = (await s.execute(select(func.count()).where(AiRuns.school_id == 9001, AiRuns.id == rid))).scalar()
            n_tools = (await s.execute(select(func.count()).where(AiToolCalls.school_id == 9001, AiToolCalls.run_id == rid))).scalar()
            n_models = (await s.execute(select(func.count()).where(AiModelCalls.school_id == 9001, AiModelCalls.run_id == rid))).scalar()
            n_snaps = (await s.execute(select(func.count()).where(AiExecutionSnapshots.school_id == 9001, AiExecutionSnapshots.run_id == rid))).scalar()
            events = (await s.execute(
                select(AiRunsStatusEvents.to_status).where(
                    AiRunsStatusEvents.school_id == 9001, AiRunsStatusEvents.run_id == rid,
                ).order_by(AiRunsStatusEvents.id)
            )).scalars().all()
            tcall = (await s.execute(select(AiToolCalls).where(
                AiToolCalls.school_id == 9001, AiToolCalls.run_id == rid))).scalars().first()
            mcall = (await s.execute(select(AiModelCalls).where(
                AiModelCalls.school_id == 9001, AiModelCalls.run_id == rid))).scalars().first()
            snap = (await s.execute(select(AiExecutionSnapshots).where(
                AiExecutionSnapshots.school_id == 9001, AiExecutionSnapshots.run_id == rid))).scalars().first()

            evidence["provenance"] = {
                "run_id": rid,
                "ai_runs": n_runs,
                "ai_tool_calls": n_tools,
                "ai_model_calls": n_models,
                "ai_execution_snapshots": n_snaps,
                "status_events": list(events),
                "final_status": run.status,
                "tool_name": tcall.tool_name if tcall else None,
                "tool_status": tcall.status if tcall else None,
                "call_seq": mcall.call_seq if mcall else None,
                "provider": mcall.provider if mcall else None,
                "model": mcall.model if mcall else None,
                "cost_currency": mcall.cost_currency if mcall else None,
                "snapshot_raw_keys": list((snap.scope_snapshot or {}).keys()) if snap else [],
            }
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        await engine.dispose()

    asyncio.run(main())


if __name__ == "__main__":
    os.environ.setdefault("DATABASE_URL_TEST",
                          "mysql+aiomysql://slice1_test:slice1-test-pw-2026@127.0.0.1:33071/wings3_slice1_test")
    _async_main()
