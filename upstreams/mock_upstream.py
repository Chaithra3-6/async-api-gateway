"""A tiny stand-in for the three real backend services.

Run this locally (or in docker-compose) so the gateway has something to
aggregate without needing real services. In production you'd point the gateway's
*_SERVICE_URL settings at the real endpoints instead.

Start: uvicorn upstreams.mock_upstream:app --port 9001
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Mock Upstream")


@app.get("/users/{user_id}")
async def user(user_id: str):
    return {"id": user_id, "name": f"User {user_id}", "tier": "gold"}


@app.get("/orders/{user_id}")
async def orders(user_id: str):
    return {"user_id": user_id, "orders": [{"id": "o-1", "total": 42.0}]}


@app.get("/recommendations/{user_id}")
async def recommendations(user_id: str):
    return {"user_id": user_id, "items": ["p-10", "p-22", "p-31"]}
