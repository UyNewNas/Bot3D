"""T30/activation: only explicit, qualified activation permits an armed check."""
from dataclasses import replace

import pytest

from framework.domain.capabilities import PoseGoalCapability, UnavailableReason
from framework.domain.discovery import MotionState
from framework.domain.time import MonotonicInstant
from framework.domain.values import RobotId

pytestmark = pytest.mark.t30_activation


def test_ready_and_leased_moving_are_disarmed_until_qualified_confirmation(authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    moving = replace(case.evidence, motion_state=MotionState.MOVING, standstill_verified=None)
    grant = authority.acquire(case.binding, 'operator-a', moving, duration_ns=10)
    token = grant.lease.lease_id
    denied = authority.check(case.binding, 'operator-a', token, moving)
    assert denied.denial is d.AuthorityDenial.NOT_ARMED and not denied.losses
    no_confirmation = authority.activate(case.binding, 'operator-a', token, moving, confirmed=False)
    assert no_confirmation.denial is d.AuthorityDenial.CONFIRMATION_REQUIRED and not no_confirmation.losses
    assert authority.check(
        case.binding, 'operator-a', token, case.evidence,
    ).denial is d.AuthorityDenial.NOT_ARMED
    confirmed = authority.activate(case.binding, 'operator-a', token, case.evidence, confirmed=True)
    assert confirmed.accepted and confirmed.snapshot.arming_state is d.ArmingState.ARMED
    assert confirmed.lease is None
    repeated = authority.activate(case.binding, 'operator-a', token, case.evidence, confirmed=True)
    assert repeated.accepted and repeated.snapshot == confirmed.snapshot


@pytest.mark.parametrize('field,failure', [
    ('identity_verified', 'IDENTITY_UNVERIFIED'),
    ('mode_permitted', 'MODE_NOT_PERMITTED'),
    ('calibration_valid', 'CALIBRATION_INVALID'),
    ('local_protection_ready', 'LOCAL_PROTECTION_UNREADY'),
    ('native_control_exclusive', 'NATIVE_CONTROL_UNCONFIRMED'),
])
@pytest.mark.parametrize('value', [False, None])
def test_continuous_facts_need_explicit_true(field, failure, value, authority_case):
    case = authority_case()
    d = case.domain
    result = case.authority.acquire(
        case.binding, 'operator-a', replace(case.evidence, **{field: value}), duration_ns=10,
    )
    assert result.denial is d.AuthorityDenial.INELIGIBLE
    assert result.policy_failures == (d.PolicyFailure[failure],)
    assert not result.losses and result.snapshot.revoke_generation == 0


@pytest.mark.parametrize('readiness', ['OFFLINE', 'INITIALIZING', 'DEGRADED', 'FAULTED'])
def test_only_ready_permits_acquire(readiness, authority_case):
    case = authority_case()
    d = case.domain
    result = case.authority.acquire(
        case.binding, 'operator-a', replace(case.evidence, readiness=d.Readiness[readiness]),
        duration_ns=10,
    )
    assert result.denial is d.AuthorityDenial.INELIGIBLE
    assert result.policy_failures == (d.PolicyFailure.NOT_READY,)


def test_unavailable_pose_goal_cannot_grant_initial_authority(authority_case):
    case = authority_case()
    d = case.domain
    capability = replace(
        case.evidence.capabilities,
        pose_goal=PoseGoalCapability((UnavailableReason.EXECUTION_UNAVAILABLE,)),
    )
    result = case.authority.acquire(
        case.binding, 'operator-a', replace(case.evidence, capabilities=capability), duration_ns=10,
    )
    assert result.denial is d.AuthorityDenial.INELIGIBLE
    assert result.policy_failures == (d.PolicyFailure.CAPABILITY_UNAVAILABLE,)


@pytest.mark.parametrize(('motion', 'standstill', 'failures'), [
    (MotionState.UNKNOWN, True, ('NOT_STOPPED',)),
    (MotionState.MOVING, None, ('NOT_STOPPED', 'STANDSTILL_UNCONFIRMED')),
    (MotionState.STOPPED, False, ('STANDSTILL_UNCONFIRMED',)),
    (MotionState.STOPPED, None, ('STANDSTILL_UNCONFIRMED',)),
])
def test_activation_parking_prerequisites_do_not_revoke_lease(motion, standstill, failures, authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    evidence = replace(case.evidence, motion_state=motion, standstill_verified=standstill)
    grant = authority.acquire(case.binding, 'operator-a', evidence, duration_ns=10)
    attempt = authority.activate(case.binding, 'operator-a', grant.lease.lease_id, evidence, confirmed=True)
    assert attempt.denial is d.AuthorityDenial.INELIGIBLE
    assert attempt.policy_failures == tuple(d.PolicyFailure[failure] for failure in failures)
    assert attempt.snapshot == grant.snapshot and not attempt.losses


def test_armed_motion_can_continue_and_renew_without_parking(authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    grant = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    token = grant.lease.lease_id
    authority.activate(case.binding, 'operator-a', token, case.evidence, confirmed=True)
    moving = replace(case.evidence, motion_state=MotionState.MOVING, standstill_verified=None)
    case.clock.advance_ns(9)
    renewed = authority.renew(case.binding, 'operator-a', token, moving, duration_ns=10)
    assert renewed.accepted and renewed.snapshot.arming_state is d.ArmingState.ARMED
    assert renewed.lease.expires_at.tick_ns == 19
    check = authority.check(case.binding, 'operator-a', token, moving)
    assert check.accepted and check.lease is None and not check.losses


def test_foreign_evidence_aggregates_continuous_failures_without_revoking(authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    grant = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    foreign = replace(
        case.evidence, binding=case.other, motion_state=MotionState.UNKNOWN,
        capabilities=replace(case.evidence.capabilities, revision=2), local_protection_ready=False,
    )
    result = authority.activate(case.binding, 'operator-a', grant.lease.lease_id, foreign, confirmed=True)
    assert result.denial is d.AuthorityDenial.INELIGIBLE
    assert result.policy_failures == (d.PolicyFailure.EVIDENCE_BINDING, d.PolicyFailure.LOCAL_PROTECTION_UNREADY)
    assert result.snapshot == grant.snapshot and not result.losses


@pytest.mark.parametrize(('operation', 'window', 'failure'), [
    ('activate', ('control-clock', 1, 1000), 'EVIDENCE_FUTURE'),
    ('check', ('control-clock', 0, 1), 'EVIDENCE_EXPIRED'),
    ('renew', ('source-clock', 0, 1000), 'EVIDENCE_CLOCK'),
])
def test_evidence_time_loss_precedes_operation_specific_gates(operation, window, failure, authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    grant = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    if failure == 'EVIDENCE_EXPIRED':
        case.clock.advance_ns(1)
    clock_id, observed, valid_until = window
    invalid = replace(
        case.evidence, observed_at=MonotonicInstant(clock_id, observed),
        valid_until=MonotonicInstant(clock_id, valid_until),
    )
    options = {'activate': {'confirmed': False}, 'check': {}, 'renew': {'duration_ns': 10}}
    result = getattr(authority, operation)(
        case.binding, 'operator-a', grant.lease.lease_id, invalid, **options[operation],
    )
    assert result.denial is d.AuthorityDenial.INELIGIBLE
    assert result.policy_failures == (d.PolicyFailure[failure],)
    assert result.losses == (
        d.AuthorityLost(case.binding, d.AuthorityLossReason.CRITICAL_FAULT, 1, 'operator-a', grant.lease.lease_id),
    )
    assert result.snapshot.lease_owner is None and not result.snapshot.binding_retired
    restored = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    assert restored.accepted and restored.snapshot.arming_state is d.ArmingState.DISARMED


@pytest.mark.parametrize(('change', 'value'), [
    ('revision', 2),
    ('configuration_revision', 'fixture-config-2'),
    ('mode', 'manual'),
    ('pose_goal', PoseGoalCapability((UnavailableReason.EXECUTION_UNAVAILABLE,))),
])
def test_current_holder_capability_context_loss_permanently_retires_binding(change, value, authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    grant = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    token = grant.lease.lease_id
    assert authority.activate(case.binding, 'operator-a', token, case.evidence, confirmed=True).accepted
    changed = replace(case.evidence, capabilities=replace(case.evidence.capabilities, **{change: value}))
    result = authority.check(case.binding, 'operator-a', token, changed)
    assert result.denial is d.AuthorityDenial.CONTEXT_CHANGED
    assert result.snapshot.binding_retired and result.snapshot.arming_state is d.ArmingState.DISARMED
    assert result.losses == (
        d.AuthorityLost(case.binding, d.AuthorityLossReason.CONTEXT_CHANGED, 1, 'operator-a', token),
    )
    for evidence in (case.evidence, changed):
        retry = authority.acquire(case.binding, 'operator-b', evidence, duration_ns=10)
        assert retry.denial is d.AuthorityDenial.CONTEXT_CHANGED and not retry.losses
    maintained = authority.snapshot(case.binding)
    assert maintained.accepted and maintained.snapshot.binding_retired


@pytest.mark.parametrize('termination', ['release', 'expiry'])
def test_adopted_context_survives_end_of_lease(termination, authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    grant = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    if termination == 'release':
        assert authority.release(case.binding, 'operator-a', grant.lease.lease_id).accepted
    else:
        case.clock.advance_ns(10)
        assert authority.poll_expired()[0].reason is d.AuthorityLossReason.EXPIRED
    changed = replace(case.evidence, capabilities=replace(case.evidence.capabilities, revision=2))
    result = authority.acquire(case.binding, 'operator-b', changed, duration_ns=10)
    assert result.denial is d.AuthorityDenial.CONTEXT_CHANGED and result.snapshot.binding_retired
    assert result.losses == (d.AuthorityLost(case.binding, d.AuthorityLossReason.CONTEXT_CHANGED, 2, None, None),)
    retry = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    assert retry.denial is d.AuthorityDenial.CONTEXT_CHANGED and not retry.losses


def test_hold_does_not_hide_continuous_failure_or_allow_activation(authority_case):
    case = authority_case(extra_bindings=True)
    authority, d = case.authority, case.domain
    grant = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    authority.mark_execution_unresolved(case.binding)
    invalid = replace(case.evidence, identity_verified=False)
    denied = authority.acquire(case.binding, 'operator-a', invalid, duration_ns=10)
    assert denied.denial is d.AuthorityDenial.INELIGIBLE
    assert authority.activate(
        case.binding, 'operator-a', grant.lease.lease_id, case.evidence, confirmed=True,
    ).denial is d.AuthorityDenial.LEASE_REQUIRED
    authority.register_session(d.SessionAuthorization('allowed-mirror', [case.mirror.robot_id]))
    assert authority.activate(
        case.mirror, 'allowed-mirror', grant.lease.lease_id, case.evidence, confirmed=True,
    ).denial is d.AuthorityDenial.READ_ONLY


def test_pure_policy_returns_all_failures_in_order(authority_case):
    case = authority_case()
    d = case.domain
    evidence = replace(
        case.evidence, binding=case.other, readiness=d.Readiness.FAULTED, motion_state=MotionState.UNKNOWN,
        capabilities=replace(
            case.evidence.capabilities,
            pose_goal=PoseGoalCapability((UnavailableReason.EXECUTION_UNAVAILABLE,)),
        ),
        identity_verified=False, mode_permitted=None, calibration_valid=False,
        local_protection_ready=None, native_control_exclusive=False, standstill_verified=None,
    )
    assert d.policy_failures(
        case.binding, evidence, MonotonicInstant('unrelated-clock', 1001), require_stopped=True,
    ) == (
        d.PolicyFailure.EVIDENCE_BINDING, d.PolicyFailure.EVIDENCE_CLOCK,
        d.PolicyFailure.NOT_READY, d.PolicyFailure.CAPABILITY_UNAVAILABLE,
        d.PolicyFailure.IDENTITY_UNVERIFIED, d.PolicyFailure.MODE_NOT_PERMITTED,
        d.PolicyFailure.CALIBRATION_INVALID, d.PolicyFailure.LOCAL_PROTECTION_UNREADY,
        d.PolicyFailure.NATIVE_CONTROL_UNCONFIRMED, d.PolicyFailure.NOT_STOPPED,
        d.PolicyFailure.STANDSTILL_UNCONFIRMED,
    )


def test_domain_values_reject_subclasses_nested_text_and_invalid_windows(authority_case):
    case = authority_case()
    d = case.domain

    class Text(str):
        pass

    class Instant(MonotonicInstant):
        pass

    class Evidence(d.ActivationEvidence):
        pass

    class Backend(type(case.binding.backend)):
        pass

    class Capabilities(type(case.evidence.capabilities)):
        pass

    with pytest.raises(TypeError):
        replace(case.binding, robot_id=RobotId(Text('alternate')))
    backend = case.binding.backend
    with pytest.raises(TypeError):
        replace(case.binding, backend=Backend(backend.device_id, backend.backend_id, backend.backend_kind, backend.backend_epoch))
    capability = case.evidence.capabilities
    with pytest.raises(TypeError):
        replace(case.evidence, capabilities=Capabilities(
            capability.revision, capability.configuration_revision, capability.mode, capability.pose_goal,
        ))
    with pytest.raises(TypeError):
        replace(case.evidence, observed_at=MonotonicInstant(Text('control-clock'), 0))
    with pytest.raises(TypeError):
        replace(case.evidence, observed_at=Instant('control-clock', 0))
    with pytest.raises(TypeError):
        replace(case.evidence, identity_verified=1)
    with pytest.raises(ValueError):
        replace(case.evidence, valid_until=MonotonicInstant('foreign-clock', 1000))
    with pytest.raises(ValueError):
        replace(case.evidence, valid_until=case.evidence.observed_at)
    with pytest.raises(TypeError):
        d.SessionAuthorization(Text('operator'), [case.binding.robot_id])
    with pytest.raises(ValueError):
        d.SessionAuthorization('operator', [case.binding.robot_id, case.binding.robot_id])
    with pytest.raises(ValueError):
        d.SessionAuthorization('space in id', [])
    fields = {field: getattr(case.evidence, field) for field in case.evidence.__dataclass_fields__}
    with pytest.raises(TypeError):
        d.policy_failures(case.binding, Evidence(**fields), case.clock.now(), require_stopped=False)
    with pytest.raises(TypeError):
        d.policy_failures(case.binding, case.evidence, case.clock.now(), require_stopped=1)


def test_public_snapshot_and_result_reject_impossible_authority(authority_case):
    case = authority_case()
    authority, d = case.authority, case.domain
    grant = authority.acquire(case.binding, 'operator-a', case.evidence, duration_ns=10)
    lease, snapshot = grant.lease, grant.snapshot
    for change in (
        {'lease_expires_at': None}, {'execution_blocked': True}, {'clock_faulted': True},
        {'binding_retired': True}, {'binding': case.mirror}, {'revoke_generation': -1},
    ):
        with pytest.raises(ValueError):
            replace(snapshot, **change)
    with pytest.raises(ValueError):
        replace(snapshot, arming_state=d.ArmingState.ARMED, lease_owner=None, lease_expires_at=None)
    for change in ({'binding': case.mirror}, {'expires_at': lease.issued_at}, {'grant_generation': -1}):
        with pytest.raises(ValueError):
            replace(lease, **change)
    with pytest.raises(TypeError):
        replace(lease, grant_generation=True)
    with pytest.raises(ValueError):
        replace(grant, denial=d.AuthorityDenial.FORBIDDEN)
    for change in (
        {'binding': case.other}, {'lease_owner': 'operator-b'},
        {'lease_expires_at': MonotonicInstant('control-clock', 11)}, {'revoke_generation': 1},
    ):
        with pytest.raises(ValueError):
            d.AuthorityResult(replace(snapshot, **change), lease=lease)
    with pytest.raises(ValueError):
        d.AuthorityResult(snapshot, denial=d.AuthorityDenial.INELIGIBLE)
    failures = [d.PolicyFailure.NOT_READY, d.PolicyFailure.IDENTITY_UNVERIFIED]
    for invalid in (list(reversed(failures)), failures * 2):
        with pytest.raises(ValueError):
            d.AuthorityResult(snapshot, denial=d.AuthorityDenial.INELIGIBLE, policy_failures=invalid)
    with pytest.raises(ValueError):
        d.AuthorityResult(snapshot, denial=d.AuthorityDenial.FORBIDDEN, policy_failures=failures)
    rejected = d.AuthorityResult(snapshot, denial=d.AuthorityDenial.INELIGIBLE, policy_failures=failures)
    failures.clear()
    assert rejected.policy_failures == (d.PolicyFailure.NOT_READY, d.PolicyFailure.IDENTITY_UNVERIFIED)
