"""
Wings 3.1 时空连续体核心富集网关 — TimetableEnricher

负责将13路时序流的孤立时间戳，富集为高精度的（节次、学科、教师）三维坐标。

双层缓存穿透阻断:
  ① 静态时空舱 (wings:timetable:slots:{school_id}) — 物理节次区间，永不过期
  ② 动态时空网格 (wings:timetable:instances:{class_id}:{date}) — 日历课表实例，24h缓存

每层缓存未命中时回源 MySQL，利用已建立的复合索引防全表扫描。
"""

import json
import logging
from datetime import datetime, time, date
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.redis_client import get_redis
from modules.timetable.models import TimetableSlot, TimetableScheduleInstance

logger = logging.getLogger(__name__)


class TimetableEnricher:
    """
    Wings 3.1 时空连续体核心富集网关
    负责将13路时序流的孤立时间戳，富集为高精度的（节次、学科、教师）三维坐标
    """

    CACHE_EXPIRATION = 86400  # 24小时缓存

    @classmethod
    async def enrich_telemetry_event(
        cls,
        school_id: int,
        class_id: int,
        occurred_at: datetime,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        13路时序流专属升维网关
        输入：学校ID、班级ID、事件绝对时间戳
        输出：富集教务上下文 {
            in_lesson: bool,
            period_index: int | None,
            slot_id: int | None,
            subject_id: int | None,
            teacher_id: int | None,
            context_desc: str
        }
        """
        target_date = occurred_at.date()
        target_time = occurred_at.time()

        # 默认底噪上下文（非教学时段）
        default_context = {
            "in_lesson": False,
            "period_index": None,
            "slot_id": None,
            "subject_id": None,
            "teacher_id": None,
            "context_desc": "课间、午休或非教学时段"
        }

        # 1. 拦截第一层：榨取该校的【物理节次时间大盘】
        slots_map = await cls._get_school_slots_cached(school_id, db)
        if not slots_map:
            logger.debug(f"[TimetableEnricher] school_id={school_id} 无作息数据，返回默认上下文")
            return default_context

        # 2. 内存时空区间精准卡位（11条数据，线性检索或二分均极快）
        matched_slot = None
        for slot_id, info in slots_map.items():
            start = time.fromisoformat(info["start"])
            end = time.fromisoformat(info["end"])
            if start <= target_time <= end:
                matched_slot = info
                matched_slot["slot_id"] = int(slot_id)
                break

        if not matched_slot:
            return default_context

        # 如果卡位到了大课间、午休、早读等非正课时段，直接熔断返回，无需查课表实例
        if matched_slot["slot_type"] != "LESSON":
            return {
                "in_lesson": False,
                "period_index": matched_slot["period_index"],
                "slot_id": matched_slot["slot_id"],
                "subject_id": None,
                "teacher_id": None,
                "context_desc": f"时空处于：{matched_slot['name']}"
            }

        # 3. 拦截第二层：榨取该班级该日期的【日历课表实例】
        day_schedule = await cls._get_class_schedule_cached(
            school_id, class_id, target_date, db
        )

        # 4. 坐标合拢：提取当前节次的任课老师与学科
        current_lesson = day_schedule.get(str(matched_slot["slot_id"]))
        if not current_lesson:
            return {
                "in_lesson": True,
                "period_index": matched_slot["period_index"],
                "slot_id": matched_slot["slot_id"],
                "subject_id": None,
                "teacher_id": None,
                "context_desc": f"当前第{matched_slot['period_index']}节课，但未排课或遭遇空堂"
            }

        return {
            "in_lesson": True,
            "period_index": matched_slot["period_index"],
            "slot_id": matched_slot["slot_id"],
            "subject_id": current_lesson["subject_id"],
            "teacher_id": current_lesson["teacher_id"],
            "context_desc": (
                f"第{matched_slot['period_index']}节课 | "
                f"学科ID:{current_lesson['subject_id']} | "
                f"教师ID:{current_lesson['teacher_id']}"
            )
        }

    @classmethod
    async def _get_school_slots_cached(
        cls, school_id: int, db: AsyncSession
    ) -> Dict[str, Any]:
        """第一层缓存看守：学校物理作息时间 (永不过期)"""
        redis = get_redis()
        cache_key = f"wings:timetable:slots:{school_id}"

        if redis is not None:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)

        # 缓存未命中（或 Redis 不可用），回源 MySQL
        stmt = select(TimetableSlot).where(
            TimetableSlot.school_id == school_id,
            TimetableSlot.is_active == True
        )
        result = await db.execute(stmt)
        slots = result.scalars().all()

        slots_map: Dict[str, Any] = {}
        for s in slots:
            slots_map[str(s.id)] = {
                "period_index": s.period_index,
                "slot_type": s.slot_type,
                "name": s.name,
                "start": s.start_time.isoformat(),
                "end": s.end_time.isoformat()
            }

        if redis is not None and slots_map:
            # 静态作息不设过期时间，除非教务处改作息
            await redis.set(cache_key, json.dumps(slots_map))
            logger.info(
                f"[TimetableEnricher] 静态作息缓存已注入: "
                f"school_id={school_id}, slots={len(slots_map)}"
            )

        return slots_map

    @classmethod
    async def _get_class_schedule_cached(
        cls, school_id: int, class_id: int, target_date: date, db: AsyncSession
    ) -> Dict[str, Any]:
        """第二层缓存看守：班级日历级实例课表 (24h 过期)"""
        redis = get_redis()
        date_str = target_date.isoformat()
        cache_key = f"wings:timetable:instances:{class_id}:{date_str}"

        if redis is not None:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)

        # 缓存击穿，回源 MySQL（利用极速复合索引 idx_timetable_query_class）
        stmt = select(TimetableScheduleInstance).where(
            TimetableScheduleInstance.school_id == school_id,
            TimetableScheduleInstance.class_id == class_id,
            TimetableScheduleInstance.date == target_date
        )
        result = await db.execute(stmt)
        instances = result.scalars().all()

        schedule_map: Dict[str, Any] = {}
        for inst in instances:
            schedule_map[str(inst.slot_id)] = {
                "subject_id": inst.subject_id,
                "teacher_id": inst.teacher_id
            }

        if redis is not None:
            # 即使当天没排课，也缓存一个空 dict，严防黑客利用不存在的日期
            # 恶意轰击穿透到 MySQL
            await redis.set(
                cache_key,
                json.dumps(schedule_map),
                ex=cls.CACHE_EXPIRATION
            )
            logger.debug(
                f"[TimetableEnricher] 课表实例缓存已注入: "
                f"class_id={class_id}, date={date_str}, "
                f"lessons={len(schedule_map)}"
            )

        return schedule_map
