"""Retry with exponential backoff.

Idea in one line: if a call fails, wait a bit and try again, doubling the wait
each time so we don't hammer a struggling service.

Wait before attempt n (1-indexed) = min(max_delay, base_delay * 2**(n-1)),
plus a little random "jitter" so many clients don't all retry in lockstep.

`sleep` is injectable so tests run instantly instead of actually waiting.
"""

from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


async def retry_async(
    func: Callable[[], Awaitable[T]],
    *,
    retries: int = 3,
    base_delay: float = 0.2,
    max_delay: float = 2.0,
    jitter: bool = True,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rng: random.Random | None = None,
) -> T:
    """Call `func` up to (retries + 1) times, backing off between attempts.

    Re-raises the last exception if every attempt fails. Only exceptions listed
    in `retry_on` are retried; anything else propagates immediately.
    """
    _rng = rng or random.Random()
    attempt = 0
    while True:
        try:
            return await func()
        except retry_on as exc:
            attempt += 1
            if attempt > retries:
                raise exc
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            if jitter:
                delay += _rng.uniform(0, base_delay)
            await sleep(delay)
