"""
modules/growth/cep_interceptor.py — CEP (Complex Event Processing) 复合事件拦截器

BOSS Phase 4 方向二核心引擎 (#1452)

当考勤危机 × 学业断层在 48h 滑动时间窗内交汇时，自动唤醒 V3 AI 引擎
生成靶向处方，持久化至 ActiveCompositeAlert 表，并广播弹窗事件到
Redis pub/sub 频道 wings:notifications:popup。

核心机制:
  1. 双向状态咬合: 考勤事件入站 -> 点亮 attendance 窗口 -> 探测 error_funnel 窗口
                   学业事件入站 -> 点亮 error_funnel 窗口 -> 探测 attendance 窗口
     双向都亮 = 复合沸点
  2. 分布式冷却锁: SETNX wings:cep:lock:composite:{student_id} (TTL 3天)
     防止学生在连续错题时疯狂压榨 DeepSeek 算力，3天内只触发一次复合大招
  3. 零阻塞后台: asyncio.create_task() 异步触发，不阻塞 listener 事件流
  4. 多模态广播: 一端入库 ActiveCompositeAlert，另一端 PUBLISH 弹窗事件
  5. 失败回退: 干预失败时释放冷却锁，允许下次重试

调用方式 (从 listeners.py):
    interceptor = ComplexEventInterceptor()
    await interceptor.process_event(TRIGGER_ATTENDANCE, event_data)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.redis_client import get_redis

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
#  常量
# ═══════════════════════════════════════════════════════════════

WINDOW_TTL = 172_800      # 48 小时 — 滑动时间窗
COOLDOWN_TTL = 259_200    # 3 天 — 冷却锁

CH_NOTIFICATIONS_POPUP = "wings:notifications:popup"

# 触发源常量
TRIGGER_ATTENDANCE = "attendance"
TRIGGER_ERROR_FUNNEL = "error_funnel"


# ═══════════════════════════════════════════════════════════════
#  Wings 3.1 时空加权引擎
# ═══════════════════════════════════════════════════════════════

def _compute_timetable_weight(timetable_ctx: dict) -> float:
    """
    根据课表时空上下文计算 CEP 复合事件加权系数。

    设计思路:
      - 正课期间发生的异常行为影响更大（学生本应在专注学习）
      - 课间/午休/非教学时段 = 标准权重 1.0
      - 降级: 无课表上下文时默认为 1.0

    权重阶梯:
      1.5 — 正课(LESSON)期间
      1.0 — 非正课/课间/午休/无数据
    """
    if not timetable_ctx:
        return 1.0
    if timetable_ctx.get("in_lesson"):
        return 1.5
    return 1.0


def _build_timetable_prompt_section(timetable_ctx: dict, weight: float) -> str:
    """
    构建 DeepSeek V3 Prompt 中的 Wings 3.1 时空课表上下文段落。

    将 Enricher 返回的 (节次, 学科, 教师) 三维坐标转化为
    自然语言段落注入处方 Prompt，让 AI 能感知事件发生的
    课堂教学环境。
    """
    lines = ["## ⚡ 时空坐标系 (Wings 3.1 课堂课表上下文)", ""]
    lines.append(f"- 复合事件加权系数: ×{weight}")
    if timetable_ctx.get("in_lesson"):
        lines.append("- 事件发生时状态: **正在上课** (课堂环境)")
        if timetable_ctx.get("period_index") is not None:
            lines.append(f"- 具体节次: 第 {timetable_ctx['period_index']} 节课")
        if timetable_ctx.get("subject_id"):
            lines.append(f"- 当前学科ID: {timetable_ctx['subject_id']}")
        if timetable_ctx.get("teacher_id"):
            lines.append(f"- 任课教师ID: {timetable_ctx['teacher_id']}")
    else:
        lines.append("- 事件发生时状态: 课间/午休/非教学时段")
    lines.append(f"- 时空上下文: {timetable_ctx.get('context_desc', '无数据')}")
    lines.append("")
    lines.append(
        "> **重要提示**: 如果事件发生于上课时间，请在分析中额外考虑"
        "课堂纪律环境和学科特点对行为的影响。如果事件发生于非教学时段，"
        "请侧重于学生自主行为习惯的分析。"
    )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  异步引擎 (独立于 listeners 的 session_factory，避免 Session 争用)
# ═══════════════════════════════════════════════════════════════

_ASYNC_DB_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+aiomysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/wings3",
)
_async_engine: Optional[Any] = None
_AsyncSessionLocal: Optional[async_sessionmaker] = None


def _get_async_session_factory() -> async_sessionmaker:
    """惰性初始化异步 session 工厂 (模块级单例)"""
    global _async_engine, _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        _async_engine = create_async_engine(
            _ASYNC_DB_URL,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=2,
        )
        _AsyncSessionLocal = async_sessionmaker(
            _async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _AsyncSessionLocal


# ═══════════════════════════════════════════════════════════════
#  CEP 核心拦截网关
# ═══════════════════════════════════════════════════════════════


class ComplexEventInterceptor:
    """
    CEP 核心拦截网关 — 复合事件处理引擎

    生命周期:
      1. process_event() — 事件入站，状态盖章 + 双向探针 + 冷却锁抢占
      2. _execute_active_intervention() — 后台异步：13路上下文 → DeepSeek → 持久化 → 广播
      3. _build_context() — 委托 AIPrescriptionAggregator 构建学生黄金上下文
      4. _persist_alert() — 持久化 ActiveCompositeAlert
      5. _broadcast_popup() — Redis PUBLISH 弹窗事件
    """

    def __init__(self):
        self.redis = get_redis()

    # ─────────────────────────────────────────────
    #  Step 1: 事件入站处理
    # ─────────────────────────────────────────────

    async def process_event(
        self,
        trigger_source: str,
        event_data: Dict[str, Any],
    ) -> None:
        """
        事件入站处理 — 状态盖章 → 双向探针扫描 → 冷却锁抢占 → 唤醒V3

        Args:
            trigger_source: TRIGGER_ATTENDANCE 或 TRIGGER_ERROR_FUNNEL
            event_data: 事件载荷 (需含 student_id, school_id)
        """
        student_id = event_data.get("student_id")
        school_id = event_data.get("school_id")

        if not student_id or not school_id:
            logger.debug("[CEP] 事件缺少 student_id/school_id, 跳过")
            return

        if self.redis is None:
            logger.debug("[CEP] Redis 不可用, CEP 降级跳过")
            return

        # ── Step 1a: 状态盖章 — 在当前触发源的窗口上点亮灯 ──
        window_key = f"wings:cep:window:{trigger_source}:{student_id}"
        try:
            await self.redis.set(window_key, "1", ex=WINDOW_TTL)
            logger.debug(
                "[CEP] 窗口盖章 | source=%s student=%s",
                trigger_source, student_id,
            )
        except Exception as e:
            logger.warning("[CEP] 窗口盖章失败, 跳过: %s", e)
            return

        # ── Step 1b: 双向探针 — 检查对侧窗口是否已点亮 ──
        opposite_source = (
            TRIGGER_ERROR_FUNNEL
            if trigger_source == TRIGGER_ATTENDANCE
            else TRIGGER_ATTENDANCE
        )
        opposite_key = f"wings:cep:window:{opposite_source}:{student_id}"

        try:
            opposite_exists = await self.redis.exists(opposite_key)
        except Exception as e:
            logger.warning("[CEP] 探针扫描失败: %s", e)
            return

        if not opposite_exists:
            logger.debug(
                "[CEP] 单侧事件, 未交汇 | student=%s trigger=%s opposite=%s (未点亮)",
                student_id, trigger_source, opposite_source,
            )
            return

        # ── 交汇沸点! 双向窗口都亮了 ──
        logger.info(
            "[CEP] 复合沸点交汇! student=%s | %s x %s",
            student_id, trigger_source, opposite_source,
        )

        # ── Step 1c: 冷却锁抢占 — SETNX 3天 TTL ──
        cooldown_key = f"wings:cep:lock:composite:{student_id}"
        try:
            acquired = await self.redis.set(
                cooldown_key, "1", ex=COOLDOWN_TTL, nx=True,
            )
        except Exception as e:
            logger.warning("[CEP] 冷却锁异常: %s", e)
            return

        if not acquired:
            logger.info(
                "[CEP] 冷却锁未获取, 3天内已触发过 | student=%s",
                student_id,
            )
            return

        # ── Step 1d: 唤醒 V3 引擎 — 零阻塞后台任务 ──
        # Wings 3.1: 提取时空上下文 & 计算加权系数
        timetable_ctx = event_data.get("_timetable_context", {})

        trigger_meta = {
            "trigger_source": trigger_source,
            "opposite_source": opposite_source,
            "attendance_window_key": f"wings:cep:window:{TRIGGER_ATTENDANCE}:{student_id}",
            "error_funnel_window_key": f"wings:cep:window:{TRIGGER_ERROR_FUNNEL}:{student_id}",
            "cooldown_key": cooldown_key,
            "triggered_at": datetime.utcnow().isoformat(),
            "trigger_event": {
                k: v for k, v in event_data.items()
                if k in (
                    "knowledge_point", "consecutive_errors", "error_count",
                    "absent_count", "absent_dates", "class_id", "level",
                    "category", "deduction",
                )
            },
            # ⚡ Wings 3.1 时空连续体: 课表上下文 + 加权系数
            "timetable_context": timetable_ctx if timetable_ctx else None,
            "weight_factor": _compute_timetable_weight(timetable_ctx),
        }

        # 后台异步执行 — 不阻塞 listener 事件循环
        asyncio.create_task(
            self._execute_active_intervention(
                student_id, school_id, trigger_meta,
            )
        )
        logger.info(
            "[CEP] V3 引擎已唤醒 (后台) | student=%s",
            student_id,
        )

    # ─────────────────────────────────────────────
    #  Step 2: V3 主动干预执行器
    # ─────────────────────────────────────────────

    async def _execute_active_intervention(
        self,
        student_id: int,
        school_id: int,
        trigger_meta: Dict[str, Any],
    ) -> None:
        """
        V3 主动干预执行器 — 13路上下文 → DeepSeek → 持久化 → 广播

        全程 try/except 包裹，任何异常不影响主事件流。
        干预失败时释放冷却锁，允许下次重试。
        """
        t0 = datetime.utcnow()
        logger.info(
            "[CEP-V3] 干预启动 | student=%s school=%s",
            student_id, school_id,
        )

        try:
            # ── Step 2a: 构建 13 路学生黄金上下文 ──
            context = await self._build_context(student_id, school_id)
            logger.info("[CEP-V3] 上下文构建完成 | student=%s", student_id)

            # ── Step 2b: 构建 Prompt + 调用 DeepSeek ──
            # tasks.py 的 _call_deepseek / _build_student_prompt 是同步函数
            # 用 asyncio.to_thread 在线程池中执行，不阻塞事件循环
            from modules.ai_prescription.tasks import (
                SYSTEM_PROMPT_STUDENT,
                _build_student_prompt,
                _call_deepseek,
            )

            prompt = _build_student_prompt(context)

            # ⚡ Wings 3.1: 注入时空课表上下文到 V3 处方 Prompt
            timetable_ctx = trigger_meta.get("timetable_context")
            if timetable_ctx:
                timetable_section = _build_timetable_prompt_section(
                    timetable_ctx, trigger_meta.get("weight_factor", 1.0)
                )
                prompt = prompt + "\n\n" + timetable_section

            result = await asyncio.to_thread(
                _call_deepseek, prompt, SYSTEM_PROMPT_STUDENT, 90,
            )

            # 解析 LLM 输出
            full_text = result.get("full_text", "")
            fact_text = result.get("fact", "")
            analysis_text = result.get("analysis", "")
            growth_text = result.get("growth", "")
            summary = result.get("summary", "")
            risk_level = result.get("risk_level", "HIGH")

            # 兜底拼接
            if not full_text and (fact_text or analysis_text or growth_text):
                full_text = f"{fact_text}\n\n{analysis_text}\n\n{growth_text}"

            logger.info(
                "[CEP-V3] DeepSeek 处方生成完成 | student=%s risk=%s",
                student_id, risk_level,
            )

            # ── Step 2c: 持久化 ActiveCompositeAlert ──
            alert_id = await self._persist_alert(
                student_id, school_id, trigger_meta, full_text, summary,
            )

            # ── Step 2d: 广播弹窗事件到 Redis ──
            await self._broadcast_popup(
                student_id, school_id, alert_id, summary, trigger_meta,
            )

            elapsed = (datetime.utcnow() - t0).total_seconds()
            logger.info(
                "[CEP-V3] 干预完成 | student=%s alert=%s 耗时=%.1fs",
                student_id, alert_id, elapsed,
            )

        except Exception as e:
            logger.error(
                "[CEP-V3] 干预失败 | student=%s: %s",
                student_id, e, exc_info=True,
            )
            # 干预失败 → 释放冷却锁，允许下次重试
            if self.redis:
                try:
                    await self.redis.delete(
                        f"wings:cep:lock:composite:{student_id}"
                    )
                    logger.info(
                        "[CEP-V3] 冷却锁已释放(干预失败,允许重试) | student=%s",
                        student_id,
                    )
                except Exception:
                    pass

    # ─────────────────────────────────────────────
    #  Step 3: 构建 13 路学生上下文
    # ─────────────────────────────────────────────

    async def _build_context(
        self, student_id: int, school_id: int,
    ) -> dict:
        """
        构建学生 13 路黄金上下文 — 委托给 AIPrescriptionAggregator

        复用 tasks.py 的异步桥接模式: 独立 async engine + session
        """
        from modules.ai_prescription.aggregator import AIPrescriptionAggregator

        factory = _get_async_session_factory()
        async with factory() as db:
            ctx = await AIPrescriptionAggregator.build_student_context(
                db, student_id=student_id, school_id=school_id, days=30,
            )
        return ctx

    # ─────────────────────────────────────────────
    #  Step 4: 持久化预警记录
    # ─────────────────────────────────────────────

    async def _persist_alert(
        self,
        student_id: int,
        school_id: int,
        trigger_meta: Dict[str, Any],
        prescription_text: str,
        summary: str,
    ) -> Optional[int]:
        """
        持久化 ActiveCompositeAlert 到数据库

        Returns:
            alert_id 或 None (失败时)
        """
        from modules.growth.models import ActiveCompositeAlert

        # 构建预警标题
        trigger_event = trigger_meta.get("trigger_event", {})
        title_parts = ["复合预警"]
        detail_parts = []

        if trigger_event.get("absent_count"):
            detail_parts.append(f"连续缺勤{trigger_event['absent_count']}天")
        if trigger_event.get("knowledge_point"):
            detail_parts.append(f"知识断层critical({trigger_event['knowledge_point']})")
        if trigger_event.get("consecutive_errors"):
            detail_parts.append(f"连续错题{trigger_event['consecutive_errors']}次")

        if detail_parts:
            title_parts.append(" | ".join(detail_parts))

        title = " + ".join(title_parts) + f" | 学生#{student_id}"

        factory = _get_async_session_factory()
        async with factory() as session:
            try:
                alert = ActiveCompositeAlert(
                    school_id=school_id,
                    student_id=student_id,
                    alert_type="CRITICAL_COMPOSITE",
                    title=title[:200],
                    reason_meta=json.dumps(
                        trigger_meta, ensure_ascii=False, default=str,
                    ),
                    ai_prescription=prescription_text,
                    is_resolved=False,
                )
                session.add(alert)
                await session.commit()
                await session.refresh(alert)
                logger.info(
                    "[CEP-V3] 预警已持久化 | alert_id=%s student=%s",
                    alert.id, student_id,
                )
                return alert.id
            except Exception as e:
                await session.rollback()
                logger.error(
                    "[CEP-V3] 持久化失败: %s", e, exc_info=True,
                )
                return None

    # ─────────────────────────────────────────────
    #  Step 5: 广播弹窗事件
    # ─────────────────────────────────────────────

    async def _broadcast_popup(
        self,
        student_id: int,
        school_id: int,
        alert_id: Optional[int],
        summary: str,
        trigger_meta: Dict[str, Any],
    ) -> None:
        """
        广播弹窗事件到 Redis pub/sub 频道 wings:notifications:popup

        前端通过 SSE/WebSocket 订阅此频道，实现班主任主页弹窗。
        """
        if self.redis is None:
            return

        popup_data = {
            "type": "composite_alert",
            "school_id": school_id,
            "student_id": student_id,
            "alert_id": alert_id,
            "title": "复合预警: 考勤危机 x 学业断层",
            "summary": (
                summary[:200]
                if summary
                else "系统检测到该学生存在考勤与学业双重风险，已自动生成AI干预处方。"
            ),
            "trigger": trigger_meta.get("trigger_source"),
            "triggered_at": trigger_meta.get("triggered_at"),
            "created_at": datetime.utcnow().isoformat(),
        }

        try:
            await self.redis.publish(
                CH_NOTIFICATIONS_POPUP,
                json.dumps(popup_data, ensure_ascii=False),
            )
            logger.info(
                "[CEP-V3] 弹窗已广播 | channel=%s student=%s",
                CH_NOTIFICATIONS_POPUP, student_id,
            )
        except Exception as e:
            logger.warning("[CEP-V3] 弹窗广播失败: %s", e)
