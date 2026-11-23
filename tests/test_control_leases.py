"""T01/leases: exclusive scoped control and serialized lease transitions."""
from dataclasses import replace
from queue import Queue
from threading import Barrier, Event, Thread

import pytest

from framework.domain.values import RobotId

pytestmark = pytest.mark.t01_leases


def test_writable_device_uniqueness_ignores_backend_and_epoch(authority_case):
    case = authority_case()
    duplicate = replace(
        case.binding, robot_id=case.mirror.robot_id,
        backend=replace(case.binding.backend, backend_id='another-backend', backend_epoch='other-epoch'),
    )
    with pytest.raises(ValueError):
        case.application.ControlAuthority([case.binding, duplicate], case.clock, max_lease_ns=100)
    with pytest.raises(ValueError):
        case.application.ControlAuthority([case.binding, case.binding], case.clock, max_lease_ns=100)


def test_read_only_mirror_and_distinct_device_have_independent_authority(authority_case):
    case = authority_case(extra_bindings=True)
    authority, d = case.authority, case.domain
    authority.register_session(d.SessionAuthorization('operator-extra', [case.mirror.robot_id, case.other.robot_id]))
    primary = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    readonly = authority.acquire(
        case.mirror, 'operator-extra', replace(case.evidence, binding=case.mirror), duration_ns=10,
    )
    independent = authority.acquire(
        case.other, 'operator-extra', replace(case.evidence, binding=case.other), duration_ns=10,
    )
    assert readonly.denial is d.AuthorityDenial.READ_ONLY
    assert readonly.snapshot.lease_owner is None
    assert primary.accepted and independent.accepted
    assert independent.lease.binding == case.other
    assert authority.snapshot(case.binding).snapshot.lease_owner == 'operator-a'


def test_session_registration_is_scoped_copied_and_atomic(authority_case):
    case = authority_case(extra_bindings=True)
    authority, d = case.authority, case.domain
    robots = [case.binding.robot_id]
    authorization = d.SessionAuthorization('operator-extra', robots)
    robots[:] = [case.other.robot_id]
    authority.register_session(authorization)
    assert authorization.robot_ids == (case.binding.robot_id,)
    with pytest.raises(ValueError):
        authority.register_session(d.SessionAuthorization('operator-extra', []))
    with pytest.raises(case.application.UnknownControlBinding):
        authority.register_session(
            d.SessionAuthorization('retry', [case.binding.robot_id, RobotId('unknown')]),
        )
    authority.register_session(d.SessionAuthorization('retry', [case.other.robot_id]))
    for actor in ('unregistered', 'viewer', 'retry'):
        assert authority.acquire(
            case.binding, actor, case.evidence, duration_ns=10,
        ).denial is d.AuthorityDenial.FORBIDDEN
    granted = authority.acquire(case.binding, 'operator-extra', case.evidence, duration_ns=10)
    assert granted.accepted and granted.snapshot.lease_owner == 'operator-extra'


def test_initial_snapshot_and_grant_are_disarmed_and_redact_lease_token(authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    initial = authority.snapshot(case.binding)
    assert initial.accepted and initial.lease is None
    assert initial.snapshot == d.AuthoritySnapshot(
        case.binding, d.ArmingState.DISARMED, None, None, False, 0, False, False,
    )
    granted = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    assert granted.accepted
    assert granted.snapshot.arming_state is d.ArmingState.DISARMED
    assert granted.lease.issued_at.tick_ns == 0 and granted.lease.expires_at.tick_ns == 10
    assert granted.lease.binding == case.binding and granted.lease.grant_generation == 0
    assert granted.lease.lease_id not in repr(granted)
    assert initial.snapshot.lease_owner is None


def test_acquire_does_not_renew_same_owner_or_preempt_another(authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    granted = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    for actor in ('operator-a', 'operator-b'):
        duplicate = authority.acquire(
            case.binding, actor, replace(case.evidence, local_protection_ready=False), duration_ns=90,
        )
        assert duplicate.denial is d.AuthorityDenial.BUSY
        assert duplicate.snapshot == granted.snapshot
        assert not duplicate.losses


def test_renew_preserves_original_scope_and_caps_deadline_from_now(authority_case):
    case = authority_case()
    authority = case.authority
    granted = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    token = granted.lease.lease_id
    case.clock.advance_ns(9)
    short = authority.renew(case.binding, 'operator-a', token, case.evidence, duration_ns=1)
    assert short.accepted and short.lease == granted.lease
    extended = authority.renew(case.binding, 'operator-a', token, case.evidence, duration_ns=100)
    assert extended.accepted and extended.lease.expires_at.tick_ns == 109
    assert replace(extended.lease, expires_at=granted.lease.expires_at) == granted.lease
    assert extended.snapshot.lease_expires_at == extended.lease.expires_at


def test_exact_owner_precedes_lease_token_and_old_token_cannot_touch_replacement(authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    granted = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    original = granted.lease.lease_id
    assert authority.release(case.binding, 'operator-b', 'wrong-token').denial is d.AuthorityDenial.FORBIDDEN
    assert authority.release(case.binding, 'operator-a', original).accepted
    assert authority.release(case.binding, 'operator-a', original).denial is d.AuthorityDenial.LEASE_REQUIRED
    replacement = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=20)
    assert replacement.lease.lease_id != original
    assert replacement.lease.grant_generation == 1
    stale = authority.renew(
        case.binding, 'operator-a', original, replace(case.evidence, local_protection_ready=False),
        duration_ns=10,
    )
    assert stale.denial is d.AuthorityDenial.STALE_LEASE
    assert stale.snapshot == replacement.snapshot and not stale.losses


def test_known_stale_full_binding_does_not_touch_live_binding(authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    granted = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    stale_bindings = (
        replace(case.binding, backend=replace(case.binding.backend, backend_epoch='old-epoch')),
        replace(case.binding, read_only=True),
    )
    for stale in stale_bindings:
        result = authority.release(stale, 'operator-a', granted.lease.lease_id)
        assert result.denial is d.AuthorityDenial.STALE_BINDING
        assert result.snapshot == granted.snapshot and not result.losses
    with pytest.raises(case.application.UnknownControlBinding):
        authority.snapshot(replace(case.binding, robot_id=RobotId('not-configured')))


def test_two_contenders_receive_one_grant(authority_case):
    case = authority_case()
    start = Barrier(3)
    results = Queue()

    def try_acquire(session_id):
        start.wait(timeout=5)
        result = case.authority.acquire(case.binding, session_id, case.evidence, duration_ns=10)
        results.put((session_id, result))

    threads = [Thread(target=try_acquire, args=(owner,), daemon=True) for owner in ('operator-a', 'operator-b')]
    for thread in threads:
        thread.start()
    start.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert results.qsize() == 2
    attempts = [results.get_nowait(), results.get_nowait()]
    (winner, grant), = [(session, result) for session, result in attempts if result.accepted]
    denied, = [result for _, result in attempts if not result.accepted]
    assert denied.denial is case.domain.AuthorityDenial.BUSY
    assert denied.snapshot.lease_owner == grant.lease.session_id == winner
    assert case.authority.snapshot(case.binding).snapshot.lease_owner == winner


@pytest.mark.parametrize('first', ['renew', 'release'])
def test_renew_and_release_have_both_serial_outcomes(first, authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    granted = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    token = granted.lease.lease_id
    start = Barrier(3)
    first_completed = Event()
    results = Queue()

    def perform(operation):
        start.wait(timeout=5)
        if operation != first:
            assert first_completed.wait(timeout=5)
        if operation == 'renew':
            result = authority.renew(case.binding, 'operator-a', token, case.evidence, duration_ns=20)
        else:
            result = authority.release(case.binding, 'operator-a', token)
        results.put((operation, result))
        if operation == first:
            first_completed.set()

    threads = [Thread(target=perform, args=(operation,), daemon=True) for operation in ('renew', 'release')]
    for thread in threads:
        thread.start()
    start.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert results.qsize() == 2
    operations = dict([results.get_nowait(), results.get_nowait()])
    assert operations['release'].accepted
    assert operations['release'].losses[0].lease_id == token
    if first == 'renew':
        assert operations['renew'].accepted
        assert operations['renew'].lease.expires_at.tick_ns == 20
    else:
        assert operations['renew'].denial is d.AuthorityDenial.LEASE_REQUIRED
    assert authority.snapshot(case.binding).snapshot.lease_owner is None
