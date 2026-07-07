"""
modules/risk_models/tasks.py — RDI 风险预警异步任务 (Phase 2B 投产)

Celery 异步任务，将 RDI 扫描从 HTTP 请求生命周期迁移至 maintenance 队列。

任务清单:
  - rdi_scan_class:  单班风险扫描 (遍历学生 → calculate_rdi → create_warning)
  - rdi_scan_school: 全校风险扫描 (查询班级 → 逐班 dispatch)
  - rdi_daily_scan:  每日定时全量扫描 (Celery Beat 调度)
"""

import asyncio
import logging
import os
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from modules.reports.celery_app import celery_engine

logger = logging.getLogger("risk_models.tasks")

# ═══════════════════════════════════════════════════════════════
# 独立数据库引擎 (避免与 app.py 循环导入)
# ═══════════════════════════════════════════════════════════════

_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+aiomysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new",
)

_task_engine = create_async_engine(
    _DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
)

TaskSessionLocal = async_sessionmaker(
    _task_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ═══════════════════════════════════════════════════════════════
# 异步核心逻辑 (供 asyncio.run() 桥接)
# ═══════════════════════════════════════════════════════════════

async def _rdi_scan_class_async(
    school_id: int, class_id: int, semester: str = None
) -> dict:
    """单班异步扫描 — 遍历学生 → 计算 RDI → 生成预警"""
    from core.models import Student
    from .services import RiskDeviationIndexCalculator, RiskWarningService

    # Celery prefork: 清理上一轮 asyncio.run() 的 stale 连接
    await _task_engine.dispose()

    t0 = time.time()
    async with TaskSessionLocal() as db:
        # 1. 查询班级活跃学生
        result = await db.execute(
            select(Student).where(
                Student.school_id == school_id,
                Student.class_id == class_id,
                Student.is_active == True,
            )
        )
        students = result.scalars().all()
        student_count = len(students)
        logger.info(
            f"[RDI] 班级扫描: school={school_id} class={class_id} "
            f"students={student_count}"
        )

        if student_count == 0:
            await db.close()
            return {
                "status": "ok",
                "school_id": school_id,
                "class_id": class_id,
                "semester": semester,
                "students_scanned": 0,
                "warnings_generated": 0,
            }

        # 2. 初始化计算器 + 预警服务
        calculator = RiskDeviationIndexCalculator(db, school_id)
        warning_service = RiskWarningService()

        scanned = 0
        warnings_generated = 0
        errors = 0

        for student in students:
            try:
                rdi = await calculator.calculate_rdi(
                    student_id=student.id,
                    suppress_low_rdi=True,
                )
                scanned += 1

                if (
                    not rdi["warning_suppressed"]
                    and rdi["rdi_score"] >= calculator.min_rdi_to_warn
                ):
                    warning = await warning_service.create_warning(
                        db, school_id, rdi, trigger_event_type="batch_scan"
                    )
                    warnings_generated += 1

                    # Phase 2C: 高危自动触发 AI 处方桥接
                    if rdi.get("risk_level") == "intervention":
                        try:
                            from modules.ai_prescription.tasks import bridge_rdi_to_approval
                            bridge_rdi_to_approval.delay(
                                student_id=student.id,
                                school_id=school_id,
                                warning_id=warning.id,
                                rdi_score=rdi["rdi_score"],
                            )
                            logger.info(
                                f"[RDI] 高危桥接触发 | student={student.id} "
                                f"warning={warning.id} rdi={rdi['rdi_score']:.2f} "
                                f"→ bridge_rdi_to_approval 已入队"
                            )
                        except Exception as bridge_exc:
                            logger.error(
                                f"[RDI] 桥接触发失败 (不影响扫描) | "
                                f"student={student.id}: {bridge_exc}"
                            )
            except ValueError:
                # 学生数据不足 (无违纪/考勤/评价记录)，跳过
                scanned += 1
            except Exception as exc:
                logger.error(
                    f"[RDI] 学生 {student.id} 扫描异常: {exc}", exc_info=True
                )
                errors += 1
                continue

        await db.commit()

    # Celery prefork: dispose 本轮的连接避免 "Event loop is closed" 清理错误
    await _task_engine.dispose()

    elapsed = round((time.time() - t0) * 1000, 0)
    result = {
        "status": "ok",
        "school_id": school_id,
        "class_id": class_id,
        "semester": semester,
        "students_scanned": scanned,
        "warnings_generated": warnings_generated,
        "errors": errors,
        "elapsed_ms": elapsed,
    }
    logger.info(
        f"[RDI] 班级扫描完成 | class={class_id} "
        f"扫描{scanned}人 预警{warnings_generated}人 错误{errors}人 耗时{elapsed}ms"
    )
    return result


async def _rdi_scan_school_async(school_id: int, semester: str = None) -> dict:
    """全校异步扫描 — 查询班级 → 逐班 dispatch rdi_scan_class"""
    from core.models import Class

    # Celery prefork: 清理上一轮 asyncio.run() 的 stale 连接
    await _task_engine.dispose()

    async with TaskSessionLocal() as db:
        result = await db.execute(
            select(Class).where(
                Class.school_id == school_id,
                Class.is_active == True,
            )
        )
        classes = result.scalars().all()

        logger.info(
            f"[RDI] 全校扫描: school={school_id} classes={len(classes)}"
        )

        dispatched = 0
        for cls in classes:
            rdi_scan_class.delay(
                school_id=school_id,
                class_id=cls.id,
                semester=semester,
            )
            dispatched += 1

        await db.close()

    # Celery prefork: dispose 本轮的连接
    await _task_engine.dispose()

    result = {
        "status": "ok",
        "school_id": school_id,
        "semester": semester,
        "classes_dispatched": dispatched,
    }
    logger.info(
        f"[RDI] 全校扫描 dispatch 完成: {dispatched} 个班级已入队"
    )
    return result


async def _rdi_daily_scan_async() -> dict:
    """每日定时全量扫描 — 遍历所有活跃学校 → dispatch rdi_scan_school"""
    from core.models import School

    # Celery prefork: 清理上一轮 asyncio.run() 的 stale 连接
    await _task_engine.dispose()

    async with TaskSessionLocal() as db:
        result = await db.execute(
            select(School).where(School.is_active == True)
        )
        schools = result.scalars().all()

        logger.info(f"[RDI] 每日定时扫描: {len(schools)} 所学校")

        dispatched = 0
        for school in schools:
            rdi_scan_school.delay(school_id=school.id)
            dispatched += 1

        await db.close()

    # Celery prefork: dispose 本轮的连接
    await _task_engine.dispose()

    result = {
        "status": "ok",
        "schools_dispatched": dispatched,
    }
    logger.info(
        f"[RDI] 每日定时扫描 dispatch 完成: {dispatched} 所学校已入队"
    )
    return result


# ═══════════════════════════════════════════════════════════════
# Celery 任务包装 (同步入口 → asyncio.run 桥接)
# ═══════════════════════════════════════════════════════════════

@celery_engine.task(
    bind=True,
    name="risk_models.rdi_scan_class",
    max_retries=2,
    default_retry_delay=300,  # 5 分钟后重试
    autoretry_for=(Exception,),
)
def rdi_scan_class(self, school_id: int, class_id: int, semester: str = None):
    """
    单班 RDI 风险扫描 (异步 — maintenance 队列)

    对指定班级全部学生执行 Z-Score + EWMA 计算，生成 RiskWarning 记录。
    使用 asyncio.run() 桥接同步 Celery → 异步 Calculator。
    """
    logger.info(
        f"[RDI] 班级风险扫描启动 | school={school_id} "
        f"class={class_id} semester={semester}"
    )
    try:
        return asyncio.run(
            _rdi_scan_class_async(school_id, class_id, semester)
        )
    except Exception as exc:
        logger.error(
            f"[RDI] 班级扫描失败 | class={class_id}: {exc}", exc_info=True
        )
        raise self.retry(exc=exc)


@celery_engine.task(
    bind=True,
    name="risk_models.rdi_scan_school",
    max_retries=1,
    default_retry_delay=600,  # 10 分钟后重试
    autoretry_for=(Exception,),
)
def rdi_scan_school(self, school_id: int, semester: str = None):
    """
    全校 RDI 风险扫描 (异步 — maintenance 队列)

    遍历学校下全部班级，逐班调用 rdi_scan_class.delay()。
    """
    logger.info(
        f"[RDI] 全校风险扫描启动 | school={school_id} semester={semester}"
    )
    try:
        return asyncio.run(_rdi_scan_school_async(school_id, semester))
    except Exception as exc:
        logger.error(
            f"[RDI] 全校扫描失败 | school={school_id}: {exc}", exc_info=True
        )
        raise self.retry(exc=exc)


@celery_engine.task(
    bind=True,
    name="risk_models.rdi_daily_scan",
    max_retries=1,
    default_retry_delay=1800,  # 30 分钟后重试
    autoretry_for=(Exception,),
)
def rdi_daily_scan(self):
    """
    每日定时全量 RDI 扫描 (Celery Beat → periodic 队列)

    凌晨 1:00 执行，遍历所有活跃学校 → dispatch 全校扫描。
    """
    logger.info("[RDI] 每日定时全量扫描启动")
    try:
        return asyncio.run(_rdi_daily_scan_async())
    except Exception as exc:
        logger.error(f"[RDI] 每日定时扫描失败: {exc}", exc_info=True)
        raise self.retry(exc=exc)
