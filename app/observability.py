"""Logging, correlation IDs, and metrics.

- Structured JSON logs, so log aggregators can parse fields instead of regex.
- A correlation ID per request (from the X-Request-ID header or generated),
  stored in a contextvar so every log line for that request carries it.
- A tiny in-process metrics registry rendered in Prometheus text format at
  /metrics. Kept dependency-free and easy to explain.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# holds the current request's correlation id; "-" when outside a request
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id.get(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = correlation_id.set(cid)
        try:
            response = await call_next(request)
        finally:
            correlation_id.reset(token)
        response.headers["X-Request-ID"] = cid
        return response


class Metrics:
    """Minimal counter registry. Not thread-shared state to worry about here
    because a single asyncio event loop runs the handlers cooperatively."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def inc(self, name: str, amount: int = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + amount

    def render(self) -> str:
        lines = []
        for name, value in sorted(self._counters.items()):
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {value}")
        return "\n".join(lines) + "\n"


metrics = Metrics()
