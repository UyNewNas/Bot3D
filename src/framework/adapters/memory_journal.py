"""Volatile single-process JournalPort; no executor, disk or pruning side effects."""
from __future__ import annotations

from threading import Lock

from framework.domain.commands import CommandKey, _count, _require, execution_digest
from framework.domain.journal import (
    AcceptanceWrite, CommandAcceptance, CommandRecord, IdempotencyConflict,
    JournalEntry, JournalEntryConflict, JournalRecordNotFound, JournalRetention,
    JournalRevisionConflict, JournalUnavailable, RetentionScope, WriteOutcome,
)

__all__ = ['InMemoryJournal']


class InMemoryJournal:
    """Atomic immutable snapshots retained for this instance's lifetime only.

    Storage failure latches writes closed. Affected keys remain explicitly
    uncertain, including failures before a record is visible. Recovery and
    durable reconciliation are outside this volatile adapter's contract.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._records: dict[CommandKey, CommandRecord] = {}
        self._write_faulted = False
        self._uncertain_keys: set[CommandKey] = set()
        self._retention = JournalRetention(RetentionScope.INSTANCE_LIFETIME, None, False)

    @property
    def retention(self) -> JournalRetention:
        return self._retention

    def _read(self, key: CommandKey, operation: str) -> CommandRecord | None:
        if key in self._uncertain_keys:
            raise JournalUnavailable(operation, WriteOutcome.UNKNOWN)
        try:
            return self._records.get(key)
        except Exception as exc:
            self._write_faulted = True
            self._uncertain_keys.add(key)
            raise JournalUnavailable(operation, None) from exc

    def _save(self, record: CommandRecord, operation: str) -> None:
        if self._write_faulted:
            raise JournalUnavailable(operation, WriteOutcome.NOT_COMMITTED)
        try:
            self._records[record.key] = record
        except Exception as exc:
            self._write_faulted = True
            self._uncertain_keys.add(record.key)
            raise JournalUnavailable(operation, WriteOutcome.UNKNOWN) from exc

    def lookup(self, key: CommandKey) -> CommandRecord | None:
        _require(key, CommandKey, 'key')
        with self._lock:
            return self._read(key, 'lookup')

    def record_acceptance(self, acceptance: CommandAcceptance) -> AcceptanceWrite:
        _require(acceptance, CommandAcceptance, 'acceptance')
        key = acceptance.command.key
        digest = execution_digest(acceptance.command)
        with self._lock:
            existing = self._read(key, 'record_acceptance')
            if existing is not None:
                if existing.digest != digest:
                    raise IdempotencyConflict('command key already has different execution semantics')
                return AcceptanceWrite(existing, False)
            record = CommandRecord(acceptance)
            self._save(record, 'record_acceptance')
            return AcceptanceWrite(record, True)

    def append(self, key: CommandKey, entry: JournalEntry, *, expected_revision: int) -> CommandRecord:
        _require(key, CommandKey, 'key')
        _require(entry, JournalEntry, 'entry')
        _count(expected_revision, 'expected_revision')
        with self._lock:
            existing = self._read(key, 'append')
            if existing is None:
                raise JournalRecordNotFound('cannot append before recording an acceptance candidate')
            for previous in existing.entries:
                if previous.entry_id == entry.entry_id:
                    if previous != entry:
                        raise JournalEntryConflict('entry ID already identifies different facts')
                    return existing
            if existing.revision != expected_revision:
                raise JournalRevisionConflict('journal revision changed; read the original record')
            updated = CommandRecord(existing.acceptance, existing.entries + (entry,))
            self._save(updated, 'append')
            return updated
