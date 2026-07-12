#!/usr/bin/env python3
"""Wings 3.1 CEP时空升维冒烟脚本"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from datetime import datetime

DATABASE_URL = os.getenv('DATABASE_URL', 'mysql+aiomysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/wings3')
engine = create_async_engine(DATABASE_URL, echo=False, pool_size=3)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def smoke():
    from core.models import Student
    from sqlalchemy import select

    async with SessionLocal() as db:
        result = await db.execute(
            select(Student.id, Student.class_id).where(Student.school_id == 1).limit(1)
        )
        row = result.first()
        student_id, class_id = row

        print(f"[SMOKE] Student: id={student_id}, class_id={class_id}")

        # Test 1: Enricher — 09:15 = 第二节课
        from modules.timetable.enricher import TimetableEnricher
        t1 = datetime(2026, 7, 15, 9, 15, 0)
        ctx1 = await TimetableEnricher.enrich_telemetry_event(1, class_id, t1, db)
        print(f"[TEST1] 09:15 -> in_lesson={ctx1['in_lesson']} period={ctx1['period_index']} subject={ctx1['subject_id']} teacher={ctx1['teacher_id']}")
        print(f"        context: {ctx1['context_desc']}")

        # Test 2: Weight factor
        from modules.growth.cep_interceptor import _compute_timetable_weight
        w1 = _compute_timetable_weight(ctx1)
        assert w1 == 1.5, f"Expected 1.5, got {w1}"
        print(f"[TEST2] Weight factor: x{w1} PASSED")

        # Test 3: Prompt section
        from modules.growth.cep_interceptor import _build_timetable_prompt_section
        section = _build_timetable_prompt_section(ctx1, w1)
        assert "正在上课" in section, "Missing 正在上课 in prompt"
        assert "加权系数" in section, "Missing 加权系数 in prompt"
        print(f"[TEST3] Prompt section ({len(section)} chars): PASSED")
        print(section)

        # Test 4: Off-class (lunch 12:30)
        t2 = datetime(2026, 7, 15, 12, 30, 0)
        ctx2 = await TimetableEnricher.enrich_telemetry_event(1, class_id, t2, db)
        w2 = _compute_timetable_weight(ctx2)
        assert w2 == 1.0, f"Expected 1.0, got {w2}"
        print(f"[TEST4] 12:30 -> in_lesson={ctx2['in_lesson']} weight=x{w2} ctx={ctx2['context_desc']} PASSED")

        # Test 5: Out of range (22:00)
        t3 = datetime(2026, 7, 15, 22, 0, 0)
        ctx3 = await TimetableEnricher.enrich_telemetry_event(1, class_id, t3, db)
        w3 = _compute_timetable_weight(ctx3)
        assert w3 == 1.0, f"Expected 1.0, got {w3}"
        print(f"[TEST5] 22:00 -> in_lesson={ctx3['in_lesson']} weight=x{w3} PASSED")

    await engine.dispose()
    print("\n[RESULT] ALL 5 TESTS PASSED!")


if __name__ == '__main__':
    asyncio.run(smoke())
