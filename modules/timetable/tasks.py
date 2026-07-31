"""
modules/timetable/tasks.py — Wings 3.1 时空发电机 (Celery Beat 定时任务)

每天凌晨 02:00 自动苏醒，将静态课表母版 (course_slots) 滚动拉伸为未来 7 天的
日历级课表实例 (timetable_schedule_instances)。

核心保障:
  - ON DUPLICATE KEY UPDATE 幂等: 重复触发不污染数据库
  - 周末自动跳过: 周六日不生成实例
  - 多租户全量滚动: 遍历所有 is_active 学校
  - prefork 安全: 引擎 dispose 双向守卫
"""

import asyncio
import logging
import os
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from modules.reports.celery_app import celery_engine

logger = logging.getLogger("wings.timetable.tasks")

# ═══════════════════════════════════════════════════════════════
# 独立数据库引擎 (避免与 app.py 循环导入)
# ═══════════════════════════════════════════════════════════════

_DATABASE_URL = os.environ.get("DATABASE_URL")

_task_engine = create_async_engine(
    _DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=3,       # 定时任务低频调用，保守连接池
    max_overflow=5,
    pool_timeout=30,
)

TaskSessionLocal = async_sessionmaker(
    _task_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ═══════════════════════════════════════════════════════════════
# 异步核心逻辑
# ═══════════════════════════════════════════════════════════════

async def _auto_generate_instances_async() -> dict:
    """
    遍历所有活跃学校租户，滚动生成今日到未来 7 天的课表实例。
    """
    from core.models import School
    from modules.timetable.data_pump import TimetableDataPump

    # Celery prefork: 清理上一轮 asyncio.run() 的 stale 连接
    await _task_engine.dispose()

    start_date = date.today()
    end_date = start_date + timedelta(days=7)

    logger.info(
        f"📡 时空发电机自动唤醒: {start_date} → {end_date} (7天滚动窗口)"
    )

    summary = {"schools_processed": 0, "total_inserted": 0, "errors": 0}

    async with TaskSessionLocal() as db:
        try:
            # 抓取所有活跃学校租户
            stmt = select(School).where(School.is_active == True)
            result = await db.execute(stmt)
            schools = result.scalars().all()

            if not schools:
                logger.warning("⚠️ 时空发电机空转: 无活跃学校租户")
                return summary

            logger.info(f"⚡ 检测到 {len(schools)} 个活跃学校租户")

            for school in schools:
                try:
                    logger.info(
                        f"🏫 学校 [ID={school.id}] {school.name}: "
                        f"滚动 {start_date} → {end_date}"
                    )

                    stats = await TimetableDataPump.pump_static_to_instances(
                        school_id=school.id,
                        start_date=start_date,
                        end_date=end_date,
                        db=db,
                    )

                    summary["schools_processed"] += 1
                    summary["total_inserted"] += stats["inserted_instances"]

                    logger.info(
                        f"✅ 学校 [ID={school.id}] 滚动完成: "
                        f"processed_days={stats['processed_days']}, "
                        f"inserted={stats['inserted_instances']}, "
                        f"skipped_weekends={stats['skipped_weekends']}"
                    )

                except Exception as exc:
                    summary["errors"] += 1
                    logger.error(
                        f"❌ 学校 [ID={school.id}] 滚动失败: {exc}",
                        exc_info=True,
                    )
                    # 不阻断其他学校的滚动，继续下一个
                    continue

        except Exception as e:
            await db.rollback()
            logger.error(f"❌ 时空发电机严重故障: {e}", exc_info=True)
            raise e

        await db.close()

    # Celery prefork: 清理本轮连接
    await _task_engine.dispose()

    logger.info(
        f"🎯 时空发电机转入休眠: "
        f"schools={summary['schools_processed']}, "
        f"inserted={summary['total_inserted']}, "
        f"errors={summary['errors']}"
    )

    return summary


# ═══════════════════════════════════════════════════════════════
# Celery 定时任务入口 (Beat → periodic 队列)
# ═══════════════════════════════════════════════════════════════

@celery_engine.task(
    bind=True,
    name="timetable.auto_generate_instances",
    max_retries=1,
    default_retry_delay=300,  # 失败后 5 分钟重试
)
def auto_generate_instances_task(self):
    """
    时空发电机 — Celery Beat 每日凌晨 02:00 触发。

    滚动生成未来 7 天的全校课表日历实例。
    依赖 data_pump.py 的 ON DUPLICATE KEY UPDATE 保证幂等。
    """
    logger.info("🔔 Celery Beat: 时空发电机定时触发")

    try:
        result = asyncio.run(_auto_generate_instances_async())
        logger.info(f"✅ 时空发电机任务完成: {result}")
        return result
    except Exception as exc:
        logger.error(f"💥 时空发电机任务失败: {exc}", exc_info=True)
        raise self.retry(exc=exc)
