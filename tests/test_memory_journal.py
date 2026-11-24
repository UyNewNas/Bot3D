"""T02: real in-memory JournalPort, with deterministic thread barriers."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from threading import Barrier

import pytest

from framework.domain.geometry import Quaternion
from framework.domain.time import MonotonicInstant
from framework.domain.values import RobotId, Vector3

pytestmark = pytest.mark.t02_journal


def test_recorded_candidate_is_not_published_acceptance(journal_case):
    c = journal_case()
    assert c.journal.lookup(c.command.key) is None
    written = c.journal.record_acceptance(c.acceptance)
    assert written.created is True
    assert written.record.state is None and written.record.certainty is None
    assert written.record.entries == () and written.record.revision == 0
    assert written.record.acceptance == c.acceptance
    accepted = c.journal.append(c.command.key, c.entry(c.event(c.domain.CommandState.ACCEPTED)),
                                expected_revision=0)
    assert accepted.state is c.domain.CommandState.ACCEPTED
    assert accepted.certainty is c.domain.ResultCertainty.PENDING and accepted.revision == 1
    assert written.record.state is None and written.record.entries == ()


def test_same_semantics_preserve_original_binding_and_admission_inputs(journal_case):
    c = journal_case()
    first = c.journal.record_acceptance(c.acceptance)
    command = replace(c.command, request_id='retry',
                      goal=replace(c.command.goal, position_m=Vector3(1, -0.0, .25),
                                   orientation_xyzw=Quaternion(0, 0, 0, -1)))
    # Later metadata does not rewrite original accepted binding, session or evidence.
    retry = replace(c.acceptance, command=command, session_id='authorized-reader',
                    backend=replace(c.acceptance.backend, backend_id='new-resolution'),
                    recorded_at=MonotonicInstant('control-clock', 10000), validation_id='later-check')
    result = c.journal.record_acceptance(retry)
    assert result.created is False and result.record == first.record
    assert result.record.acceptance.command.request_id == 'request-1'
    assert result.record.acceptance.backend.backend_id == 'backend-a'
    assert result.record.acceptance.session_id == 'operator-a'


@pytest.mark.parametrize('field', ['epoch', 'target', 'deadline', 'lease'])
def test_conflict_never_replaces_original_record(field, journal_case):
    c = journal_case()
    first = c.journal.record_acceptance(c.acceptance).record
    changes = {
        'epoch': replace(c.command, backend_epoch='epoch-b'),
        'target': replace(c.command, goal=replace(c.command.goal, position_m=Vector3(2, 0, .25))),
        'deadline': replace(c.command, timing=replace(c.command.timing, start_before_ns=201)),
        'lease': replace(c.command, lease_id='replacement-lease'),
    }
    new_command = changes[field]
    proposal = replace(c.acceptance, command=new_command,
                       backend=replace(c.acceptance.backend, backend_epoch=new_command.backend_epoch))
    with pytest.raises(c.domain.IdempotencyConflict) as caught:
        c.journal.record_acceptance(proposal)
    assert caught.value.code == 'IDEMPOTENCY_CONFLICT'
    assert c.journal.lookup(c.command.key) == first


def test_same_uuid_under_other_robot_is_a_distinct_key(journal_case):
    c = journal_case()
    first = c.journal.record_acceptance(c.acceptance).record
    other_robot = RobotId('other-arm')
    other = replace(c.command, key=replace(c.command.key, robot_id=other_robot),
                    goal=replace(c.command.goal, robot_id=other_robot))
    assert c.journal.record_acceptance(replace(c.acceptance, command=other)).created
    assert c.journal.lookup(c.command.key) == first
    assert c.journal.lookup(other.key).key.robot_id == other_robot


def test_real_threaded_same_key_acceptance_has_one_creator(journal_case):
    c = journal_case()
    start = Barrier(8)

    def submit(n):
        start.wait(timeout=5)
        return c.journal.record_acceptance(replace(c.acceptance,
            command=replace(c.command, request_id=f'request-{n}')))

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(submit, range(8)))
    assert sum(result.created for result in results) == 1
    assert all(result.record == results[0].record for result in results)
    assert c.journal.lookup(c.command.key).revision == 0


def test_revision_conflict_and_exact_event_retry(journal_case):
    c = journal_case()
    original = c.planning()
    entry = c.entry(c.domain.DispatchIntent('attempt-1', 'a' * 64, 'query-1'), 'intent', 3)
    updated = c.journal.append(c.command.key, entry, expected_revision=2)
    assert updated.revision == 3 and original.revision == 2 and original.intent is None
    assert c.journal.append(c.command.key, entry, expected_revision=2) == updated
    with pytest.raises(c.domain.JournalRevisionConflict):
        c.journal.append(c.command.key, c.entry(c.event(c.domain.CommandState.DISPATCHING), 'state', 4),
                         expected_revision=2)
    with pytest.raises(c.domain.JournalEntryConflict):
        c.journal.append(c.command.key, replace(entry, payload=replace(entry.payload, query_key='other')),
                         expected_revision=3)
    assert c.journal.lookup(c.command.key) == updated


def test_two_concurrent_updates_cannot_overwrite_each_other(journal_case):
    c = journal_case()
    c.planning()
    start = Barrier(2)

    def append(n):
        start.wait(timeout=5)
        try:
            return c.journal.append(c.command.key,
                c.entry(c.domain.DispatchIntent(f'attempt-{n}', 'a' * 64, f'query-{n}'), f'intent-{n}', 3),
                expected_revision=2)
        except c.domain.JournalRevisionConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(append, (1, 2)))
    assert sum(isinstance(result, c.domain.JournalRevisionConflict) for result in results) == 1
    record = c.journal.lookup(c.command.key)
    assert record.revision == 3 and len(record.entries) == 3
    assert record.intent.attempt_id in {'attempt-1', 'attempt-2'}


def test_intent_and_receipt_have_causal_order_and_one_original_attempt(journal_case):
    c = journal_case()
    c.journal.record_acceptance(c.acceptance)
    intent = c.entry(c.domain.DispatchIntent('attempt-1', 'a' * 64, 'query-1'), 'intent', 3)
    with pytest.raises(c.domain.JournalOrderError):
        c.journal.append(c.command.key, intent, expected_revision=0)
    c.planning()
    with pytest.raises(c.domain.JournalOrderError):
        c.journal.append(c.command.key, c.entry(c.event(c.domain.CommandState.DISPATCHING), 'dispatching', 3),
                         expected_revision=2)
    record = c.journal.append(c.command.key, intent, expected_revision=2)
    for payload in (c.domain.DispatchIntent('attempt-2', 'b' * 64, 'query-2'),
                    c.domain.BackendReceipt('attempt-2', 'wrong-handle')):
        with pytest.raises(c.domain.JournalOrderError):
            c.journal.append(c.command.key, c.entry(payload, 'wrong', 4), expected_revision=3)
    assert c.journal.lookup(c.command.key) == record


def test_record_keeps_receipt_and_success_after_real_lifecycle_facts(journal_case):
    c = journal_case()
    record = c.executing()
    result = c.journal.append(c.command.key,
        c.entry(c.event(c.domain.CommandState.SUCCEEDED, c.domain.ResultCertainty.CONFIRMED), 'terminal', 7),
        expected_revision=6)
    assert result.state is c.domain.CommandState.SUCCEEDED
    assert result.terminal.reason == 'fixture evidence'
    assert result.intent.query_key == 'query-1'
    assert result.receipt.backend_handle == 'handle-1'
    assert record.state is c.domain.CommandState.EXECUTING
    assert c.journal.record_acceptance(c.acceptance).record == result


def test_unknown_terminal_keeps_original_certainty_when_late_handle_arrives(journal_case):
    c = journal_case()
    c.planning()
    c.journal.append(c.command.key,
        c.entry(c.domain.DispatchIntent('attempt-1', 'a' * 64, 'query-1'), 'intent', 3), expected_revision=2)
    c.journal.append(c.command.key, c.entry(c.event(c.domain.CommandState.DISPATCHING), 'dispatching', 4),
                     expected_revision=3)
    unknown = c.event(c.domain.CommandState.INTERRUPTED, c.domain.ResultCertainty.UNKNOWN, 'reply lost')
    terminal = c.journal.append(c.command.key, c.entry(unknown, 'terminal', 5), expected_revision=4)
    receipt = c.journal.append(c.command.key,
        c.entry(c.domain.BackendReceipt('attempt-1', 'late-original-handle'), 'late-receipt', 6),
        expected_revision=5)
    reconciled = c.journal.append(c.command.key,
        c.entry(c.domain.ReconciliationFact('attempt-1', 'handle-result', 'later completion observed'), 'fact', 7),
        expected_revision=6)
    assert terminal.receipt is None and receipt.receipt.backend_handle == 'late-original-handle'
    assert reconciled.state is c.domain.CommandState.INTERRUPTED
    assert reconciled.certainty is c.domain.ResultCertainty.UNKNOWN
    assert reconciled.terminal == unknown
    for payload in (c.event(c.domain.CommandState.SUCCEEDED, c.domain.ResultCertainty.CONFIRMED),
                    c.domain.DispatchIntent('attempt-2', 'b' * 64, 'query-2'),
                    c.domain.BackendReceipt('attempt-1', 'replacement-handle')):
        with pytest.raises(c.domain.JournalOrderError):
            c.journal.append(c.command.key, c.entry(payload, 'forbidden', 8), expected_revision=7)


def test_cancel_prevents_late_success_and_terminal_key_cannot_be_reused(journal_case):
    c = journal_case()
    c.executing()
    c.journal.append(c.command.key, c.entry(c.event(c.domain.CommandState.CANCEL_REQUESTED), 'cancel', 7),
                     expected_revision=6)
    with pytest.raises(c.domain.JournalOrderError):
        c.journal.append(c.command.key,
            c.entry(c.event(c.domain.CommandState.SUCCEEDED, c.domain.ResultCertainty.CONFIRMED), 'late-success', 8),
            expected_revision=7)
    stopped = c.journal.append(c.command.key,
        c.entry(c.event(c.domain.CommandState.CANCELLED, c.domain.ResultCertainty.CONFIRMED), 'stopped', 8),
        expected_revision=7)
    assert c.journal.record_acceptance(c.acceptance).record == stopped


def test_rejected_candidate_still_owns_idempotency_key(journal_case):
    c = journal_case()
    c.journal.record_acceptance(c.acceptance)
    rejected = c.journal.append(c.command.key,
        c.entry(c.event(c.domain.CommandState.REJECTED, c.domain.ResultCertainty.CONFIRMED, 'lease changed'), 'rejected'),
        expected_revision=0)
    assert c.journal.record_acceptance(c.acceptance).record == rejected
    assert rejected.state is c.domain.CommandState.REJECTED


@pytest.mark.parametrize(('state', 'certainty', 'valid'), [
    ('ACCEPTED', 'PENDING', True), ('PLANNING', 'PENDING', True),
    ('DISPATCHING', 'PENDING', True), ('EXECUTING', 'PENDING', True),
    ('CANCEL_REQUESTED', 'PENDING', True), ('ACCEPTED', 'CONFIRMED', False),
    ('SUCCEEDED', 'CONFIRMED', True), ('SUCCEEDED', 'UNKNOWN', False),
    ('CANCELLED', 'CONFIRMED', True), ('CANCELLED', 'UNKNOWN', False),
    ('REJECTED', 'CONFIRMED', True), ('REJECTED', 'UNKNOWN', False),
    ('FAILED', 'UNKNOWN', True), ('FAILED', 'CONFIRMED', True), ('FAILED', 'PENDING', False),
    ('TIMED_OUT', 'UNKNOWN', True), ('TIMED_OUT', 'CONFIRMED', True),
    ('INTERRUPTED', 'UNKNOWN', True), ('INTERRUPTED', 'CONFIRMED', True),
])
def test_public_state_certainty_pairs_are_preserved(state, certainty, valid, journal_case):
    c = journal_case()
    if valid:
        assert c.event(c.domain.CommandState(state), c.domain.ResultCertainty(certainty)).state.value == state
    else:
        with pytest.raises(ValueError):
            c.event(c.domain.CommandState(state), c.domain.ResultCertainty(certainty))


def test_scope_timestamp_and_plain_data_validation(journal_case):
    c = journal_case()
    with pytest.raises(ValueError):
        replace(c.acceptance, backend=replace(c.acceptance.backend, backend_epoch='old-epoch'))
    with pytest.raises(ValueError):
        replace(c.acceptance, recorded_at=MonotonicInstant('other-clock', 0))
    record = c.planning()
    for instant in (MonotonicInstant('control-clock', 1), MonotonicInstant('other-clock', 3)):
        with pytest.raises(c.domain.JournalOrderError):
            c.journal.append(c.command.key,
                replace(c.entry(c.domain.DispatchIntent('attempt-1', 'a' * 64, 'query-1')), recorded_at=instant),
                expected_revision=2)
    with pytest.raises(TypeError):
        c.journal.append(c.command.key, c.entry(c.event(c.domain.CommandState.PLANNING)), expected_revision=True)
    with pytest.raises(TypeError):
        c.entry({'sdk': object()})
    with pytest.raises(TypeError):
        c.domain.CommandEvent('ACCEPTED', c.domain.ResultCertainty.PENDING, 'not enum')
    with pytest.raises(FrozenInstanceError):
        record.entries = ()
    assert c.journal.lookup(c.command.key) == record


def test_retention_declares_volatile_instance_lifetime_and_never_prunes(journal_case):
    c = journal_case()
    record = c.journal.record_acceptance(c.acceptance).record
    retention = c.journal.retention
    assert retention.scope is c.domain.RetentionScope.INSTANCE_LIFETIME
    assert retention.window_ns is None and retention.durable is False
    assert c.journal.lookup(c.command.key) == record
    assert journal_case().journal.lookup(c.command.key) is None


def test_missing_key_and_malformed_inputs_are_not_accepted(journal_case):
    c = journal_case()
    entry = c.entry(c.event(c.domain.CommandState.ACCEPTED))
    with pytest.raises(c.domain.JournalRecordNotFound):
        c.journal.append(c.command.key, entry, expected_revision=0)
    with pytest.raises(TypeError):
        c.journal.lookup((c.command.key.robot_id, c.command.key.command_id))
    with pytest.raises(TypeError):
        c.journal.record_acceptance(c.command)


def test_intent_cannot_precede_planning(journal_case):
    c = journal_case()
    c.journal.record_acceptance(c.acceptance)
    accepted = c.journal.append(c.command.key, c.entry(c.event(c.domain.CommandState.ACCEPTED), 'accepted'),
                                expected_revision=0)
    with pytest.raises(c.domain.JournalOrderError):
        c.journal.append(c.command.key,
            c.entry(c.domain.DispatchIntent('attempt-1', 'a' * 64, 'query-1'), 'too-early', 2),
            expected_revision=1)
    assert c.journal.lookup(c.command.key) == accepted


@pytest.mark.parametrize('phase', ['receipt', 'executing'])
def test_backend_acceptance_requires_cancellation_request_before_cancelled(phase, journal_case):
    c = journal_case()
    c.planning()
    c.journal.append(c.command.key,
        c.entry(c.domain.DispatchIntent('attempt-1', 'a' * 64, 'query-1'), 'intent', 3), expected_revision=2)
    c.journal.append(c.command.key,
        c.entry(c.event(c.domain.CommandState.DISPATCHING), 'dispatching', 4), expected_revision=3)
    record = c.journal.append(c.command.key,
        c.entry(c.domain.BackendReceipt('attempt-1', 'handle-1'), 'receipt', 5), expected_revision=4)
    if phase == 'executing':
        record = c.journal.append(c.command.key,
            c.entry(c.event(c.domain.CommandState.EXECUTING), 'executing', 6), expected_revision=5)
    with pytest.raises(c.domain.JournalOrderError):
        c.journal.append(c.command.key,
            c.entry(c.event(c.domain.CommandState.CANCELLED, c.domain.ResultCertainty.CONFIRMED), 'shortcut', 7),
            expected_revision=record.revision)
    assert c.journal.lookup(c.command.key) == record
    pending = c.journal.append(c.command.key,
        c.entry(c.event(c.domain.CommandState.CANCEL_REQUESTED), 'cancel-requested', 7),
        expected_revision=record.revision)
    cancelled = c.journal.append(c.command.key,
        c.entry(c.event(c.domain.CommandState.CANCELLED, c.domain.ResultCertainty.CONFIRMED), 'cancelled', 8),
        expected_revision=pending.revision)
    assert cancelled.state is c.domain.CommandState.CANCELLED


def test_undispatched_ticket_can_be_cancelled_without_backend_cancellation(journal_case):
    c = journal_case()
    c.planning()
    c.journal.append(c.command.key,
        c.entry(c.domain.DispatchIntent('attempt-1', 'a' * 64, 'query-1'), 'intent', 3), expected_revision=2)
    c.journal.append(c.command.key,
        c.entry(c.event(c.domain.CommandState.DISPATCHING), 'dispatching', 4), expected_revision=3)
    cancelled = c.journal.append(c.command.key,
        c.entry(c.event(c.domain.CommandState.CANCELLED, c.domain.ResultCertainty.CONFIRMED,
                        'coordinator proved ticket revoked before final claim'), 'cancelled', 5),
        expected_revision=4)
    assert cancelled.state is c.domain.CommandState.CANCELLED and cancelled.receipt is None
