"""Only the clock port needed by the current engineering slice is defined."""
from __future__ import annotations

from typing import Protocol

from framework.domain.time import MonotonicInstant


class MonotonicClock(Protocol):
    """A quick, nonblocking read from one explicit monotonic clock domain."""

    def now(self) -> MonotonicInstant:
        """Return ordinary domain data, never SDK, HTTP or ORM objects."""
        ...
