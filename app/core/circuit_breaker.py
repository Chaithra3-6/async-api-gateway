"""A small circuit breaker.

Idea in one line: after an upstream service fails too many times in a row, stop
calling it for a while so we fail fast instead of piling up slow, doomed calls.

Three states:
    CLOSED     -> normal. Calls go through. We count consecutive failures.
    OPEN       -> tripped. We reject calls immediately for `recovery_timeout`
                  seconds, then move to HALF_OPEN to test the water.
    HALF_OPEN  -> we allow ONE trial call. Success -> CLOSED. Failure -> OPEN.

The clock is injectable (`time_func`) so tests can control time instead of
sleeping. Default is a monotonic clock, which never goes backwards.
"""

from __future__ import annotations

import time
from enum import Enum


class State(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when the breaker is OPEN and rejects a call without trying it."""

    def __init__(self, name: str) -> None:
        super().__init__(f"circuit '{name}' is open")
        self.name = name


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        time_func=time.monotonic,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._now = time_func

        self.state = State.CLOSED
        self._consecutive_failures = 0
        self._opened_at = 0.0

    def before_request(self) -> None:
        """Call this right before making the upstream request.

        Raises CircuitOpenError if the breaker is OPEN and the cooldown has not
        elapsed. Otherwise returns (and may flip OPEN -> HALF_OPEN).
        """
        if self.state is State.OPEN:
            if self._now() - self._opened_at >= self.recovery_timeout:
                # Cooldown is over: allow a single trial call.
                self.state = State.HALF_OPEN
            else:
                raise CircuitOpenError(self.name)
        # CLOSED and HALF_OPEN both proceed.

    def on_success(self) -> None:
        """Call after a successful request."""
        self._consecutive_failures = 0
        self.state = State.CLOSED

    def on_failure(self) -> None:
        """Call after a failed request."""
        if self.state is State.HALF_OPEN:
            # The trial call failed: go straight back to OPEN.
            self._trip()
            return

        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._trip()

    def _trip(self) -> None:
        self.state = State.OPEN
        self._opened_at = self._now()
