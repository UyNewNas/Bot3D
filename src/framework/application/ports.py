"""Plain-data ports for time, observations and transactional command history."""
from __future__ import annotations

from typing import Protocol

from framework.domain.discovery import BackendDescription, BackendState
from framework.domain.commands import CommandKey
from framework.domain.journal import (
    AcceptanceWrite, CommandAcceptance, CommandRecord, JournalEntry, JournalRetention,
)
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


class JournalPort(Protocol):
    """Trusted internal storage port; callers authorize resource access first.

    A recorded candidate is not public ACCEPTED or permission to execute. Every
    write confirmation returns to the coordinator for current checks. A storage
    exception must never become 'missing, safe to submit again'; STOP must use
    its independent path. The retention descriptor states this adapter's scope.
    """

    @property
    def retention(self) -> JournalRetention:
        ...

    def lookup(self, key: CommandKey) -> CommandRecord | None:
        ...

    def record_acceptance(self, acceptance: CommandAcceptance) -> AcceptanceWrite:
        ...

    def append(self, key: CommandKey, entry: JournalEntry, *, expected_revision: int) -> CommandRecord:
        ...
