"""
core/event_bus.py - Redis pub/sub 分布式事件总线

解决 4 Workers 下内存事件总线丢失 75% 事件的问题。
通过 Redis pub/sub 实现跨进程通信，任何 Worker publish 的事件，
所有 Worker 的订阅者都能收到。

设计原则:
  1. fire-and-forget: publish 不阻塞调用方，上游模块零感知
  2. 异常沙箱: 订阅者处理器异常不外泄，不影响发布方
  3. 单例模式: 全局唯一 EventBus 实例
  4. 优雅关闭: shutdown 取消所有监听任务

频道命名规范: {module}.{event}
  error_funnel.critical       - 错题断层 critical 触发
  behavior.disciplined        - 违纪处分创建
  psych.risk_changed          - 心理风险等级变更
  attendance.consecutive_absent - 连续缺勤预警
"""

import json
import asyncio
import logging
from typing import Any, Callable, Awaitable, Optional, Dict, List

from core.redis_client import get_redis

logger = logging.getLogger(__name__)

# 处理器类型: async def handler(event: dict) -> None
Handler = Callable[[Dict[str, Any]], Awaitable[None]]


class EventBus:
    """
    基于 Redis pub/sub 的跨进程分布式事件总线。

    单例模式 — 所有模块共享同一个实例。
    """

    _instance: Optional["EventBus"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tasks: List[asyncio.Task] = []
            cls._instance._channels: Dict[str, Handler] = {}
            cls._instance._started = False
        return cls._instance

    # ═══════════════════════════════════════════════════════════════
    #  发布 (上游模块调用)
    # ═══════════════════════════════════════════════════════════════

    def publish(self, channel: str, event: Dict[str, Any]):
        """
        fire-and-forget 发布事件 — 不阻塞调用方。

        在当前事件循环中创建后台任务执行 Redis PUBLISH，
        调用方无需 await，上游模块零感知。

        Args:
            channel: 频道名 (如 "behavior.disciplined")
            event:   事件载荷 dict (必须 JSON 可序列化)
        """
        redis = get_redis()
        if redis is None:
            # Redis 不可用 — 静默降级，不阻塞业务
            return
        # 后台任务发布，不等待
        asyncio.create_task(self._do_publish(redis, channel, event))

    async def _do_publish(self, redis, channel: str, event: Dict[str, Any]):
        """实际执行 Redis PUBLISH"""
        try:
            payload = json.dumps(event, default=str, ensure_ascii=False)
            await redis.publish(channel, payload)
        except Exception as e:
            logger.error(f"[EventBus] publish 失败 channel={channel}: {e}")

    # ═══════════════════════════════════════════════════════════════
    #  订阅 (growth listeners 调用)
    # ═══════════════════════════════════════════════════════════════

    async def subscribe(self, channel: str, handler: Handler):
        """
        订阅频道 — 启动后台监听任务。

        每个 Worker 进程都会启动自己的监听器，
        Redis pub/sub 会将消息广播给所有订阅者。

        Args:
            channel: 频道名
            handler: 异步处理函数 async def handler(event: dict) -> None
        """
        redis = get_redis()
        if redis is None:
            logger.warning(f"[EventBus] Redis 不可用, 跳过订阅 {channel}")
            return

        self._channels[channel] = handler
        task = asyncio.create_task(self._listener(channel, handler))
        self._tasks.append(task)
        logger.info(f"[EventBus] 已订阅频道: {channel}")

    async def _listener(self, channel: str, handler: Handler):
        """
        Redis pubsub 监听循环 — 运行在后台 Task 中。

        自愈机制: Redis 瞬断时自动重连，指数退避 (2→4→8→16s, 上限 30s)。
        仅响应 asyncio.CancelledError 退出。
        """
        backoff = 2  # 初始退避秒数

        while True:
            redis = get_redis()
            if redis is None:
                logger.warning(
                    f"[EventBus] Redis 不可用, {backoff}s 后重试 channel={channel}"
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue

            pubsub = redis.pubsub()
            try:
                await pubsub.subscribe(channel)
                logger.info(f"[EventBus] 监听器启动: {channel}")
                backoff = 2  # 连接成功, 重置退避

                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue

                    try:
                        event = json.loads(message["data"])
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.error(
                            f"[EventBus] JSON 解析失败 channel={channel}: {e}"
                        )
                        continue

                    # 沙箱执行 — 处理器异常不外泄
                    await self._safe_execute(handler, event)

            except asyncio.CancelledError:
                logger.info(f"[EventBus] 监听任务被取消: {channel}")
                raise
            except Exception as e:
                logger.error(
                    f"[EventBus] 监听异常 channel={channel}: {e} — "
                    f"{backoff}s 后重连",
                    exc_info=True,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)  # 指数退避, 上限 30s
            finally:
                try:
                    await pubsub.unsubscribe(channel)
                    await pubsub.aclose()
                except Exception:
                    pass

    async def _safe_execute(self, handler: Handler, event: Dict[str, Any]):
        """沙箱执行 — 任何异常都被捕获，不影响监听循环"""
        try:
            await handler(event)
        except Exception as e:
            logger.error(
                f"[EventBus] 处理器异常 handler={handler.__name__}: {e}",
                exc_info=True,
            )

    # ═══════════════════════════════════════════════════════════════
    #  生命周期管理
    # ═══════════════════════════════════════════════════════════════

    async def shutdown(self):
        """关闭所有监听任务 — 在 app.py lifespan shutdown 中调用"""
        if not self._tasks:
            return

        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._channels.clear()
        logger.info(f"[EventBus] 所有监听任务已关闭")

    def is_active(self) -> bool:
        """事件总线是否处于活跃状态"""
        return get_redis() is not None and bool(self._tasks)
