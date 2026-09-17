from app.core.circuit_breaker import CircuitBreaker, CircuitOpenError, State


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, secs):
        self.t += secs


def test_opens_after_threshold_failures():
    cb = CircuitBreaker("s", failure_threshold=3, recovery_timeout=30, time_func=Clock())
    for _ in range(3):
        cb.before_request()
        cb.on_failure()
    assert cb.state is State.OPEN


def test_open_circuit_rejects_immediately():
    clock = Clock()
    cb = CircuitBreaker("s", failure_threshold=1, recovery_timeout=30, time_func=clock)
    cb.before_request()
    cb.on_failure()
    try:
        cb.before_request()
        assert False, "expected CircuitOpenError"
    except CircuitOpenError:
        pass


def test_half_open_after_cooldown_then_recovers():
    clock = Clock()
    cb = CircuitBreaker("s", failure_threshold=1, recovery_timeout=30, time_func=clock)
    cb.before_request()
    cb.on_failure()
    clock.advance(30)
    cb.before_request()
    assert cb.state is State.HALF_OPEN
    cb.on_success()
    assert cb.state is State.CLOSED


def test_half_open_failure_reopens():
    clock = Clock()
    cb = CircuitBreaker("s", failure_threshold=1, recovery_timeout=30, time_func=clock)
    cb.before_request()
    cb.on_failure()
    clock.advance(30)
    cb.before_request()
    cb.on_failure()
    assert cb.state is State.OPEN


def test_success_resets_failure_count():
    cb = CircuitBreaker("s", failure_threshold=3, recovery_timeout=5, time_func=Clock())
    cb.before_request(); cb.on_failure()
    cb.before_request(); cb.on_failure()
    cb.before_request(); cb.on_success()
    cb.before_request(); cb.on_failure()
    cb.before_request(); cb.on_failure()
    assert cb.state is State.CLOSED
