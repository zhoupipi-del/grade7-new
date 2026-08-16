"""
modules/research_ai/tasks.py
=============================
教研 AI Celery 异步任务。

复用 wings3 主 Celery 引擎（modules.reports.celery_app.celery_engine），
队列 high_priority（AI 任务 10-60s，Worker concurrency=4）。

任务：
  - research_ai.generate_lesson_plan：单篇教案生成
  - research_ai.generate_homework：分层作业生成

作文批改为同步 API（单篇 30-60s 可接受），不进 Celery。

注意：Celery worker 是同步进程，需要在任务内部用 asyncio.run
驱动异步的 service 层，每次任务创建独立的 async engine。
"""
from __future__ import annotations

import asyncio
import logging
import os

from celery import Task

from modules.reports.celery_app import celery_engine

logger = logging.getLogger(__name__)


def _run_async(coro):
    """在 Celery 同步任务中运行 async 协程。"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.run(coro)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _mark_lesson_item_failed(item_id: int, error_msg: str) -> None:
    """
    [V2.1.1] Celery 重试全部耗尽后，把 item 标记为最终 failed，
    并刷新 batch 聚合状态。service 层在 transport error 时只保持 processing，
    不写 terminal failed；只有本函数被调用时才是真正的终态。
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from core.models import get_local_now
    from modules.research_ai.models_lesson_plan import LessonPlanItem
    from modules.research_ai.services_lesson_plan import _refresh_task_status

    engine = create_async_engine(
        os.environ.get("DATABASE_URL", ""),
        pool_pre_ping=True, pool_recycle=300, pool_size=2,
    )
    try:
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as db:
            item = await db.get(LessonPlanItem, item_id)
            if item and item.status != "success":
                item.status = "failed"
                item.error_msg = error_msg[:500]
                item.finished_at = get_local_now()
                db.add(item)
                await db.commit()
                await _refresh_task_status(db, item.task_id)
    finally:
        await engine.dispose()


async def _mark_homework_task_failed(task_id: int, error_msg: str) -> None:
    """[V2.1.1] Celery 重试耗尽后，把 homework task 标记为最终 failed。"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from core.models import get_local_now
    from modules.research_ai.models_homework import HomeworkTask

    engine = create_async_engine(
        os.environ.get("DATABASE_URL", ""),
        pool_pre_ping=True, pool_recycle=300, pool_size=2,
    )
    try:
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as db:
            task = await db.get(HomeworkTask, task_id)
            if task and task.status != "success":
                task.status = "failed"
                task.error_msg = error_msg[:2000]
                task.finished_at = get_local_now()
                db.add(task)
                await db.commit()
    finally:
        await engine.dispose()


# ════════════════════════════════════════════════════════════
# 教案批量生成
# ════════════════════════════════════════════════════════════

@celery_engine.task(
    bind=True,
    name="research_ai.generate_lesson_plan",
    queue="high_priority",
    max_retries=2,
    acks_late=True,
    default_retry_delay=5,
)
def generate_lesson_plan(self: Task, item_id: int) -> dict:
    """单篇教案生成（批量接口逐篇派发，worker 可并发执行）。"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from modules.research_ai.services_lesson_plan import generate_one_lesson

    async def _run():
        engine = create_async_engine(
            os.environ.get("DATABASE_URL", ""),
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=2,
        )
        async_session = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        try:
            async with async_session() as db:
                await generate_one_lesson(db, item_id)
        finally:
            await engine.dispose()

    try:
        logger.info("[ResearchAI-Task] 开始生成教案 item=%s", item_id)
        _run_async(_run())
        return {"status": "SUCCESS", "item_id": item_id}
    except Exception as exc:  # noqa: BLE001
        logger.exception("[ResearchAI-Task] 教案生成失败 item=%s", item_id)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries * 5)
        # [V2.1.1] 重试耗尽，标记最终 failed
        try:
            _run_async(_mark_lesson_item_failed(item_id, f"重试耗尽：{exc}"))
        except Exception:  # noqa: BLE001
            logger.exception("[ResearchAI-Task] 标记教案 item=%s 最终失败时出错", item_id)
        return {"status": "FAILURE", "item_id": item_id, "error": str(exc)}


# ════════════════════════════════════════════════════════════
# 分层作业生成
# ════════════════════════════════════════════════════════════

@celery_engine.task(
    bind=True,
    name="research_ai.generate_homework",
    queue="high_priority",
    max_retries=2,
    acks_late=True,
    default_retry_delay=10,
)
def generate_homework(self: Task, task_id: int) -> dict:
    """分层作业生成（单次 15-40 秒）。"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from modules.research_ai.services_homework import generate_layered_homework

    async def _run():
        engine = create_async_engine(
            os.environ.get("DATABASE_URL", ""),
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=2,
        )
        async_session = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        try:
            async with async_session() as db:
                await generate_layered_homework(db, task_id)
        finally:
            await engine.dispose()

    try:
        logger.info("[ResearchAI-Task] 开始生成分层作业 task=%s", task_id)
        _run_async(_run())
        return {"status": "SUCCESS", "task_id": task_id}
    except Exception as exc:  # noqa: BLE001
        logger.exception("[ResearchAI-Task] 分层作业生成失败 task=%s", task_id)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries * 10)
        # [V2.1.1] 重试耗尽，标记最终 failed
        try:
            _run_async(_mark_homework_task_failed(task_id, f"重试耗尽：{exc}"))
        except Exception:  # noqa: BLE001
            logger.exception("[ResearchAI-Task] 标记作业 task=%s 最终失败时出错", task_id)
        return {"status": "FAILURE", "task_id": task_id, "error": str(exc)}



# ════════════════════════════════════════════════════════════
# V2.2 新功能：AI 试卷命制
# ════════════════════════════════════════════════════════════

async def _mark_paper_task_failed(task_id: int, error_msg: str) -> None:
    """[V2.2] Celery 重试耗尽后，把 paper task 标记为最终 failed。"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from core.models import get_local_now
    from modules.research_ai.models_paper import PaperTask

    engine = create_async_engine(
        os.environ.get("DATABASE_URL", ""),
        pool_pre_ping=True, pool_recycle=300, pool_size=2,
    )
    try:
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as db:
            task = await db.get(PaperTask, task_id)
            if task and task.status != "success":
                task.status = "failed"
                task.error_msg = error_msg[:2000]
                task.finished_at = get_local_now()
                db.add(task)
                await db.commit()
    finally:
        await engine.dispose()


@celery_engine.task(
    bind=True,
    name="research_ai.generate_paper",
    queue="high_priority",
    max_retries=2,
    acks_late=True,
    default_retry_delay=10,
)
def generate_paper(self: Task, task_id: int) -> dict:
    """试卷命制（单次 15-60 秒）。"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from modules.research_ai.services_paper import generate_paper as _gen

    async def _run():
        engine = create_async_engine(
            os.environ.get("DATABASE_URL", ""),
            pool_pre_ping=True, pool_recycle=300, pool_size=2,
        )
        async_session = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        try:
            async with async_session() as db:
                await _gen(db, task_id)
        finally:
            await engine.dispose()

    try:
        logger.info("[ResearchAI-Task] 开始命制试卷 task=%s", task_id)
        _run_async(_run())
        return {"status": "SUCCESS", "task_id": task_id}
    except Exception as exc:  # noqa: BLE001
        logger.exception("[ResearchAI-Task] 试卷命制失败 task=%s", task_id)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries * 10)
        try:
            _run_async(_mark_paper_task_failed(task_id, f"重试耗尽：{exc}"))
        except Exception:  # noqa: BLE001
            logger.exception("[ResearchAI-Task] 标记试卷 task=%s 最终失败时出错", task_id)
        return {"status": "FAILURE", "task_id": task_id, "error": str(exc)}


# ════════════════════════════════════════════════════════════
# V2.2 新功能：AI 学情分析报告
# ════════════════════════════════════════════════════════════

async def _mark_analysis_task_failed(task_id: int, error_msg: str) -> None:
    """[V2.2] Celery 重试耗尽后，把 analysis task 标记为最终 failed。"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from core.models import get_local_now
    from modules.research_ai.models_analysis import AnalysisTask

    engine = create_async_engine(
        os.environ.get("DATABASE_URL", ""),
        pool_pre_ping=True, pool_recycle=300, pool_size=2,
    )
    try:
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as db:
            task = await db.get(AnalysisTask, task_id)
            if task and task.status != "success":
                task.status = "failed"
                task.error_msg = error_msg[:2000]
                task.finished_at = get_local_now()
                db.add(task)
                await db.commit()
    finally:
        await engine.dispose()


@celery_engine.task(
    bind=True,
    name="research_ai.generate_analysis",
    queue="high_priority",
    max_retries=2,
    acks_late=True,
    default_retry_delay=10,
)
def generate_analysis(self: Task, task_id: int) -> dict:
    """学情分析报告（单次 15-60 秒）。"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from modules.research_ai.services_analysis import generate_analysis as _gen

    async def _run():
        engine = create_async_engine(
            os.environ.get("DATABASE_URL", ""),
            pool_pre_ping=True, pool_recycle=300, pool_size=2,
        )
        async_session = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        try:
            async with async_session() as db:
                await _gen(db, task_id)
        finally:
            await engine.dispose()

    try:
        logger.info("[ResearchAI-Task] 开始学情分析 task=%s", task_id)
        _run_async(_run())
        return {"status": "SUCCESS", "task_id": task_id}
    except Exception as exc:  # noqa: BLE001
        logger.exception("[ResearchAI-Task] 学情分析失败 task=%s", task_id)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries * 10)
        try:
            _run_async(_mark_analysis_task_failed(task_id, f"重试耗尽：{exc}"))
        except Exception:  # noqa: BLE001
            logger.exception("[ResearchAI-Task] 标记学情 task=%s 最终失败时出错", task_id)
        return {"status": "FAILURE", "task_id": task_id, "error": str(exc)}


# ════════════════════════════════════════════════════════════
# V2.2 新功能：AI 学生评语生成
# ════════════════════════════════════════════════════════════

async def _mark_comment_task_failed(task_id: int, error_msg: str) -> None:
    """[V2.2] Celery 重试耗尽后，把 comment task 标记为最终 failed。"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from core.models import get_local_now
    from modules.research_ai.models_comment import CommentTask

    engine = create_async_engine(
        os.environ.get("DATABASE_URL", ""),
        pool_pre_ping=True, pool_recycle=300, pool_size=2,
    )
    try:
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as db:
            task = await db.get(CommentTask, task_id)
            if task and task.status != "success":
                task.status = "failed"
                task.error_msg = error_msg[:2000]
                task.finished_at = get_local_now()
                db.add(task)
                await db.commit()
    finally:
        await engine.dispose()


@celery_engine.task(
    bind=True,
    name="research_ai.generate_comments",
    queue="high_priority",
    max_retries=2,
    acks_late=True,
    default_retry_delay=10,
)
def generate_comments(self: Task, task_id: int) -> dict:
    """学生评语批量生成（单次 15-60 秒）。"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from modules.research_ai.services_comment import generate_comments as _gen

    async def _run():
        engine = create_async_engine(
            os.environ.get("DATABASE_URL", ""),
            pool_pre_ping=True, pool_recycle=300, pool_size=2,
        )
        async_session = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        try:
            async with async_session() as db:
                await _gen(db, task_id)
        finally:
            await engine.dispose()

    try:
        logger.info("[ResearchAI-Task] 开始生成学生评语 task=%s", task_id)
        _run_async(_run())
        return {"status": "SUCCESS", "task_id": task_id}
    except Exception as exc:  # noqa: BLE001
        logger.exception("[ResearchAI-Task] 学生评语生成失败 task=%s", task_id)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries * 10)
        try:
            _run_async(_mark_comment_task_failed(task_id, f"重试耗尽：{exc}"))
        except Exception:  # noqa: BLE001
            logger.exception("[ResearchAI-Task] 标记评语 task=%s 最终失败时出错", task_id)
        return {"status": "FAILURE", "task_id": task_id, "error": str(exc)}
