"""Clock-scoped monotonic snapshots. Internal ticks are integer nanoseconds."""
from __future__ import annotations

from dataclasses import dataclass


class ClockDomainMismatch(ValueError):
    """Raised when arithmetic would mix unrelated clock domains."""


@dataclass(frozen=True, slots=True)
class MonotonicInstant:
    """An immutable reading, not a wall-clock timestamp or a deadline policy."""

    clock_id: str
    tick_ns: int

    def __post_init__(self) -> None:
        if not isinstance(self.clock_id, str):
            raise TypeError('clock_id must be a string')
        if not self.clock_id or self.clock_id.isspace():
            raise ValueError('clock_id must not be empty or whitespace')
        if type(self.tick_ns) is not int:
            raise TypeError('tick_ns must be an integer, not bool or float')
        if self.tick_ns < 0:
            raise ValueError('tick_ns must not be negative')

    def elapsed_ns_since(self, earlier: MonotonicInstant) -> int:
        """Return an explicit nonnegative interval within the same clock only."""
        if not isinstance(earlier, MonotonicInstant):
            raise TypeError('earlier must be a MonotonicInstant')
        if self.clock_id != earlier.clock_id:
            raise ClockDomainMismatch('cannot subtract readings from different clock_id values')
        elapsed = self.tick_ns - earlier.tick_ns
        if elapsed < 0:
            raise ValueError('earlier reading is in the future; clock regression or ordering error')
        return elapsed
