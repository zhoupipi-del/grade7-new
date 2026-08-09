"""
core/ratelimit.py — 基于 Redis 的按 (用户 + 学校) 滑动窗口限流。

保护高成本端点（AI 德育处方），防止单用户 / 单校刷爆 LLM 配额。
Redis 不可用时 fail-open（放行），与登录锁定降级策略一致。
"""

from __future__ import annotations

import logging
import os
import time

from fastapi import Depends, HTTPException, Request, status

from core.redis_client import get_redis
from core.routers import get_current_user

logger = logging.getLogger(__name__)

# 默认每校每用户每小时最多 20 次 AI 处方调用；可通过环境变量覆盖。
AI_COST_MAX_PER_WINDOW = int(os.getenv("AI_COST_MAX_PER_HOUR", "20"))
AI_COST_WINDOW_SECONDS = int(os.getenv("AI_COST_WINDOW_SECONDS", "3600"))


async def ai_prescription_rate_limit(
    request: Request,
    current_user=Depends(get_current_user),
):
    """
    AI 处方端点依赖：按 (school_id, user_id) 计数限流。

    超限返回 429；Redis 不可用时放行（fail-open）。
    """
    redis = get_redis()
    if redis is None:
        return  # Redis 降级时不阻断业务

    user_id = getattr(current_user, "id", None)
    school_id = getattr(current_user, "school_id", None)
    if user_id is None or school_id is None:
        return

    key = f"ai_cost_limit:{school_id}:{user_id}"
    now = time.time()
    try:
        async with redis.pipeline(transaction=False) as pipe:
            pipe.zremrangebyscore(key, 0, now - AI_COST_WINDOW_SECONDS)
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, AI_COST_WINDOW_SECONDS)
            pipe.zcard(key)
            results = await pipe.execute()
        count = results[3]
        if count > AI_COST_MAX_PER_WINDOW:
            # 回滚本次计入，避免误吞配额
            await redis.zrem(key, str(now))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"AI 调用频率超限（每校每用户每小时最多 {AI_COST_MAX_PER_WINDOW} 次），"
                    "请稍后再试。"
                ),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("AI 限流检查异常，fail-open: %s", e)
