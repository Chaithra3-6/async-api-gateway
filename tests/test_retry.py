import pytest

from app.core.retry import retry_async


@pytest.mark.asyncio
async def test_succeeds_after_transient_failures():
    delays = []

    async def fake_sleep(d):
        delays.append(d)

    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("boom")
        return "ok"

    result = await retry_async(
        flaky, retries=3, base_delay=0.2, jitter=False, sleep=fake_sleep
    )
    assert result == "ok"
    assert calls["n"] == 3
    assert delays == [0.2, 0.4]


@pytest.mark.asyncio
async def test_gives_up_and_reraises():
    async def fake_sleep(_):
        return None

    attempts = {"n": 0}

    async def always_fail():
        attempts["n"] += 1
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        await retry_async(always_fail, retries=2, jitter=False, sleep=fake_sleep)
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_only_retries_listed_exceptions():
    async def fake_sleep(_):
        return None

    calls = {"n": 0}

    async def type_error():
        calls["n"] += 1
        raise TypeError("not retried")

    with pytest.raises(TypeError):
        await retry_async(
            type_error, retries=5, retry_on=(ValueError,), jitter=False, sleep=fake_sleep
        )
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_backoff_capped_at_max_delay():
    delays = []

    async def fake_sleep(d):
        delays.append(d)

    async def fail():
        raise ValueError("x")

    with pytest.raises(ValueError):
        await retry_async(
            fail, retries=5, base_delay=1.0, max_delay=3.0, jitter=False, sleep=fake_sleep
        )
    assert delays == [1.0, 2.0, 3.0, 3.0, 3.0]
