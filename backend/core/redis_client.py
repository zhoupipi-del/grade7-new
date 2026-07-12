"""
core/redis_client.py - Redis 异步客户端单例

跨进程分布式事件总线底座。4 Workers 下内存总线会丢失 75% 事件，
通过 Redis pub/sub 实现跨 Worker 通信。

DB 分配:
  DB 0 - 旧 Flask
  DB 1 - 事件总线 (本模块使用)
  DB 2 - Celery broker
  DB 3 - Celery result_backend

初始化模式参照 PolicyEngine: init_redis() / get_redis() / close_redis()
"""

import os
import logging
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
#  单例存储
# ═══════════════════════════════════════════════════════════════

_redis_client: Optional[aioredis.Redis] = None


def get_redis() -> Optional[aioredis.Redis]:
    """获取全局 Redis 客户端实例 (可能为 None — 降级模式)"""
    return _redis_client


def set_redis(client: aioredis.Redis):
    """注入 Redis 客户端实例"""
    global _redis_client
    _redis_client = client


# ═══════════════════════════════════════════════════════════════
#  生命周期管理
# ═══════════════════════════════════════════════════════════════

async def init_redis() -> aioredis.Redis:
    """
    初始化 Redis 异步客户端 — 在 app.py lifespan 中调用。

    环境变量:
      REDIS_HOST     默认 127.0.0.1
      REDIS_PORT     默认 6379
      REDIS_PASSWORD 默认空 (无密码)
      REDIS_EVENT_DB 默认 1 (事件总线专用 DB)

    Returns:
        aioredis.Redis 实例 (已存入全局单例)
    """
    global _redis_client

    host = os.getenv("REDIS_HOST", "127.0.0.1")
    port = int(os.getenv("REDIS_PORT", "6379"))
    password = os.getenv("REDIS_PASSWORD", "")
    db = int(os.getenv("REDIS_EVENT_DB", "1"))

    # 构建连接 URL
    auth_part = f":{password}@" if password else ""
    url = f"redis://{auth_part}{host}:{port}/{db}"

    client = aioredis.from_url(
        url,
        decode_responses=True,      # 自动解码为 str (pub/sub 消息体为 JSON 字符串)
        max_connections=30,   # 4 频道 pubsub 独占 + 常规缓存读写
        socket_keepalive=True,
        socket_connect_timeout=5,
        retry_on_timeout=True,
    )

    # 连通性测试
    await client.ping()
    _redis_client = client

    logger.info(
        f"Redis 客户端已初始化: {host}:{port}/{db} "
        f"(auth={'on' if password else 'off'})"
    )
    return client


async def close_redis():
    """关闭 Redis 连接 — 在 app.py lifespan shutdown 中调用"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis 连接已释放")
