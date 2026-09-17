"""The heart of the gateway: fetch three upstream services concurrently, each
call protected by retry + circuit breaker, then merge into one response.

If an upstream is unavailable (circuit open, or still failing after retries) we
don't fail the whole request — we return that section as unavailable and serve
the rest. This is "graceful degradation".

The merged result is cached in Redis for a short TTL so repeat requests are cheap.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx

from app.config import settings
from app.core.circuit_breaker import CircuitBreaker, CircuitOpenError
from app.core.retry import retry_async
from app.observability import metrics

log = logging.getLogger("aggregator")

# one breaker per upstream, created at import and reused
breakers: dict[str, CircuitBreaker] = {
    name: CircuitBreaker(
        name,
        failure_threshold=settings.circuit_failure_threshold,
        recovery_timeout=settings.circuit_recovery_timeout,
    )
    for name in ("user", "orders", "recommendations")
}


async def _fetch_one(
    name: str,
    url: str,
    http_client: httpx.AsyncClient,
) -> dict:
    """Fetch a single upstream with retry + circuit breaker.

    Returns the parsed JSON on success, or a degraded marker on failure so the
    caller can still assemble a partial response.
    """
    breaker = breakers[name]

    async def _do_request() -> dict:
        breaker.before_request()  # raises CircuitOpenError if the breaker is open
        try:
            resp = await http_client.get(url)
            resp.raise_for_status()
        except Exception:
            breaker.on_failure()
            raise
        breaker.on_success()
        return resp.json()

    try:
        data = await retry_async(
            _do_request,
            retries=settings.retry_attempts,
            base_delay=settings.retry_base_delay,
            # don't waste retries on an open circuit
            retry_on=(httpx.HTTPError,),
        )
        metrics.inc("upstream_success_total")
        return {"available": True, "data": data}
    except CircuitOpenError:
        metrics.inc("upstream_circuit_open_total")
        log.warning("upstream %s skipped: circuit open", name)
        return {"available": False, "reason": "circuit_open"}
    except Exception as exc:  # noqa: BLE001 - degrade gracefully on any upstream error
        metrics.inc("upstream_failure_total")
        log.warning("upstream %s failed: %s", name, exc)
        return {"available": False, "reason": "upstream_error"}


async def aggregate_profile(
    user_id: str,
    http_client: httpx.AsyncClient,
    redis,
) -> dict:
    """Return a merged profile for `user_id`, using cache when available."""
    cache_key = f"profile:{user_id}"

    cached = await redis.get(cache_key)
    if cached is not None:
        metrics.inc("cache_hit_total")
        result = json.loads(cached)
        result["cached"] = True
        return result
    metrics.inc("cache_miss_total")

    # fire all three upstream calls at once and wait for all to settle
    user, orders, recs = await asyncio.gather(
        _fetch_one("user", f"{settings.user_service_url}/users/{user_id}", http_client),
        _fetch_one("orders", f"{settings.orders_service_url}/orders/{user_id}", http_client),
        _fetch_one(
            "recommendations",
            f"{settings.recommendations_service_url}/recommendations/{user_id}",
            http_client,
        ),
    )

    result = {
        "user_id": user_id,
        "user": user,
        "orders": orders,
        "recommendations": recs,
        "cached": False,
    }

    # only cache a fully-successful response, so we don't cache degraded data
    if all(part["available"] for part in (user, orders, recs)):
        await redis.set(cache_key, json.dumps(result), ex=settings.cache_ttl_seconds)

    return result
