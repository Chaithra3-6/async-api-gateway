"""End-to-end test of the gateway.

Upstream HTTP calls are mocked with respx. Redis and MongoDB are real services
(provided by docker-compose locally or by GitHub Actions in CI). Run just these
with:  pytest -m integration

The ASGI app is driven in-process via httpx ASGITransport, with lifespan managed
by asgi-lifespan so startup/shutdown (client setup/teardown) actually runs.
"""

import httpx
import pytest
import respx
from asgi_lifespan import LifespanManager

from app.config import settings
from app.main import app

pytestmark = pytest.mark.integration


async def _client():
    manager = LifespanManager(app)
    await manager.__aenter__()
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return manager, client


async def _token(client):
    resp = await client.post(
        "/auth/token",
        json={"username": settings.demo_username, "password": settings.demo_password},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _mock_all_upstreams_ok():
    respx.get(url__regex=r".*/users/.*").mock(
        return_value=httpx.Response(200, json={"id": "42", "name": "User 42"})
    )
    respx.get(url__regex=r".*/orders/.*").mock(
        return_value=httpx.Response(200, json={"orders": []})
    )
    respx.get(url__regex=r".*/recommendations/.*").mock(
        return_value=httpx.Response(200, json={"items": ["p-1"]})
    )


@pytest.mark.asyncio
async def test_requires_auth():
    manager, client = await _client()
    try:
        resp = await client.get("/api/v1/profile/42")
        assert resp.status_code == 403  # no Authorization header -> HTTPBearer rejects
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


@pytest.mark.asyncio
@respx.mock
async def test_aggregates_three_upstreams():
    _mock_all_upstreams_ok()
    manager, client = await _client()
    try:
        token = await _token(client)
        resp = await client.get(
            "/api/v1/profile/42", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["user"]["available"] is True
        assert body["orders"]["available"] is True
        assert body["recommendations"]["available"] is True
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


@pytest.mark.asyncio
@respx.mock
async def test_graceful_degradation_when_one_upstream_fails():
    respx.get(url__regex=r".*/users/.*").mock(
        return_value=httpx.Response(200, json={"id": "7"})
    )
    respx.get(url__regex=r".*/orders/.*").mock(return_value=httpx.Response(500))
    respx.get(url__regex=r".*/recommendations/.*").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    manager, client = await _client()
    try:
        token = await _token(client)
        # use a fresh user id so we don't read a cached full response
        resp = await client.get(
            "/api/v1/profile/7", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["user"]["available"] is True
        assert body["orders"]["available"] is False  # degraded, not fatal
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_health_is_liveness_only():
    manager, client = await _client()
    try:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)
