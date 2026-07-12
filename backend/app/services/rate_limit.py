"""Redis-backed fixed-window limits with a local development fallback."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict

from fastapi import HTTPException, status
from redis.asyncio import Redis

from app.core.config import settings

_redis: Redis | None = None
_local: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))
_lock = asyncio.Lock()


def _client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def enforce_limit(key: str, *, limit: int, window_seconds: int) -> None:
    if settings.ENVIRONMENT == "test" or limit <= 0:
        return
    redis_key = f"limit:{key}"
    try:
        client = _client()
        count = await client.incr(redis_key)
        if count == 1:
            await client.expire(redis_key, window_seconds)
        ttl = max(await client.ttl(redis_key), 1)
    except Exception:
        async with _lock:
            now = time.monotonic()
            count, expires = _local[redis_key]
            if expires <= now:
                count, expires = 0, now + window_seconds
            count += 1
            _local[redis_key] = (count, expires)
            ttl = max(int(expires - now), 1)

    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много запросов. Повторите позже.",
            headers={"Retry-After": str(ttl)},
        )


async def enforce_ai_limits(*, user_id: str, organization_id: str) -> None:
    await enforce_limit(
        f"ai:user:{user_id}:minute",
        limit=settings.AI_REQUESTS_PER_MINUTE,
        window_seconds=60,
    )
    await enforce_limit(
        f"ai:org:{organization_id}:day",
        limit=settings.AI_DAILY_REQUESTS_PER_ORG,
        window_seconds=24 * 60 * 60,
    )
