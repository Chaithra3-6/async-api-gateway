"""Fixed-window rate limiting.

Idea in one line: allow at most `limit` requests per client per `window_seconds`;
once the window rolls over, the count resets.

Two backends behind the same tiny interface:
    InMemoryRateLimiter -> pure Python, used in tests and as a fallback.
    RedisRateLimiter    -> shared across processes, used in production.

The window number is floor(now / window_seconds), so all requests in the same
window share one counter key.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int


class InMemoryRateLimiter:
    def __init__(self, limit: int, window_seconds: int, time_func=time.time) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._now = time_func
        self._counters: dict[str, int] = {}

    async def check(self, client_id: str) -> RateLimitResult:
        window = int(self._now() // self.window_seconds)
        key = f"{client_id}:{window}"
        count = self._counters.get(key, 0) + 1
        self._counters[key] = count
        remaining = max(0, self.limit - count)
        return RateLimitResult(allowed=count <= self.limit, remaining=remaining)


class RedisRateLimiter:
    """Same interface, backed by Redis so the limit is shared across instances.

    Uses INCR to bump the window counter and sets EXPIRE on first hit so old
    windows clean themselves up.
    """

    def __init__(self, redis, limit: int, window_seconds: int) -> None:
        self._redis = redis
        self.limit = limit
        self.window_seconds = window_seconds

    async def check(self, client_id: str) -> RateLimitResult:
        window = int(time.time() // self.window_seconds)
        key = f"ratelimit:{client_id}:{window}"
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, self.window_seconds)
        remaining = max(0, self.limit - count)
        return RateLimitResult(allowed=count <= self.limit, remaining=remaining)
