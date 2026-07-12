"""
Wings 3.1 时空拉伸泵 — TimetableDataPump

将静态课表母版 (course_slots) 横向拉伸为日历级课表实例 (timetable_schedule_instances)。
打破 week_pattern 星期枷锁，全面映射到真实 date 坐标。

核心算法:
  1. 读取所有 CourseSlot 模板 (class_id × day_of_week × slot_number)
  2. 建立 slot_number → TimetableSlot.id 映射 (仅 LESSON 类型)
  3. 按日期范围逐日扫描，匹配 weekday 后批量注入实例
  4. INSERT ... ON DUPLICATE KEY UPDATE 保证幂等 (uix_class_date_slot)
"""

import logging
from datetime import date, timedelta
from typing import Dict, List, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from modules.timetable.models import CourseSlot, TimetableSlot, TimetableScheduleInstance

logger = logging.getLogger(__name__)


class TimetableDataPump:
    """
    静态课表母版 → 日历级实例 横向拉伸泵

    用法:
        result = await TimetableDataPump.pump_static_to_instances(
            school_id=1,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
            db=db
        )
    """

    @staticmethod
    async def pump_static_to_instances(
        school_id: int,
        start_date: date,
        end_date: date,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        主泵入口：将指定日期范围内的静态课表拉伸为日历级实例。

        Args:
            school_id: 学校 ID
            start_date: 起始日期（含）
            end_date: 结束日期（含）
            db: 异步数据库会话

        Returns:
            {"processed_days": int, "inserted_instances": int, "skipped_weekends": int}
        """
        # ── Step 1: 建立 slot_number → TimetableSlot.id 映射 ──
        stmt = select(TimetableSlot).where(
            TimetableSlot.school_id == school_id,
            TimetableSlot.slot_type == "LESSON",
            TimetableSlot.is_active == True,
        )
        result = await db.execute(stmt)
        lesson_slots = result.scalars().all()

        # period_index (1-8) → slot_id
        period_to_slot_id: Dict[int, int] = {
            s.period_index: s.id for s in lesson_slots
        }

        if not period_to_slot_id:
            logger.warning(
                f"[DataPump] school_id={school_id} 无 LESSON 类型节次定义，"
                f"请先灌注 timetable_slots 种子数据"
            )
            return {"processed_days": 0, "inserted_instances": 0, "skipped_weekends": 0}

        logger.info(
            f"[DataPump] 节次映射就绪: {len(period_to_slot_id)} 个正课节次 "
            f"(period_index: {sorted(period_to_slot_id.keys())})"
        )

        # ── Step 2: 拉取所有静态课表模板 ──
        stmt = select(CourseSlot).where(
            CourseSlot.school_id == school_id,
            CourseSlot.is_active == True,
        )
        result = await db.execute(stmt)
        templates = result.scalars().all()

        if not templates:
            logger.warning(
                f"[DataPump] school_id={school_id} 的 course_slots 为空仓，"
                f"请先灌注静态课表母版"
            )
            return {"processed_days": 0, "inserted_instances": 0, "skipped_weekends": 0}

        logger.info(f"[DataPump] 静态课表母版已加载: {len(templates)} 条模板")

        # ── Step 3: 建立 (class_id, day_of_week) → [slot_info] 索引 ──
        template_index: Dict[str, List[Dict]] = {}
        for t in templates:
            key = f"{t.class_id}:{t.day_of_week}"
            if key not in template_index:
                template_index[key] = []
            template_index[key].append({
                "slot_number": t.slot_number,
                "course_id": t.course_id,
                "teacher_id": t.teacher_id,
                "classroom_id": t.classroom_id,
            })

        # ── Step 4: 逐日扫描，生成实例 ──
        inserted_total = 0
        skipped_weekends = 0
        processed_days = 0

        current = start_date
        while current <= end_date:
            # Python isoweekday: 1=Mon ... 7=Sun (匹配 MySQL SmallInteger day_of_week)
            iso_weekday = current.isoweekday()

            if iso_weekday >= 6:  # 周六、周日跳过
                skipped_weekends += 1
                current += timedelta(days=1)
                continue

            # 批量构建当天所有班级 x 节次的实例
            instance_payloads = []
            for class_key, slot_list in template_index.items():
                cid_str, dow_str = class_key.split(":")
                cid = int(cid_str)
                dow = int(dow_str)
                if dow != iso_weekday:
                    continue

                for sl in slot_list:
                    slot_number = sl["slot_number"]
                    slot_id = period_to_slot_id.get(slot_number)
                    if slot_id is None:
                        logger.debug(
                            f"[DataPump] slot_number={slot_number} 无对应 TimetableSlot，跳过"
                        )
                        continue

                    instance_payloads.append({
                        "school_id": school_id,
                        "class_id": cid,
                        "date": current,
                        "slot_id": slot_id,
                        "period_index": slot_number,
                        "subject_id": sl["course_id"],
                        "teacher_id": sl["teacher_id"],
                        "classroom_id": sl["classroom_id"],
                    })

            if instance_payloads:
                # 使用 MySQL ON DUPLICATE KEY UPDATE 保证幂等
                # uix_class_date_slot: (class_id, date, slot_id) 唯一约束
                stmt = mysql_insert(TimetableScheduleInstance).values(instance_payloads)

                # ON DUPLICATE KEY UPDATE: 更新可能变动的字段
                stmt = stmt.on_duplicate_key_update(
                    subject_id=stmt.inserted.subject_id,
                    teacher_id=stmt.inserted.teacher_id,
                    classroom_id=stmt.inserted.classroom_id,
                    is_adjusted=False,  # 重新泵入视为非调课
                )

                await db.execute(stmt)
                inserted_total += len(instance_payloads)

            processed_days += 1
            current += timedelta(days=1)

        await db.commit()

        logger.info(
            f"[DataPump] 拉伸完成: "
            f"processed_days={processed_days}, "
            f"inserted={inserted_total}, "
            f"skipped_weekends={skipped_weekends}"
        )

        return {
            "processed_days": processed_days,
            "inserted_instances": inserted_total,
            "skipped_weekends": skipped_weekends,
        }
