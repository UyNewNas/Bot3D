"""Read ports for monotonic time and robot observations."""
from __future__ import annotations

from typing import Protocol

from framework.domain.discovery import BackendDescription, BackendState
from framework.domain.time import MonotonicInstant


class MonotonicClock(Protocol):
    """A quick, nonblocking read from one explicit monotonic clock domain."""

    def now(self) -> MonotonicInstant:
        """Return ordinary domain data, never SDK, HTTP or ORM objects."""
        ...


class ReadOnlyBackend(Protocol):
    """Two reads returning ordinary domain values for one backend identity."""

    def describe(self) -> BackendDescription:
        ...

    def read_state(self) -> BackendState:
        ...
