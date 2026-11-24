"""T18: injected backing-store failures exercise the real journal's error paths."""
from dataclasses import replace

import pytest

pytestmark = pytest.mark.t18_journal_fault


class FailingRecords(dict):
    """Test-only mapping: preserve real records and vary the commit boundary."""

    def __init__(self, records, phase):
        super().__init__(records)
        self.phase = phase
        self.writes = 0

    def __setitem__(self, key, value):
        self.writes += 1
        if self.phase == 'before':
            raise OSError('write failed before commit')
        super().__setitem__(key, value)
        if self.phase == 'after':
            raise OSError('commit acknowledged too late')

    def get(self, key, default=None):
        if self.phase == 'read':
            raise OSError('read failed')
        return super().get(key, default)


@pytest.mark.parametrize('phase', ['before', 'after'])
@pytest.mark.parametrize('stage', ['acceptance', 'intent', 'terminal'])
def test_failed_write_never_reports_success_or_reopens_key(phase, stage, journal_case):
    c = journal_case()
    if stage == 'intent':
        before = c.planning()
        pending = c.entry(c.domain.DispatchIntent('attempt-1', 'a' * 64, 'query-1'), 'intent', 3)
    elif stage == 'terminal':
        before = c.executing()
        pending = c.entry(c.event(c.domain.CommandState.SUCCEEDED, c.domain.ResultCertainty.CONFIRMED), 'done', 7)
    else:
        before = None

    store = FailingRecords(c.journal._records, phase)
    c.journal._records = store
    with pytest.raises(c.domain.JournalUnavailable) as failure:
        if stage == 'acceptance':
            c.journal.record_acceptance(c.acceptance)
        else:
            c.journal.append(c.command.key, pending, expected_revision=before.revision)
    assert failure.value.write_outcome is c.domain.WriteOutcome.UNKNOWN
    assert store.writes == 1
    # A known-uncertain key cannot be reported as absent or silently retried.
    with pytest.raises(c.domain.JournalUnavailable):
        c.journal.lookup(c.command.key)
    with pytest.raises(c.domain.JournalUnavailable):
        c.journal.record_acceptance(c.acceptance)
    other = replace(c.command, key=replace(c.command.key,
                    command_id='12345678-1234-5678-1234-567812345679'))
    with pytest.raises(c.domain.JournalUnavailable) as denied:
        c.journal.record_acceptance(replace(c.acceptance, command=other))
    assert denied.value.write_outcome is c.domain.WriteOutcome.NOT_COMMITTED
    assert store.writes == 1
    # Inspect the injected storage directly: old or whole new record, never half an update.
    stored = dict.get(store, c.command.key)
    if phase == 'before':
        assert stored == before
    elif stage == 'acceptance':
        assert stored.acceptance == c.acceptance and stored.revision == 0 and stored.state is None
    else:
        assert stored.revision == before.revision + 1 and stored.entries[-1] == pending
        assert before.entries[-1] != pending


def test_read_failure_is_not_a_missing_record_and_blocks_new_writes(journal_case):
    c = journal_case()
    c.journal.record_acceptance(c.acceptance)
    c.journal._records = FailingRecords(c.journal._records, 'read')
    with pytest.raises(c.domain.JournalUnavailable) as failure:
        c.journal.lookup(c.command.key)
    assert failure.value.operation == 'lookup' and failure.value.write_outcome is None
    c.journal._records.phase = 'healthy'
    with pytest.raises(c.domain.JournalUnavailable):
        c.journal.lookup(c.command.key)
    with pytest.raises(c.domain.JournalUnavailable):
        c.journal.record_acceptance(replace(c.acceptance, command=replace(c.command,
            key=replace(c.command.key, command_id='12345678-1234-5678-1234-567812345679'))))


def test_unaffected_history_can_be_read_after_other_key_failure(journal_case):
    c = journal_case()
    old = c.executing()
    c.journal._records = FailingRecords(c.journal._records, 'before')
    new_command = replace(c.command, key=replace(c.command.key,
                          command_id='12345678-1234-5678-1234-567812345679'))
    with pytest.raises(c.domain.JournalUnavailable):
        c.journal.record_acceptance(replace(c.acceptance, command=new_command))
    assert c.journal.lookup(c.command.key) == old
    retry = c.journal.record_acceptance(c.acceptance)
    assert retry.created is False and retry.record == old
    assert c.journal.append(c.command.key, old.entries[-1], expected_revision=5) == old
    with pytest.raises(c.domain.JournalUnavailable):
        c.journal.append(c.command.key,
            c.entry(c.event(c.domain.CommandState.SUCCEEDED, c.domain.ResultCertainty.CONFIRMED), 'done', 7),
            expected_revision=6)
