"""Real monotonic source and an explicitly injected deterministic test clock."""
from __future__ import annotations

from time import monotonic_ns
from uuid import uuid4

from framework.domain.time import MonotonicInstant


class SystemMonotonicClock:
    """One OS monotonic source with a fresh identity per runtime clock object.

    Construct once in a runtime's composition root and share it. The origin is
    intentionally unspecified; neither readings nor identity survive a restart.
    This is not a device clock, simulation clock or hard-real-time guarantee.
    """

    def __init__(self) -> None:
        self._clock_id = uuid4().hex

    def now(self) -> MonotonicInstant:
        return MonotonicInstant(self._clock_id, monotonic_ns())


class ManualMonotonicClock:
    """Single-owner test double; NEVER use as a live protection clock.

    Time changes only by explicit nonnegative integer increments. There are no
    callbacks, sleeps or scheduler. This fake provides no thread-safety claim.
    """

    def __init__(self, *, clock_id: str, start_ns: int = 0) -> None:
        self._instant = MonotonicInstant(clock_id, start_ns)

    def now(self) -> MonotonicInstant:
        return self._instant

    def advance_ns(self, delta_ns: int) -> MonotonicInstant:
        if type(delta_ns) is not int:
            raise TypeError('delta_ns must be an integer, not bool or float')
        if delta_ns < 0:
            raise ValueError('a monotonic clock cannot move backwards')
        updated = MonotonicInstant(self._instant.clock_id, self._instant.tick_ns + delta_ns)
        self._instant = updated
        return updated
