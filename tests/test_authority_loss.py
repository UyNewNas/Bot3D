"""T07/authority-loss: each effect preserves the scope it revoked."""
from dataclasses import replace

import pytest

pytestmark = pytest.mark.t07_authority_loss


@pytest.mark.parametrize(('operation', 'reason'), [('release', 'RELEASED'), ('deactivate', 'DEACTIVATED')])
def test_voluntary_loss_disarms_and_hands_off_original_binding(operation, reason, authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    grant = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    token = grant.lease.lease_id
    armed = authority.activate(case.binding, 'operator-a', token, case.evidence, confirmed=True)
    assert armed.accepted and armed.snapshot.arming_state is d.ArmingState.ARMED
    result = getattr(authority, operation)(case.binding, 'operator-a', token)
    assert result.accepted and result.lease is None
    assert result.snapshot.lease_owner is None and result.snapshot.arming_state is d.ArmingState.DISARMED
    assert result.snapshot.revoke_generation == 1
    assert result.losses == (
        d.AuthorityLost(case.binding, d.AuthorityLossReason[reason], 1, 'operator-a', token),
    )
    assert token not in repr(result.losses[0])
    assert armed.snapshot.lease_owner == 'operator-a'


@pytest.mark.parametrize('reason', ['SESSION_LOST', 'PERMISSION_REVOKED'])
def test_revoked_sessions_cannot_reacquire_or_register_same_id(reason, authority_case):
    case = authority_case(extra_bindings=True)
    authority, d = case.authority, case.domain
    authorization = d.SessionAuthorization('operator-shared', [case.other.robot_id, case.binding.robot_id])
    authority.register_session(authorization)
    other_grant = authority.acquire(
        case.other, 'operator-shared', replace(case.evidence, binding=case.other), duration_ns=10,
    )
    first_grant = authority.acquire(case.binding, 'operator-shared', case.evidence, duration_ns=10)
    loss_reason = d.AuthorityLossReason[reason]
    effects = authority.revoke_session('operator-shared', loss_reason)
    assert effects == (
        d.AuthorityLost(case.binding, loss_reason, 1, 'operator-shared', first_grant.lease.lease_id),
        d.AuthorityLost(case.other, loss_reason, 1, 'operator-shared', other_grant.lease.lease_id),
    )
    assert authority.revoke_session('operator-shared', loss_reason) == ()
    with pytest.raises(ValueError):
        authority.register_session(authorization)
    with pytest.raises(KeyError):
        authority.revoke_session('unknown-session', loss_reason)
    assert authority.acquire(
        case.binding, 'operator-shared', case.evidence, duration_ns=10,
    ).denial is d.AuthorityDenial.FORBIDDEN
    replacement = authority.acquire(case.binding, 'operator-b', case.evidence, duration_ns=10)
    rejected = authority.check(
        case.binding, 'operator-shared', first_grant.lease.lease_id, case.evidence,
    )
    assert rejected.denial is d.AuthorityDenial.FORBIDDEN
    assert rejected.snapshot == replacement.snapshot and not rejected.losses


@pytest.mark.parametrize(('actor', 'denial'), [('operator-b', 'LEASE_EXPIRED'), ('viewer', 'FORBIDDEN')])
def test_acquire_reports_expiry_even_when_request_cannot_grant(actor, denial, authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    grant = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    case.clock.advance_ns(10)
    response = authority.acquire(case.binding, actor, case.evidence, duration_ns=10)
    assert response.denial is d.AuthorityDenial[denial]
    assert response.snapshot.lease_owner is None
    assert response.losses == (
        d.AuthorityLost(case.binding, d.AuthorityLossReason.EXPIRED, 1, 'operator-a', grant.lease.lease_id),
    )
    observer = authority.snapshot(case.binding)
    assert observer.accepted and not observer.losses
    assert authority.poll_expired() == ()
    fresh = authority.acquire(case.binding, 'operator-b', case.evidence, duration_ns=10)
    assert fresh.accepted and fresh.lease.lease_id != grant.lease.lease_id


def test_delayed_timeout_cannot_revoke_another_lease(authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    timeout = d.AuthorityLossReason.EXECUTION_TIMEOUT
    first = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    with pytest.raises(ValueError):
        authority.revoke(case.binding, timeout)
    stale = replace(case.binding, backend=replace(case.binding.backend, backend_epoch='old'))
    assert authority.revoke(stale, timeout, lease_id=first.lease.lease_id).denial is d.AuthorityDenial.STALE_BINDING
    expired = authority.revoke(case.binding, timeout, lease_id=first.lease.lease_id)
    assert expired.accepted
    assert expired.losses == (d.AuthorityLost(case.binding, timeout, 1, 'operator-a', first.lease.lease_id),)
    second = authority.acquire(case.binding, 'operator-b', case.evidence, duration_ns=10)
    delayed = authority.revoke(case.binding, timeout, lease_id=first.lease.lease_id)
    assert delayed.denial is d.AuthorityDenial.STALE_LEASE
    assert delayed.snapshot == second.snapshot and not delayed.losses


def test_trusted_idle_revoke_reports_ownerless_protection(authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    reason = d.AuthorityLossReason.STOP_REQUESTED
    revoked = authority.revoke(case.binding, reason)
    assert revoked.accepted
    assert revoked.losses == (d.AuthorityLost(case.binding, reason, 1, None, None),)
    with pytest.raises(ValueError):
        authority.revoke(case.binding, d.AuthorityLossReason.CLOCK_FAULT)
    with pytest.raises(ValueError):
        authority.revoke_session('operator-a', reason)


def test_unresolved_execution_atomically_revokes_then_requires_current_aggregate_hold(authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    lease = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10).lease
    armed = authority.activate(case.binding, 'operator-a', lease.lease_id, case.evidence, confirmed=True)
    assert armed.accepted and armed.snapshot.arming_state is d.ArmingState.ARMED
    first, blocked = authority.mark_execution_unresolved(case.binding)
    reason = d.AuthorityLossReason.EXECUTION_UNRESOLVED
    assert blocked.accepted and blocked.snapshot.execution_blocked
    assert blocked.snapshot.lease_owner is None and blocked.snapshot.arming_state is d.ArmingState.DISARMED
    assert blocked.losses == (d.AuthorityLost(case.binding, reason, 1, 'operator-a', lease.lease_id),)
    assert authority.snapshot(case.binding).accepted
    assert authority.acquire(
        case.binding, 'operator-a', case.evidence, duration_ns=10,
    ).denial is d.AuthorityDenial.EXECUTION_UNRESOLVED
    second, still_blocked = authority.mark_execution_unresolved(case.binding)
    assert second.hold_id != first.hold_id and second.revision == first.revision + 1
    assert second.hold_id not in repr(second)
    assert still_blocked.losses == (d.AuthorityLost(case.binding, reason, 2, None, None),)
    for old in (first, replace(second, hold_id='different'), replace(second, revision=first.revision)):
        response = authority.resolve_execution(old)
        assert response.denial is d.AuthorityDenial.STALE_HOLD and response.snapshot.execution_blocked
    cleared = authority.resolve_execution(second)
    assert cleared.accepted and not cleared.snapshot.execution_blocked
    assert cleared.snapshot.lease_owner is None and cleared.snapshot.arming_state is d.ArmingState.DISARMED
    assert authority.resolve_execution(second).denial is d.AuthorityDenial.STALE_HOLD
    fresh = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    assert fresh.lease.grant_generation == 2
    assert authority.activate(
        case.binding, 'operator-a', lease.lease_id, case.evidence, confirmed=True,
    ).denial is d.AuthorityDenial.STALE_LEASE
    assert fresh.snapshot.arming_state is d.ArmingState.DISARMED


def test_hold_operations_require_exact_binding_and_preserve_retirement(authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    stale = replace(case.binding, backend=replace(case.binding.backend, backend_epoch='old'))
    with pytest.raises(ValueError):
        authority.mark_execution_unresolved(stale)
    hold, _ = authority.mark_execution_unresolved(case.binding)
    denied = authority.resolve_execution(replace(hold, binding=stale))
    assert denied.denial is d.AuthorityDenial.STALE_BINDING and denied.snapshot.execution_blocked
    retired = authority.revoke(case.binding, d.AuthorityLossReason.CONTEXT_CHANGED)
    assert retired.snapshot.execution_blocked and retired.snapshot.binding_retired
    resolved = authority.resolve_execution(hold)
    assert resolved.accepted and resolved.snapshot.binding_retired and not resolved.snapshot.execution_blocked
    assert authority.acquire(
        case.binding, 'operator-a', case.evidence, duration_ns=10,
    ).denial is d.AuthorityDenial.CONTEXT_CHANGED


def test_loss_and_result_values_reject_invalid_scope_and_duplicate_effects(authority_case):
    case = authority_case()
    d = case.domain
    initial = case.authority.snapshot(case.binding).snapshot
    with pytest.raises(ValueError):
        d.AuthorityLost(case.binding, d.AuthorityLossReason.EXPIRED, 1, None, None)
    with pytest.raises(ValueError):
        d.AuthorityLost(case.binding, d.AuthorityLossReason.STOP_REQUESTED, 1, 'operator-a', None)
    with pytest.raises(ValueError):
        d.AuthorityLost(case.mirror, d.AuthorityLossReason.EXPIRED, 1, 'operator-a', 'lease')
    with pytest.raises(ValueError):
        d.AuthorityLost(case.binding, d.AuthorityLossReason.CRITICAL_FAULT, 0, None, None)
    future = d.AuthorityLost(case.binding, d.AuthorityLossReason.STOP_REQUESTED, 1, None, None)
    with pytest.raises(ValueError):
        d.AuthorityResult(initial, losses=[future])
    present = replace(initial, revoke_generation=1)
    with pytest.raises(ValueError):
        d.AuthorityResult(present, losses=[future, future])
    with pytest.raises(ValueError):
        d.AuthorityResult(present, losses=[replace(future, binding=case.other)])
    reason = d.AuthorityLossReason.CLOCK_FAULT
    target = d.AuthorityLost(case.binding, reason, 1, 'operator-a', 'target-lease')
    crossed = d.AuthorityLost(case.other, reason, 2, 'operator-b', 'other-lease')
    events = [target, crossed]
    faulted = replace(present, clock_faulted=True)
    result = d.AuthorityResult(faulted, denial=d.AuthorityDenial.FORBIDDEN, losses=events)
    events.clear()
    assert result.losses == (target, crossed) and not result.accepted


def test_foreign_clock_fault_cannot_accompany_an_armed_snapshot(authority_case):
    case = authority_case()
    d = case.domain
    armed = d.AuthoritySnapshot(
        case.binding, d.ArmingState.ARMED, 'operator-a', case.evidence.valid_until,
        False, 0, False, False,
    )
    foreign_loss = d.AuthorityLost(
        case.other, d.AuthorityLossReason.CLOCK_FAULT, 1, 'operator-b', 'other-lease',
    )
    with pytest.raises(ValueError):
        d.AuthorityResult(armed, losses=(foreign_loss,))


def test_same_binding_clock_fault_requires_a_faulted_snapshot(authority_case):
    case = authority_case()
    d = case.domain
    healthy = d.AuthoritySnapshot(
        case.binding, d.ArmingState.DISARMED, None, None, False, 1, False, False,
    )
    loss = d.AuthorityLost(
        case.binding, d.AuthorityLossReason.CLOCK_FAULT, 1, 'operator-a', 'target-lease',
    )
    with pytest.raises(ValueError):
        d.AuthorityResult(healthy, denial=d.AuthorityDenial.FORBIDDEN, losses=(loss,))


def test_historical_context_loss_requires_binding_retirement(authority_case):
    case = authority_case()
    d = case.domain
    armed = d.AuthoritySnapshot(
        case.binding, d.ArmingState.ARMED, 'operator-b', case.evidence.valid_until,
        False, 2, False, False,
    )
    loss = d.AuthorityLost(
        case.binding, d.AuthorityLossReason.CONTEXT_CHANGED, 1, 'operator-a', 'retired-lease',
    )
    retired = replace(
        armed, arming_state=d.ArmingState.DISARMED, lease_owner=None,
        lease_expires_at=None, binding_retired=True,
    )
    result = d.AuthorityResult(retired, losses=(loss,))
    assert result.accepted and result.losses == (loss,)
    with pytest.raises(ValueError):
        d.AuthorityResult(armed, losses=(loss,))


@pytest.mark.parametrize(('denial_name', 'flag'), [
    ('CONTEXT_CHANGED', 'binding_retired'),
    ('CLOCK_UNHEALTHY', 'clock_faulted'),
])
def test_permanent_state_denials_require_snapshot_flag_even_without_losses(denial_name, flag, authority_case):
    case = authority_case()
    d = case.domain
    healthy = case.authority.snapshot(case.binding).snapshot
    denial = d.AuthorityDenial[denial_name]
    latched = replace(healthy, **{flag: True})
    result = d.AuthorityResult(latched, denial=denial)
    assert result.denial is denial and result.losses == ()
    with pytest.raises(ValueError):
        d.AuthorityResult(healthy, denial=denial)


def test_returned_lease_cannot_reuse_a_token_revoked_by_historical_loss(authority_case):
    case = authority_case()
    d = case.domain
    lease = d.ControlLease(
        'current-lease', 'operator-a', case.binding, case.evidence.observed_at,
        case.evidence.valid_until, case.evidence.capabilities, 2,
    )
    snapshot = d.AuthoritySnapshot(
        case.binding, d.ArmingState.DISARMED, lease.session_id, lease.expires_at,
        False, 2, False, False,
    )
    ended = d.AuthorityLost(
        case.binding, d.AuthorityLossReason.RELEASED, 1, lease.session_id, 'old-lease',
    )
    valid = d.AuthorityResult(snapshot, lease=lease, losses=(ended,))
    assert valid.accepted and valid.lease == lease and valid.losses == (ended,)
    with pytest.raises(ValueError):
        d.AuthorityResult(snapshot, lease=lease, losses=(replace(ended, lease_id=lease.lease_id),))
