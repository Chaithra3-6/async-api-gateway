"""Shared clients: Redis, MongoDB (motor), and a pooled httpx client.

These are created once at startup and reused, which is both faster (connection
pooling) and correct (one place owns the connections). The gateway holds them on
`app.state` and the lifespan handler opens/closes them.
"""

from __future__ import annotations

import httpx
import redis.asyncio as aioredis
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings


def make_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


def make_mongo() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(settings.mongo_url)


def make_http_client() -> httpx.AsyncClient:
    # a single pooled client for all upstream calls
    return httpx.AsyncClient(timeout=settings.upstream_timeout_seconds)
