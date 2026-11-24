"""T42/lease-clock: the protection clock controls expiry and fails closed."""
from dataclasses import replace

import pytest

from framework.domain.time import MonotonicInstant

pytestmark = pytest.mark.t42_lease_clock


class AdjustableClock:
    """A quick deterministic port for fault readings a real manual clock forbids."""

    def __init__(self, reading=None):
        self.reading = MonotonicInstant('control-clock', 0) if reading is None else reading
        self.reads = 0

    def now(self):
        self.reads += 1
        if isinstance(self.reading, Exception):
            raise self.reading
        return self.reading


@pytest.mark.parametrize(('duration', 'error'), [
    (0, ValueError), (-1, ValueError), (101, ValueError), (True, TypeError),
    (1.5, TypeError), ('10', TypeError),
])
def test_programming_duration_errors_do_not_run_expiry_maintenance(duration, error, authority_case):
    clock = AdjustableClock()
    case = authority_case(clock=clock)
    authority, d = case.authority, case.domain
    grant = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    clock.reading = MonotonicInstant('control-clock', 10)
    assert clock.reads == 2
    with pytest.raises(error):
        authority.acquire(case.binding, 'operator-b', case.evidence, duration_ns=duration)
    with pytest.raises(error):
        authority.renew(case.binding, 'operator-a', grant.lease.lease_id, case.evidence, duration_ns=duration)
    assert clock.reads == 2
    expired = authority.snapshot(case.binding)
    assert expired.denial is d.AuthorityDenial.LEASE_EXPIRED
    assert expired.losses[0].lease_id == grant.lease.lease_id


@pytest.mark.parametrize(('deadline_check', 'expected'), [(9, None), (10, 'LEASE_EXPIRED'), (11, 'LEASE_EXPIRED')])
def test_snapshot_enforces_strict_expiry(deadline_check, expected, authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    grant = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    authority.activate(case.binding, 'operator-a', grant.lease.lease_id, case.evidence, confirmed=True)
    case.clock.advance_ns(deadline_check)
    snapshot = authority.snapshot(case.binding)
    if expected is None:
        assert snapshot.accepted and not snapshot.losses
        assert snapshot.snapshot.arming_state is d.ArmingState.ARMED
    else:
        assert snapshot.denial is d.AuthorityDenial[expected]
        assert snapshot.snapshot.arming_state is d.ArmingState.DISARMED
        assert snapshot.losses[0].reason is d.AuthorityLossReason.EXPIRED
        assert authority.snapshot(case.binding).accepted


def test_source_clock_advance_cannot_change_protection_deadline(authority_case, source_clock):
    case = authority_case()
    authority, d = case.authority, case.domain
    grant = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    source_clock.advance_ns(100000)
    assert authority.poll_expired() == ()
    case.clock.advance_ns(10)
    effects = authority.poll_expired()
    assert len(effects) == 1 and effects[0].lease_id == grant.lease.lease_id
    assert effects[0].reason is d.AuthorityLossReason.EXPIRED


@pytest.mark.parametrize('fault', [
    MonotonicInstant('other-clock', 1000),
    MonotonicInstant('control-clock', 0),
    RuntimeError('test clock read failed'),
    'invalid-reading',
], ids=['changed-clock', 'regressed-tick', 'exception', 'invalid-reading'])
def test_global_fault_effects_survive_forbidden_request_and_latched_clock(fault, authority_case):
    clock = AdjustableClock(MonotonicInstant('control-clock', 1))
    case = authority_case(clock=clock, extra_bindings=True)
    authority, d = case.authority, case.domain
    authority.register_session(d.SessionAuthorization('other-operator', [case.other.robot_id]))
    other_evidence = replace(case.evidence, binding=case.other)
    other = authority.acquire(case.other, 'other-operator', other_evidence, duration_ns=10)
    primary = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    for binding, session, grant, evidence in (
        (case.binding, 'operator-a', primary, case.evidence),
        (case.other, 'other-operator', other, other_evidence),
    ):
        armed = authority.activate(binding, session, grant.lease.lease_id, evidence, confirmed=True)
        assert armed.accepted and armed.snapshot.arming_state is d.ArmingState.ARMED

    auxiliary_hold, _ = authority.mark_execution_unresolved(case.mirror)
    clock.reading = fault
    rejected = authority.acquire(case.binding, 'viewer', case.evidence, duration_ns=10)
    assert rejected.denial is d.AuthorityDenial.FORBIDDEN
    assert rejected.snapshot.clock_faulted and rejected.snapshot.lease_owner is None
    assert rejected.snapshot.arming_state is d.ArmingState.DISARMED
    reason = d.AuthorityLossReason.CLOCK_FAULT
    assert rejected.losses == (
        d.AuthorityLost(case.binding, reason, 1, 'operator-a', primary.lease.lease_id),
        d.AuthorityLost(case.other, reason, 1, 'other-operator', other.lease.lease_id),
    )
    reads_after_fault = clock.reads
    clock.reading = MonotonicInstant('control-clock', 2)
    unhealthy = authority.snapshot(case.other)
    assert unhealthy.denial is d.AuthorityDenial.CLOCK_UNHEALTHY
    assert unhealthy.snapshot.clock_faulted and unhealthy.snapshot.lease_owner is None
    assert unhealthy.snapshot.arming_state is d.ArmingState.DISARMED
    assert not unhealthy.losses and authority.poll_expired() == ()
    assert authority.acquire(
        case.binding, 'operator-a', case.evidence, duration_ns=10,
    ).denial is d.AuthorityDenial.CLOCK_UNHEALTHY
    assert authority.snapshot(case.mirror).snapshot.execution_blocked
    assert authority.resolve_execution(auxiliary_hold).accepted
    assert authority.revoke_session('operator-a', d.AuthorityLossReason.SESSION_LOST) == ()
    hold, marked = authority.mark_execution_unresolved(case.other)
    assert marked.accepted and authority.resolve_execution(hold).accepted
    protection = authority.revoke(case.binding, d.AuthorityLossReason.STOP_REQUESTED)
    assert protection.accepted and protection.losses[0].session_id is None
    assert clock.reads == reads_after_fault


def test_protection_and_stale_binding_do_not_touch_clock_before_fault_discovery(authority_case):
    clock = AdjustableClock()
    case = authority_case(clock=clock, extra_bindings=True)
    authority, d = case.authority, case.domain
    primary = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    authority.register_session(d.SessionAuthorization('other-operator', [case.other.robot_id]))
    other = authority.acquire(
        case.other, 'other-operator', replace(case.evidence, binding=case.other), duration_ns=10,
    )
    reads = clock.reads
    clock.reading = RuntimeError('test clock read failed')
    stale = replace(case.binding, backend=replace(case.binding.backend, backend_epoch='old-epoch'))
    assert authority.snapshot(stale).denial is d.AuthorityDenial.STALE_BINDING
    protection = authority.revoke(case.binding, d.AuthorityLossReason.STOP_REQUESTED)
    assert protection.losses[0].lease_id == primary.lease.lease_id
    hold, marked = authority.mark_execution_unresolved(case.binding)
    assert marked.accepted and authority.resolve_execution(hold).accepted
    assert clock.reads == reads
    effects = authority.revoke_session('other-operator', d.AuthorityLossReason.PERMISSION_REVOKED)
    assert effects[0].lease_id == other.lease.lease_id and clock.reads == reads
    assert authority.snapshot(case.binding).snapshot.clock_faulted


def test_targeted_maintenance_leaves_other_expiry_for_sorted_poll(authority_case):
    case = authority_case(extra_bindings=True)
    authority, d = case.authority, case.domain
    last = replace(case.other, robot_id=type(case.other.robot_id)('z-fixture'))
    authority = case.application.ControlAuthority([last, case.binding, case.mirror], case.clock, max_lease_ns=100)
    authority.register_session(d.SessionAuthorization('operator-a', [last.robot_id, case.binding.robot_id]))
    authority.acquire(last, 'operator-a', replace(case.evidence, binding=last), duration_ns=10)
    authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    case.clock.advance_ns(10)
    assert authority.snapshot(case.mirror).accepted
    effects = authority.poll_expired()
    assert [effect.binding for effect in effects] == [case.binding, last]
    assert all(effect.reason is d.AuthorityLossReason.EXPIRED for effect in effects)
    assert authority.poll_expired() == ()


def test_constructor_validates_maximum_and_initial_clock_read(authority_case):
    plain = authority_case()
    cls = plain.application.ControlAuthority
    unread = AdjustableClock()
    with pytest.raises(TypeError):
        cls([plain.binding], unread, max_lease_ns=True)
    with pytest.raises(ValueError):
        cls([plain.binding], unread, max_lease_ns=0)
    assert unread.reads == 0
    with pytest.raises(RuntimeError, match='test initial fault'):
        cls([plain.binding], AdjustableClock(RuntimeError('test initial fault')), max_lease_ns=100)
    with pytest.raises(TypeError):
        cls([plain.binding], AdjustableClock('invalid-reading'), max_lease_ns=100)
