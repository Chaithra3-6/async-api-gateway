"""FastAPI gateway wiring everything together.

Endpoints:
    POST /auth/token                 -> exchange demo credentials for a JWT
    GET  /api/v1/profile/{user_id}   -> aggregated profile (JWT + rate limited)
    GET  /health                     -> liveness (is the process up?)
    GET  /ready                      -> readiness (are Redis and Mongo reachable?)
    GET  /metrics                    -> Prometheus-format counters
"""

from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.aggregator import aggregate_profile
from app.clients import make_http_client, make_mongo, make_redis
from app.config import settings
from app.core.rate_limit import RedisRateLimiter
from app.core.security import (
    create_access_token,
    decode_access_token,
    TokenError,
)
from app.observability import (
    CorrelationIdMiddleware,
    configure_logging,
    correlation_id,
    metrics,
)

log = logging.getLogger("gateway")
bearer = HTTPBearer(auto_error=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    app.state.redis = make_redis()
    app.state.mongo = make_mongo()
    app.state.http = make_http_client()
    app.state.rate_limiter = RedisRateLimiter(
        app.state.redis,
        limit=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
    log.info("gateway started")
    try:
        yield
    finally:
        await app.state.http.aclose()
        await app.state.redis.aclose()
        app.state.mongo.close()
        log.info("gateway stopped")


app = FastAPI(title="Async Aggregation Gateway", version="1.0.0", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)


# ---------- auth ----------
def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    try:
        payload = decode_access_token(
            creds.credentials,
            secret=settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))
    return payload["sub"]


@app.post("/auth/token")
async def issue_token(body: dict):
    username = body.get("username", "")
    password = body.get("password", "")
    # constant-time comparison to avoid leaking validity via timing
    ok = secrets.compare_digest(username, settings.demo_username) and (
        secrets.compare_digest(password, settings.demo_password)
    )
    if not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    token = create_access_token(
        username,
        secret=settings.jwt_secret,
        expires_minutes=settings.access_token_expire_minutes,
        algorithm=settings.jwt_algorithm,
    )
    return {"access_token": token, "token_type": "bearer"}


# ---------- main aggregation endpoint ----------
@app.get("/api/v1/profile/{user_id}")
async def get_profile(user_id: str, request: Request, user: str = Depends(current_user)):
    # rate limit per authenticated user
    limit = await request.app.state.rate_limiter.check(user)
    if not limit.allowed:
        metrics.inc("rate_limited_total")
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate limit exceeded",
            headers={"Retry-After": str(settings.rate_limit_window_seconds)},
        )

    metrics.inc("profile_requests_total")
    result = await aggregate_profile(
        user_id, request.app.state.http, request.app.state.redis
    )

    # append-only audit log in MongoDB (fire the write, don't block the response on failures)
    try:
        await request.app.state.mongo[settings.mongo_db]["request_log"].insert_one(
            {
                "user_id": user_id,
                "requested_by": user,
                "correlation_id": correlation_id.get(),
                "cached": result["cached"],
                "at": datetime.now(timezone.utc),
            }
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("audit log write failed: %s", exc)

    return result


# ---------- operational endpoints ----------
@app.get("/health")
async def health():
    # liveness: the process is running and can answer. No dependencies checked.
    return {"status": "ok"}


@app.get("/ready")
async def ready(request: Request):
    # readiness: only report ready if the things we depend on are reachable.
    checks = {"redis": False, "mongo": False}
    try:
        await request.app.state.redis.ping()
        checks["redis"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        await request.app.state.mongo.admin.command("ping")
        checks["mongo"] = True
    except Exception:  # noqa: BLE001
        pass

    if all(checks.values()):
        return {"status": "ready", "checks": checks}
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {"status": "not_ready", "checks": checks})


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint():
    return metrics.render()
