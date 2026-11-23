"""Immutable control authority values and pure activation policy."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeVar

from .capabilities import CapabilitySnapshot, _validate_token
from .discovery import BackendIdentity, MotionState, _validate_robot_id
from .time import MonotonicInstant
from .values import RobotId

__all__ = [
    'Readiness', 'ArmingState', 'ControlBinding', 'SessionAuthorization',
    'ActivationEvidence', 'ControlLease', 'AuthoritySnapshot', 'AuthorityLossReason',
    'AuthorityLost', 'ExecutionHold', 'AuthorityDenial', 'PolicyFailure', 'AuthorityResult',
    'policy_failures',
]


class Readiness(StrEnum):
    OFFLINE = 'OFFLINE'
    INITIALIZING = 'INITIALIZING'
    READY = 'READY'
    DEGRADED = 'DEGRADED'
    FAULTED = 'FAULTED'


class ArmingState(StrEnum):
    DISARMED = 'DISARMED'
    ARMED = 'ARMED'


class AuthorityLossReason(StrEnum):
    RELEASED = 'RELEASED'
    EXPIRED = 'EXPIRED'
    SESSION_LOST = 'SESSION_LOST'
    PERMISSION_REVOKED = 'PERMISSION_REVOKED'
    DEACTIVATED = 'DEACTIVATED'
    STOP_REQUESTED = 'STOP_REQUESTED'
    EXECUTION_TIMEOUT = 'EXECUTION_TIMEOUT'
    EXECUTION_UNRESOLVED = 'EXECUTION_UNRESOLVED'
    CRITICAL_FAULT = 'CRITICAL_FAULT'
    CONTEXT_CHANGED = 'CONTEXT_CHANGED'
    CLOCK_FAULT = 'CLOCK_FAULT'


class AuthorityDenial(StrEnum):
    FORBIDDEN = 'FORBIDDEN'
    READ_ONLY = 'READ_ONLY'
    BUSY = 'BUSY'
    LEASE_REQUIRED = 'LEASE_REQUIRED'
    STALE_LEASE = 'STALE_LEASE'
    LEASE_EXPIRED = 'LEASE_EXPIRED'
    STALE_BINDING = 'STALE_BINDING'
    INELIGIBLE = 'INELIGIBLE'
    CONTEXT_CHANGED = 'CONTEXT_CHANGED'
    CONFIRMATION_REQUIRED = 'CONFIRMATION_REQUIRED'
    NOT_ARMED = 'NOT_ARMED'
    EXECUTION_UNRESOLVED = 'EXECUTION_UNRESOLVED'
    STALE_HOLD = 'STALE_HOLD'
    CLOCK_UNHEALTHY = 'CLOCK_UNHEALTHY'


class PolicyFailure(StrEnum):
    EVIDENCE_BINDING = 'EVIDENCE_BINDING'
    EVIDENCE_CLOCK = 'EVIDENCE_CLOCK'
    EVIDENCE_FUTURE = 'EVIDENCE_FUTURE'
    EVIDENCE_EXPIRED = 'EVIDENCE_EXPIRED'
    NOT_READY = 'NOT_READY'
    CAPABILITY_UNAVAILABLE = 'CAPABILITY_UNAVAILABLE'
    IDENTITY_UNVERIFIED = 'IDENTITY_UNVERIFIED'
    MODE_NOT_PERMITTED = 'MODE_NOT_PERMITTED'
    CALIBRATION_INVALID = 'CALIBRATION_INVALID'
    LOCAL_PROTECTION_UNREADY = 'LOCAL_PROTECTION_UNREADY'
    NATIVE_CONTROL_UNCONFIRMED = 'NATIVE_CONTROL_UNCONFIRMED'
    NOT_STOPPED = 'NOT_STOPPED'
    STANDSTILL_UNCONFIRMED = 'STANDSTILL_UNCONFIRMED'


_Item = TypeVar('_Item')


def _require_type(value: object, expected: type, name: str) -> None:
    if type(value) is not expected:
        raise TypeError(f'{name} must be a concrete {expected.__name__}')


def _require_count(value: int, name: str, *, minimum: int = 0) -> None:
    _require_type(value, int, name)
    if value < minimum:
        raise ValueError(f'{name} must be at least {minimum}')


def _value_tuple(
    values: tuple[_Item, ...] | list[_Item], expected: type[_Item], name: str,
) -> tuple[_Item, ...]:
    if type(values) not in (list, tuple):
        raise TypeError(f'{name} must be a list or tuple')
    items = tuple(values)
    for item in items:
        _require_type(item, expected, f'{name} item')
    return items


def _validate_instant(value: MonotonicInstant, name: str) -> None:
    _require_type(value, MonotonicInstant, name)
    _validate_token(value.clock_id, f'{name}.clock_id')


def _validate_window(start: MonotonicInstant, end: MonotonicInstant, start_name: str, end_name: str) -> None:
    _validate_instant(start, start_name)
    _validate_instant(end, end_name)
    if start.clock_id != end.clock_id or start.tick_ns >= end.tick_ns:
        raise ValueError(f'{end_name} must be later than {start_name} in the same clock domain')


@dataclass(frozen=True, slots=True)
class ControlBinding:
    """Trusted logical and physical scope of a control authority decision."""

    robot_id: RobotId
    backend: BackendIdentity
    read_only: bool

    def __post_init__(self) -> None:
        _validate_robot_id(self.robot_id)
        _require_type(self.backend, BackendIdentity, 'backend')
        _require_type(self.read_only, bool, 'read_only')


@dataclass(frozen=True, slots=True)
class SessionAuthorization:
    """Robot scope supplied by the trusted session registrar."""

    session_id: str
    robot_ids: tuple[RobotId, ...] | list[RobotId]

    def __post_init__(self) -> None:
        _validate_token(self.session_id, 'session_id')
        robots = _value_tuple(self.robot_ids, RobotId, 'robot_ids')
        for robot in robots:
            _validate_robot_id(robot)
        if len(set(robots)) != len(robots):
            raise ValueError('robot_ids must not contain duplicates')
        object.__setattr__(self, 'robot_ids', robots)


@dataclass(frozen=True, slots=True)
class ActivationEvidence:
    """One binding's trusted projected facts and their protection-clock window."""

    binding: ControlBinding
    capabilities: CapabilitySnapshot
    readiness: Readiness
    motion_state: MotionState
    observed_at: MonotonicInstant
    valid_until: MonotonicInstant
    identity_verified: bool | None
    mode_permitted: bool | None
    calibration_valid: bool | None
    local_protection_ready: bool | None
    native_control_exclusive: bool | None
    standstill_verified: bool | None

    def __post_init__(self) -> None:
        _require_type(self.binding, ControlBinding, 'binding')
        _require_type(self.capabilities, CapabilitySnapshot, 'capabilities')
        _require_type(self.readiness, Readiness, 'readiness')
        _require_type(self.motion_state, MotionState, 'motion_state')
        _validate_window(self.observed_at, self.valid_until, 'observed_at', 'valid_until')
        for name in (
            'identity_verified', 'mode_permitted', 'calibration_valid',
            'local_protection_ready', 'native_control_exclusive', 'standstill_verified',
        ):
            value = getattr(self, name)
            if value is not None:
                _require_type(value, bool, name)


@dataclass(frozen=True, slots=True)
class ControlLease:
    lease_id: str = field(repr=False)
    session_id: str
    binding: ControlBinding
    issued_at: MonotonicInstant
    expires_at: MonotonicInstant
    capabilities: CapabilitySnapshot
    grant_generation: int

    def __post_init__(self) -> None:
        _validate_token(self.lease_id, 'lease_id')
        _validate_token(self.session_id, 'session_id')
        _require_type(self.binding, ControlBinding, 'binding')
        _validate_window(self.issued_at, self.expires_at, 'issued_at', 'expires_at')
        _require_type(self.capabilities, CapabilitySnapshot, 'capabilities')
        _require_count(self.grant_generation, 'grant_generation')
        if self.binding.read_only:
            raise ValueError('lease requires a writable binding')


@dataclass(frozen=True, slots=True)
class AuthoritySnapshot:
    binding: ControlBinding
    arming_state: ArmingState
    lease_owner: str | None
    lease_expires_at: MonotonicInstant | None
    execution_blocked: bool
    revoke_generation: int
    clock_faulted: bool
    binding_retired: bool

    def __post_init__(self) -> None:
        _require_type(self.binding, ControlBinding, 'binding')
        _require_type(self.arming_state, ArmingState, 'arming_state')
        _require_type(self.execution_blocked, bool, 'execution_blocked')
        _require_count(self.revoke_generation, 'revoke_generation')
        _require_type(self.clock_faulted, bool, 'clock_faulted')
        _require_type(self.binding_retired, bool, 'binding_retired')
        if self.lease_owner is not None:
            _validate_token(self.lease_owner, 'lease_owner')
        if self.lease_expires_at is not None:
            _validate_instant(self.lease_expires_at, 'lease_expires_at')
        if (self.lease_owner is None) != (self.lease_expires_at is None):
            raise ValueError('lease_owner and lease_expires_at must be present together')
        if self.lease_owner is not None and (
            self.binding.read_only or self.execution_blocked or self.clock_faulted or self.binding_retired
        ):
            raise ValueError('lease owner requires a writable, unblocked and healthy binding')
        if self.arming_state is ArmingState.ARMED and self.lease_owner is None:
            raise ValueError('arming requires a lease owner')


_LEASE_LOSS_REASONS = frozenset({
    AuthorityLossReason.RELEASED, AuthorityLossReason.EXPIRED, AuthorityLossReason.SESSION_LOST,
    AuthorityLossReason.PERMISSION_REVOKED, AuthorityLossReason.DEACTIVATED,
    AuthorityLossReason.EXECUTION_TIMEOUT, AuthorityLossReason.CLOCK_FAULT,
})


@dataclass(frozen=True, slots=True)
class AuthorityLost:
    """Original scope of authority to be handed off to the trusted coordinator."""

    binding: ControlBinding
    reason: AuthorityLossReason
    revoke_generation: int
    session_id: str | None
    lease_id: str | None = field(repr=False)

    def __post_init__(self) -> None:
        _require_type(self.binding, ControlBinding, 'binding')
        _require_type(self.reason, AuthorityLossReason, 'reason')
        _require_count(self.revoke_generation, 'revoke_generation', minimum=1)
        if self.session_id is not None:
            _validate_token(self.session_id, 'session_id')
        if self.lease_id is not None:
            _validate_token(self.lease_id, 'lease_id')
        if (self.session_id is None) != (self.lease_id is None):
            raise ValueError('session_id and lease_id must be present together')
        if self.session_id is None and self.reason in _LEASE_LOSS_REASONS:
            raise ValueError('this loss reason requires the original lease')
        if self.session_id is not None and self.binding.read_only:
            raise ValueError('lease loss requires a writable binding')


@dataclass(frozen=True, slots=True)
class ExecutionHold:
    """Latest aggregate unresolved-execution revision known to the coordinator."""

    binding: ControlBinding
    hold_id: str = field(repr=False)
    revision: int

    def __post_init__(self) -> None:
        _require_type(self.binding, ControlBinding, 'binding')
        _validate_token(self.hold_id, 'hold_id')
        _require_count(self.revision, 'revision', minimum=1)


@dataclass(frozen=True, slots=True)
class AuthorityResult:
    snapshot: AuthoritySnapshot
    lease: ControlLease | None = None
    denial: AuthorityDenial | None = None
    policy_failures: tuple[PolicyFailure, ...] | list[PolicyFailure] = ()
    losses: tuple[AuthorityLost, ...] | list[AuthorityLost] = ()

    def __post_init__(self) -> None:
        _require_type(self.snapshot, AuthoritySnapshot, 'snapshot')
        if self.denial is not None:
            _require_type(self.denial, AuthorityDenial, 'denial')
            if self.denial is AuthorityDenial.CONTEXT_CHANGED and not self.snapshot.binding_retired:
                raise ValueError('context change denial requires a retired binding')
            if self.denial is AuthorityDenial.CLOCK_UNHEALTHY and not self.snapshot.clock_faulted:
                raise ValueError('unhealthy clock denial requires a faulted snapshot')
        if self.lease is not None:
            _require_type(self.lease, ControlLease, 'lease')
            if self.denial is not None:
                raise ValueError('a denied result cannot carry a lease')
            if (
                self.lease.binding != self.snapshot.binding
                or self.lease.session_id != self.snapshot.lease_owner
                or self.lease.expires_at != self.snapshot.lease_expires_at
                or self.lease.grant_generation != self.snapshot.revoke_generation
            ):
                raise ValueError('returned lease must match the authority snapshot')
        failures = _value_tuple(self.policy_failures, PolicyFailure, 'policy_failures')
        if bool(failures) != (self.denial is AuthorityDenial.INELIGIBLE):
            raise ValueError('only INELIGIBLE results must carry policy failures')
        if failures != tuple(failure for failure in PolicyFailure if failure in failures):
            raise ValueError('policy failures must be unique and in policy order')
        losses = _value_tuple(self.losses, AuthorityLost, 'losses')
        if len({loss.binding.robot_id for loss in losses}) != len(losses):
            raise ValueError('losses must have distinct robot IDs')
        for loss in losses:
            if loss.reason is AuthorityLossReason.CLOCK_FAULT and not self.snapshot.clock_faulted:
                raise ValueError('clock fault losses require a faulted snapshot')
            if self.lease is not None and loss.lease_id == self.lease.lease_id:
                raise ValueError('a returned lease cannot also be recorded as lost')
            if loss.binding == self.snapshot.binding:
                if loss.reason is AuthorityLossReason.CONTEXT_CHANGED and not self.snapshot.binding_retired:
                    raise ValueError('context change loss requires a retired binding')
                if loss.revoke_generation > self.snapshot.revoke_generation:
                    raise ValueError('loss generation cannot exceed the current snapshot generation')
            elif loss.reason is not AuthorityLossReason.CLOCK_FAULT:
                raise ValueError('only clock fault losses can span different bindings')
        object.__setattr__(self, 'policy_failures', failures)
        object.__setattr__(self, 'losses', losses)

    @property
    def accepted(self) -> bool:
        return self.denial is None


def policy_failures(
    binding: ControlBinding, evidence: ActivationEvidence, now: MonotonicInstant, *, require_stopped: bool,
) -> tuple[PolicyFailure, ...]:
    """Evaluate continuous prerequisites and optionally the conditions for activation."""
    _require_type(binding, ControlBinding, 'binding')
    _require_type(evidence, ActivationEvidence, 'evidence')
    _validate_instant(now, 'now')
    _require_type(require_stopped, bool, 'require_stopped')

    failures = []
    if evidence.binding != binding:
        failures.append(PolicyFailure.EVIDENCE_BINDING)
    if evidence.observed_at.clock_id != now.clock_id:
        failures.append(PolicyFailure.EVIDENCE_CLOCK)
    elif now.tick_ns < evidence.observed_at.tick_ns:
        failures.append(PolicyFailure.EVIDENCE_FUTURE)
    elif now.tick_ns >= evidence.valid_until.tick_ns:
        failures.append(PolicyFailure.EVIDENCE_EXPIRED)

    prerequisites = (
        (evidence.readiness is Readiness.READY, PolicyFailure.NOT_READY),
        (evidence.capabilities.pose_goal.available, PolicyFailure.CAPABILITY_UNAVAILABLE),
        (evidence.identity_verified, PolicyFailure.IDENTITY_UNVERIFIED),
        (evidence.mode_permitted, PolicyFailure.MODE_NOT_PERMITTED),
        (evidence.calibration_valid, PolicyFailure.CALIBRATION_INVALID),
        (evidence.local_protection_ready, PolicyFailure.LOCAL_PROTECTION_UNREADY),
        (evidence.native_control_exclusive, PolicyFailure.NATIVE_CONTROL_UNCONFIRMED),
    )
    if require_stopped:
        prerequisites += (
            (evidence.motion_state is MotionState.STOPPED, PolicyFailure.NOT_STOPPED),
            (evidence.standstill_verified, PolicyFailure.STANDSTILL_UNCONFIRMED),
        )
    failures.extend(failure for fact, failure in prerequisites if fact is not True)
    return tuple(failures)
