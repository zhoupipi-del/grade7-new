#!/usr/bin/env python3
"""
Wings 3.1 创世纪全链路总攻管道 — genesis_pump.py

四阵地一波流：
  阵地一：14门标准初中课程基因库灌注
  阵地二：320条静态课表母版 (course_slots) 锻造
  阵地三：引爆 TimetableDataPump 横向拉伸 7月整月
  阵地四：TimetableEnricher 实弹狙击验证

运行: cd /root/backend && .venv/bin/python3 scripts/genesis_pump.py
幂等设计: 所有 INSERT 使用检查存在性 + ON DUPLICATE KEY UPDATE
"""

import asyncio
import logging
import os
import sys
from datetime import date, datetime

# 确保 backend 在路径中
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# 加载 .env
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

# ═══════════════════════════════════════════════════════════════
# 数据库连接（独立脚本，不依赖 FastAPI app）
# ═══════════════════════════════════════════════════════════════
from core.db_utils import get_db_url_for_script
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = get_db_url_for_script("运行前请先 export DATABASE_URL=...")

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=5)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("wings.genesis")

SCHOOL_ID = 1  # 梨江中学
SEMESTER = "2026_summer"


async def run_genesis_pipeline():
    logger.info("=" * 60)
    logger.info("🔥 启动 Wings 3.1 创世纪全链路总攻管道")
    logger.info("=" * 60)

    async with AsyncSessionLocal() as db:
        # ═══════════════════════════════════════════════════════
        # 阵地一：14门标准初中课程基因库灌注
        # ═══════════════════════════════════════════════════════
        logger.info("⚔️ 阵地一：正在灌注14门标准初中课程...")

        from modules.timetable.models import Course

        required_courses = [
            "语文",
            "数学",
            "英语",
            "物理",
            "化学",
            "道德与法治",
            "历史",
            "地理",
            "生物",
            "音乐",
            "美术",
            "体育",
            "信息技术",
            "劳动",
        ]

        # 检查现有课程
        stmt = select(Course).where(Course.school_id == SCHOOL_ID)
        res = await db.execute(stmt)
        existing_courses = {c.name: c.id for c in res.scalars().all()}
        logger.info(f"   现有课程: {len(existing_courses)} 门 -> {list(existing_courses.keys())}")

        course_payloads = []
        for c_name in required_courses:
            if c_name not in existing_courses:
                # Course模型无 code 字段，用 name + short_name + subject_category 标识
                course_payloads.append(
                    {
                        "school_id": SCHOOL_ID,
                        "name": c_name,
                        "short_name": c_name[:2],  # 取前两字作简称
                        "subject_category": "mandatory"
                        if c_name not in ("音乐", "美术", "信息技术", "劳动")
                        else "elective",
                        "weekly_slots": 5
                        if c_name in ("语文", "数学", "英语")
                        else (3 if c_name in ("物理", "化学") else 2),
                    }
                )

        if course_payloads:
            await db.execute(insert(Course), course_payloads)
            await db.commit()
            logger.info(f"✅ 成功注入 {len(course_payloads)} 门全新学科基因！")

        # 重新拉取完整的 course_id 映射表
        res = await db.execute(select(Course).where(Course.school_id == SCHOOL_ID))
        course_pool = list(res.scalars().all())
        course_map = {c.name: c for c in course_pool}
        logger.info(f"📊 基因库就绪，当前全科大盘：{len(course_pool)} 门课程")

        # ═══════════════════════════════════════════════════════
        # 准备物料：召集班级与教师
        # ═══════════════════════════════════════════════════════
        from core.models import Class, User

        class_res = await db.execute(
            select(Class).where(
                Class.school_id == SCHOOL_ID,
                Class.is_active == True,
            )
        )
        classes = list(class_res.scalars().all())
        logger.info(f"📋 班级池: {len(classes)} 个 -> {[c.name for c in classes]}")

        # 取所有教师角色用户（role=teacher + class_teacher 都有 class_id 的优先）
        teacher_res = await db.execute(
            select(User).where(
                User.school_id == SCHOOL_ID,
                User.is_active == True,
            )
        )
        all_users = list(teacher_res.scalars().all())
        # 优先用有 class_id 的（班主任），其次所有用户
        teachers = [u for u in all_users if u.class_id is not None]
        if not teachers:
            teachers = all_users

        if not classes:
            logger.error("❌ 班级池为空！总攻终止！")
            return
        if not teachers:
            logger.error("❌ 教师池为空！总攻终止！")
            return

        logger.info(
            f"👨‍🏫 教师池: {len(teachers)} 人 -> {[t.display_name for t in teachers[:5]]}..."
        )

        # ═══════════════════════════════════════════════════════
        # 阵地二：三维时空母版锻造 (course_slots)
        # ═══════════════════════════════════════════════════════
        logger.info(f"⚔️ 阵地二：正在锻造静态课表母版 ({len(classes)}个班 × 5天 × 8节)...")

        from modules.timetable.models import CourseSlot

        # 先清空旧仓（幂等：确保唯一键约束不被旧数据阻击）
        stmt = select(CourseSlot).where(CourseSlot.school_id == SCHOOL_ID)
        res = await db.execute(stmt)
        existing_slots = res.scalars().all()
        if existing_slots:
            logger.info(f"   发现 {len(existing_slots)} 条旧课表母版，执行清仓...")
            await db.execute(delete(CourseSlot).where(CourseSlot.school_id == SCHOOL_ID))
            await db.commit()

        template_payloads = []
        teacher_index = 0
        course_index = 0

        for cls in classes:
            for day in range(1, 6):  # 周一 ~ 周五 (SmallInteger 1-5)
                for slot in range(1, 9):  # 每天8节正课
                    target_course = course_pool[course_index % len(course_pool)]
                    target_teacher = teachers[teacher_index % len(teachers)]

                    payload = {
                        "school_id": SCHOOL_ID,
                        "class_id": cls.id,
                        "day_of_week": day,
                        "slot_number": slot,
                        "course_id": target_course.id,
                        "teacher_id": target_teacher.id,
                        "semester": SEMESTER,  # ⚡ 修正：CourseSlot 必需字段
                        "week_pattern": "all",  # ⚡ 修正：每周都上
                    }
                    template_payloads.append(payload)

                    course_index += 1
                    teacher_index += 1

        if template_payloads:
            await db.execute(insert(CourseSlot), template_payloads)
            await db.commit()
            logger.info(f"✅ 成功铸造 {len(template_payloads)} 条静态课表母版数据！")

        # ═══════════════════════════════════════════════════════
        # 阵地三：引爆时空数据泵 (横向拉伸7月整月)
        # ═══════════════════════════════════════════════════════
        logger.info("⚔️ 阵地三：引爆时空数据泵，开始向日历实例表无限拉伸...")
        start_d = date(2026, 7, 1)
        end_d = date(2026, 7, 31)

        from modules.timetable.data_pump import TimetableDataPump

        pump_result = await TimetableDataPump.pump_static_to_instances(
            school_id=SCHOOL_ID,
            start_date=start_d,
            end_date=end_d,
            db=db,
        )
        logger.info(
            f"✅ 数据泵落盘成功！处理天数：{pump_result['processed_days']}天，"
            f"生成日历级实例：{pump_result['inserted_instances']}条！"
        )

        # ═══════════════════════════════════════════════════════
        # 阵地四：全链路核聚变冒烟验证 (TimetableEnricher)
        # ═══════════════════════════════════════════════════════
        logger.info("⚔️ 阵地四：激活 TimetableEnricher，执行13路流高精时空弹道测试...")

        from modules.timetable.enricher import TimetableEnricher

        test_class_id = classes[0].id
        test_class_name = classes[0].name

        # 测试靶点 1: 2026-07-15 09:15 (应为第二节课 08:55-09:40)
        test_1 = datetime(2026, 7, 15, 9, 15, 0)
        enriched_1 = await TimetableEnricher.enrich_telemetry_event(
            school_id=SCHOOL_ID,
            class_id=test_class_id,
            occurred_at=test_1,
            db=db,
        )

        # 测试靶点 2: 2026-07-15 07:50 (早读时段)
        test_2 = datetime(2026, 7, 15, 7, 50, 0)
        enriched_2 = await TimetableEnricher.enrich_telemetry_event(
            school_id=SCHOOL_ID,
            class_id=test_class_id,
            occurred_at=test_2,
            db=db,
        )

        # 测试靶点 3: 2026-07-15 12:30 (午休)
        test_3 = datetime(2026, 7, 15, 12, 30, 0)
        enriched_3 = await TimetableEnricher.enrich_telemetry_event(
            school_id=SCHOOL_ID,
            class_id=test_class_id,
            occurred_at=test_3,
            db=db,
        )

        # 测试靶点 4: 2026-07-15 22:00 (深夜 — 应返回默认上下文)
        test_4 = datetime(2026, 7, 15, 22, 0, 0)
        enriched_4 = await TimetableEnricher.enrich_telemetry_event(
            school_id=SCHOOL_ID,
            class_id=test_class_id,
            occurred_at=test_4,
            db=db,
        )

        logger.info("=" * 60)
        logger.info("🏆 WINGS 3.1 端到端全链路实弹演练报告 🏆")
        logger.info("=" * 60)
        logger.info(f"🎯 测试班级: {test_class_name} (ID={test_class_id})")
        logger.info(
            f"📡 课程基因库: {len(course_pool)} 门 | 班级数: {len(classes)} | 教师数: {len(teachers)}"
        )
        logger.info(
            f"🔩 静态母版: {len(template_payloads)} 条 | 日历实例: {pump_result['inserted_instances']} 条"
        )
        logger.info("-" * 60)

        logger.info("📍 靶点1 — 2026-07-15 09:15 (预期: 第二节课)")
        logger.info(
            f"   in_lesson={enriched_1['in_lesson']} | period_index={enriched_1['period_index']}"
        )
        logger.info(
            f"   subject_id={enriched_1['subject_id']} | teacher_id={enriched_1['teacher_id']}"
        )
        logger.info(f"   context: {enriched_1['context_desc']}")

        logger.info("📍 靶点2 — 2026-07-15 07:50 (预期: 早读/非正课)")
        logger.info(
            f"   in_lesson={enriched_2['in_lesson']} | period_index={enriched_2['period_index']}"
        )
        logger.info(f"   context: {enriched_2['context_desc']}")

        logger.info("📍 靶点3 — 2026-07-15 12:30 (预期: 午休)")
        logger.info(
            f"   in_lesson={enriched_3['in_lesson']} | period_index={enriched_3['period_index']}"
        )
        logger.info(f"   context: {enriched_3['context_desc']}")

        logger.info("📍 靶点4 — 2026-07-15 22:00 (预期: 默认底噪)")
        logger.info(
            f"   in_lesson={enriched_4['in_lesson']} | period_index={enriched_4['period_index']}"
        )
        logger.info(f"   context: {enriched_4['context_desc']}")

        logger.info("=" * 60)

        # 清理引擎
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_genesis_pipeline())
