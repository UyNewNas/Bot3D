"""Immutable command history and its local causal invariants, not motion authority."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .capabilities import _validate_token
from .commands import CommandKey, PoseCommand, _count, _require, execution_digest
from .discovery import BackendIdentity
from .time import MonotonicInstant

__all__ = [
    'CommandState', 'ResultCertainty', 'WriteOutcome', 'RetentionScope', 'JournalRetention',
    'CommandAcceptance', 'CommandEvent', 'DispatchIntent', 'BackendReceipt', 'ReconciliationFact',
    'JournalEntry', 'CommandRecord', 'AcceptanceWrite', 'JournalError', 'IdempotencyConflict',
    'JournalRevisionConflict', 'JournalEntryConflict', 'JournalOrderError',
    'JournalRecordNotFound', 'JournalUnavailable',
]


class CommandState(StrEnum):
    REJECTED = 'REJECTED'
    ACCEPTED = 'ACCEPTED'
    PLANNING = 'PLANNING'
    DISPATCHING = 'DISPATCHING'
    EXECUTING = 'EXECUTING'
    CANCEL_REQUESTED = 'CANCEL_REQUESTED'
    SUCCEEDED = 'SUCCEEDED'
    CANCELLED = 'CANCELLED'
    FAILED = 'FAILED'
    TIMED_OUT = 'TIMED_OUT'
    INTERRUPTED = 'INTERRUPTED'


class ResultCertainty(StrEnum):
    PENDING = 'PENDING'
    CONFIRMED = 'CONFIRMED'
    UNKNOWN = 'UNKNOWN'


class WriteOutcome(StrEnum):
    NOT_COMMITTED = 'NOT_COMMITTED'
    UNKNOWN = 'UNKNOWN'


class RetentionScope(StrEnum):
    INSTANCE_LIFETIME = 'INSTANCE_LIFETIME'
    TIME_WINDOW = 'TIME_WINDOW'


class JournalError(RuntimeError):
    """An explicit journal failure; never an instruction to retry execution."""


class IdempotencyConflict(JournalError):
    code = 'IDEMPOTENCY_CONFLICT'


class JournalRevisionConflict(JournalError):
    code = 'JOURNAL_REVISION_CONFLICT'


class JournalEntryConflict(JournalError):
    code = 'JOURNAL_ENTRY_CONFLICT'


class JournalOrderError(JournalError):
    code = 'JOURNAL_ORDER_ERROR'


class JournalRecordNotFound(JournalError):
    code = 'JOURNAL_RECORD_NOT_FOUND'


class JournalUnavailable(JournalError):
    code = 'JOURNAL_UNAVAILABLE'

    def __init__(self, operation: str, write_outcome: WriteOutcome | None) -> None:
        self.operation = operation
        self.write_outcome = write_outcome
        super().__init__(f'journal unavailable during {operation}; do not advance execution')


_TERMINAL = frozenset({
    CommandState.REJECTED, CommandState.SUCCEEDED, CommandState.CANCELLED,
    CommandState.FAILED, CommandState.TIMED_OUT, CommandState.INTERRUPTED,
})
_UNCERTAIN_TERMINAL = frozenset({CommandState.FAILED, CommandState.TIMED_OUT, CommandState.INTERRUPTED})
_EARLY_END = frozenset({CommandState.CANCELLED, CommandState.FAILED,
                       CommandState.TIMED_OUT, CommandState.INTERRUPTED})
_NEXT = {
    None: _EARLY_END | {CommandState.ACCEPTED, CommandState.REJECTED},
    CommandState.ACCEPTED: _EARLY_END | {CommandState.PLANNING},
    CommandState.PLANNING: _EARLY_END | {CommandState.PLANNING, CommandState.DISPATCHING},
    CommandState.DISPATCHING: _EARLY_END | {
        CommandState.DISPATCHING, CommandState.EXECUTING, CommandState.CANCEL_REQUESTED,
    },
    CommandState.EXECUTING: (_EARLY_END - {CommandState.CANCELLED}) | {
        CommandState.EXECUTING, CommandState.CANCEL_REQUESTED, CommandState.SUCCEEDED,
    },
    CommandState.CANCEL_REQUESTED: _EARLY_END | {CommandState.CANCEL_REQUESTED},
}


def _text(value: str, name: str) -> None:
    _require(value, str, name)
    if not value.strip():
        raise ValueError(f'{name} must contain non-whitespace text')


def _instant(value: MonotonicInstant) -> None:
    _require(value, MonotonicInstant, 'recorded_at')
    _validate_token(value.clock_id, 'recorded_at.clock_id')


@dataclass(frozen=True, slots=True)
class JournalRetention:
    scope: RetentionScope
    window_ns: int | None
    durable: bool

    def __post_init__(self) -> None:
        _require(self.scope, RetentionScope, 'scope')
        _require(self.durable, bool, 'durable')
        if self.scope is RetentionScope.INSTANCE_LIFETIME:
            if self.window_ns is not None:
                raise ValueError('instance retention has no time window')
        else:
            _count(self.window_ns, 'window_ns', minimum=1)


@dataclass(frozen=True, slots=True)
class CommandAcceptance:
    """Recorded candidate and original check reference, not published ACCEPTED."""

    command: PoseCommand
    backend: BackendIdentity
    session_id: str
    recorded_at: MonotonicInstant
    validation_id: str

    def __post_init__(self) -> None:
        _require(self.command, PoseCommand, 'command')
        _require(self.backend, BackendIdentity, 'backend')
        _validate_token(self.session_id, 'session_id')
        _validate_token(self.validation_id, 'validation_id')
        _instant(self.recorded_at)
        if self.backend.backend_epoch != self.command.backend_epoch:
            raise ValueError('acceptance must retain the submitted backend epoch')
        if self.recorded_at.clock_id != self.command.timing.clock_id:
            raise ValueError('acceptance must use the command protection clock')


@dataclass(frozen=True, slots=True)
class CommandEvent:
    state: CommandState
    certainty: ResultCertainty
    reason: str

    def __post_init__(self) -> None:
        _require(self.state, CommandState, 'state')
        _require(self.certainty, ResultCertainty, 'certainty')
        _text(self.reason, 'reason')
        if self.state in _UNCERTAIN_TERMINAL:
            allowed = {ResultCertainty.CONFIRMED, ResultCertainty.UNKNOWN}
        elif self.state in _TERMINAL:
            allowed = {ResultCertainty.CONFIRMED}
        else:
            allowed = {ResultCertainty.PENDING}
        if self.certainty not in allowed:
            raise ValueError('invalid command state / certainty combination')


@dataclass(frozen=True, slots=True)
class DispatchIntent:
    attempt_id: str
    plan_digest: str
    query_key: str

    def __post_init__(self) -> None:
        _validate_token(self.attempt_id, 'attempt_id')
        _validate_token(self.query_key, 'query_key')
        _require(self.plan_digest, str, 'plan_digest')
        if len(self.plan_digest) != 64 or any(char not in '0123456789abcdef' for char in self.plan_digest):
            raise ValueError('plan_digest must be a lowercase SHA-256 hex digest')


@dataclass(frozen=True, slots=True)
class BackendReceipt:
    attempt_id: str
    backend_handle: str

    def __post_init__(self) -> None:
        _validate_token(self.attempt_id, 'attempt_id')
        _text(self.backend_handle, 'backend_handle')


@dataclass(frozen=True, slots=True)
class ReconciliationFact:
    attempt_id: str
    kind: str
    detail: str

    def __post_init__(self) -> None:
        _validate_token(self.attempt_id, 'attempt_id')
        _validate_token(self.kind, 'kind')
        _text(self.detail, 'detail')


@dataclass(frozen=True, slots=True)
class JournalEntry:
    entry_id: str
    recorded_at: MonotonicInstant
    payload: CommandEvent | DispatchIntent | BackendReceipt | ReconciliationFact

    def __post_init__(self) -> None:
        _validate_token(self.entry_id, 'entry_id')
        _instant(self.recorded_at)
        if type(self.payload) not in (CommandEvent, DispatchIntent, BackendReceipt, ReconciliationFact):
            raise TypeError('journal payload must be a concrete supported domain value')


def _validate_history(acceptance: CommandAcceptance, entries: tuple[JournalEntry, ...]) -> None:
    previous_time = acceptance.recorded_at
    state = None
    intent = None
    receipt = None
    dispatched = False
    ids = set()
    for entry in entries:
        _require(entry, JournalEntry, 'entry')
        if entry.entry_id in ids:
            raise JournalEntryConflict('journal entry IDs must be unique')
        ids.add(entry.entry_id)
        now = entry.recorded_at
        if now.clock_id != previous_time.clock_id or now.tick_ns < previous_time.tick_ns:
            raise JournalOrderError('journal recording times must be ordered in one clock domain')
        previous_time = now
        payload = entry.payload
        if type(payload) is CommandEvent:
            if payload.state not in _NEXT.get(state, ()):
                raise JournalOrderError('illegal command transition or immutable terminal state')
            if (payload.state is CommandState.CANCELLED and receipt is not None
                    and state is not CommandState.CANCEL_REQUESTED):
                raise JournalOrderError('backend acceptance requires a recorded cancellation request')
            if payload.state is CommandState.DISPATCHING:
                if intent is None:
                    raise JournalOrderError('DISPATCHING requires a recorded intent')
                dispatched = True
            if payload.state is CommandState.EXECUTING and receipt is None:
                raise JournalOrderError('EXECUTING requires the original backend receipt')
            state = payload.state
        elif type(payload) is DispatchIntent:
            if intent is not None or state is not CommandState.PLANNING:
                raise JournalOrderError('one intent requires an accepted command in PLANNING')
            intent = payload
        else:
            if intent is None or payload.attempt_id != intent.attempt_id:
                raise JournalOrderError('fact must refer to the original dispatch attempt')
            if type(payload) is BackendReceipt:
                if not dispatched or receipt is not None:
                    raise JournalOrderError('one original receipt requires a recorded dispatch phase')
                receipt = payload


@dataclass(frozen=True, slots=True)
class CommandRecord:
    acceptance: CommandAcceptance
    entries: tuple[JournalEntry, ...] | list[JournalEntry] = ()
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        _require(self.acceptance, CommandAcceptance, 'acceptance')
        if type(self.entries) not in (list, tuple):
            raise TypeError('entries must be a list or tuple')
        entries = tuple(self.entries)
        _validate_history(self.acceptance, entries)
        object.__setattr__(self, 'entries', entries)
        object.__setattr__(self, 'digest', execution_digest(self.acceptance.command))

    @property
    def key(self) -> CommandKey:
        return self.acceptance.command.key

    @property
    def revision(self) -> int:
        return len(self.entries)

    @property
    def state(self) -> CommandState | None:
        return next((entry.payload.state for entry in reversed(self.entries)
                     if type(entry.payload) is CommandEvent), None)

    @property
    def certainty(self) -> ResultCertainty | None:
        return next((entry.payload.certainty for entry in reversed(self.entries)
                     if type(entry.payload) is CommandEvent), None)

    @property
    def terminal(self) -> CommandEvent | None:
        return next((entry.payload for entry in self.entries
                     if type(entry.payload) is CommandEvent and entry.payload.state in _TERMINAL), None)

    @property
    def intent(self) -> DispatchIntent | None:
        return next((entry.payload for entry in self.entries if type(entry.payload) is DispatchIntent), None)

    @property
    def receipt(self) -> BackendReceipt | None:
        return next((entry.payload for entry in self.entries if type(entry.payload) is BackendReceipt), None)


@dataclass(frozen=True, slots=True)
class AcceptanceWrite:
    record: CommandRecord
    created: bool

    def __post_init__(self) -> None:
        _require(self.record, CommandRecord, 'record')
        _require(self.created, bool, 'created')
