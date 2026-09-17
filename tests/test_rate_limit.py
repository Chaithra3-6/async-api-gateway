import pytest

from app.core.rate_limit import InMemoryRateLimiter


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, secs):
        self.t += secs


@pytest.mark.asyncio
async def test_allows_up_to_limit_then_blocks():
    rl = InMemoryRateLimiter(limit=3, window_seconds=60, time_func=Clock())
    assert (await rl.check("a")).allowed
    assert (await rl.check("a")).allowed
    assert (await rl.check("a")).allowed
    assert not (await rl.check("a")).allowed


@pytest.mark.asyncio
async def test_remaining_counts_down():
    rl = InMemoryRateLimiter(limit=3, window_seconds=60, time_func=Clock())
    assert (await rl.check("a")).remaining == 2
    assert (await rl.check("a")).remaining == 1
    assert (await rl.check("a")).remaining == 0


@pytest.mark.asyncio
async def test_clients_are_independent():
    rl = InMemoryRateLimiter(limit=1, window_seconds=60, time_func=Clock())
    assert (await rl.check("a")).allowed
    assert (await rl.check("b")).allowed


@pytest.mark.asyncio
async def test_window_rollover_resets():
    clock = Clock()
    rl = InMemoryRateLimiter(limit=1, window_seconds=60, time_func=clock)
    assert (await rl.check("a")).allowed
    assert not (await rl.check("a")).allowed
    clock.advance(60)
    assert (await rl.check("a")).allowed
