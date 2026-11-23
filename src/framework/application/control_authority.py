"""Synchronized in-memory leases, activation, and protective revocation."""
from __future__ import annotations

from dataclasses import dataclass, replace
from threading import Lock
from uuid import uuid4

from framework.domain.capabilities import CapabilitySnapshot, _validate_token
from framework.domain.control import (
    ActivationEvidence, ArmingState, AuthorityDenial, AuthorityLost, AuthorityLossReason,
    AuthorityResult, AuthoritySnapshot, ControlBinding, ControlLease, ExecutionHold, PolicyFailure,
    SessionAuthorization, _require_count, _require_type, _validate_instant, _value_tuple,
    policy_failures,
)
from framework.domain.time import MonotonicInstant
from framework.domain.values import DeviceId, RobotId

from .ports import MonotonicClock

__all__ = ['ControlAuthority', 'UnknownControlBinding']

_PROTECTIVE_REASONS = frozenset({
    AuthorityLossReason.STOP_REQUESTED, AuthorityLossReason.EXECUTION_TIMEOUT,
    AuthorityLossReason.CRITICAL_FAULT, AuthorityLossReason.CONTEXT_CHANGED,
})
_SESSION_REASONS = frozenset({
    AuthorityLossReason.SESSION_LOST, AuthorityLossReason.PERMISSION_REVOKED,
})


class UnknownControlBinding(KeyError):
    """The logical robot has no binding configured with this authority owner."""


@dataclass(slots=True)
class _Entry:
    binding: ControlBinding
    lease: ControlLease | None = None
    arming_state: ArmingState = ArmingState.DISARMED
    adopted_capabilities: CapabilitySnapshot | None = None
    revoke_generation: int = 0
    retired: bool = False
    hold: ExecutionHold | None = None
    hold_revision: int = 0


class ControlAuthority:
    """Serialize authority decisions and return protective effects to the caller."""

    def __init__(
        self, bindings: list[ControlBinding] | tuple[ControlBinding, ...],
        clock: MonotonicClock, *, max_lease_ns: int,
    ) -> None:
        """Copy trusted bindings and establish the protection clock's initial reading."""
        bindings = _value_tuple(bindings, ControlBinding, 'bindings')
        _require_count(max_lease_ns, 'max_lease_ns', minimum=1)
        entries: dict[RobotId, _Entry] = {}
        writable_devices: set[DeviceId] = set()
        for binding in sorted(bindings, key=lambda binding: binding.robot_id.value):
            if binding.robot_id in entries:
                raise ValueError(f'duplicate robot ID {binding.robot_id.value!r}')
            if not binding.read_only:
                device_id = binding.backend.device_id
                if device_id in writable_devices:
                    raise ValueError(f'multiple writable bindings for device {device_id.value!r}')
                writable_devices.add(device_id)
            entries[binding.robot_id] = _Entry(binding)

        if not callable(getattr(clock, 'now', None)):
            raise TypeError('clock must provide a callable now() method')
        initial = clock.now()
        _validate_instant(initial, 'clock reading')

        self._entries = entries
        self._sessions: dict[str, tuple[RobotId, ...] | None] = {}
        self._clock = clock
        self._last_reading = initial
        self._clock_faulted = False
        self._max_lease_ns = max_lease_ns
        # Allocate the namespace outside the lock. Counters give fresh IDs using only memory.
        self._token_namespace = uuid4().hex
        self._token_sequence = 0
        self._lock = Lock()

    def register_session(self, authorization: SessionAuthorization) -> None:
        """Register the trusted registrar's immutable scope for a fresh session ID."""
        _require_type(authorization, SessionAuthorization, 'authorization')
        with self._lock:
            if authorization.session_id in self._sessions:
                raise ValueError('session ID is already registered or revoked')
            for robot_id in authorization.robot_ids:
                self._lookup(robot_id)
            self._sessions[authorization.session_id] = authorization.robot_ids

    def acquire(
        self, binding: ControlBinding, session_id: str, evidence: ActivationEvidence, *, duration_ns: int,
    ) -> AuthorityResult:
        _validate_token(session_id, 'session_id')
        _require_type(evidence, ActivationEvidence, 'evidence')
        self._validate_duration(duration_ns)
        with self._lock:
            entry, now, rejected = self._enter(binding, session_id)
            if rejected is not None:
                return rejected
            assert now is not None
            rejected = self._evaluate_evidence(entry, evidence, now)
            if rejected is not None:
                return rejected
            if entry.hold is not None:
                return self._result(entry, denial=AuthorityDenial.EXECUTION_UNRESOLVED)
            lease = ControlLease(
                self._new_token(), session_id, entry.binding, now, self._deadline(now, duration_ns),
                evidence.capabilities, entry.revoke_generation,
            )
            if entry.adopted_capabilities is None:
                entry.adopted_capabilities = evidence.capabilities
            entry.lease = lease
            return self._result(entry, lease=lease)

    def renew(
        self, binding: ControlBinding, session_id: str, lease_id: str,
        evidence: ActivationEvidence, *, duration_ns: int,
    ) -> AuthorityResult:
        self._validate_lease_request(session_id, lease_id)
        _require_type(evidence, ActivationEvidence, 'evidence')
        self._validate_duration(duration_ns)
        with self._lock:
            entry, now, rejected = self._enter(binding, session_id, lease_id)
            if rejected is not None:
                return rejected
            assert now is not None and entry.lease is not None
            rejected = self._evaluate_evidence(entry, evidence, now)
            if rejected is not None:
                return rejected
            expiry = self._deadline(now, duration_ns)
            if expiry.tick_ns > entry.lease.expires_at.tick_ns:
                entry.lease = replace(entry.lease, expires_at=expiry)
            return self._result(entry, lease=entry.lease)

    def activate(
        self, binding: ControlBinding, session_id: str, lease_id: str,
        evidence: ActivationEvidence, *, confirmed: bool,
    ) -> AuthorityResult:
        _require_type(confirmed, bool, 'confirmed')
        return self._check_execution(binding, session_id, lease_id, evidence, confirmed=confirmed)

    def check(
        self, binding: ControlBinding, session_id: str, lease_id: str, evidence: ActivationEvidence,
    ) -> AuthorityResult:
        """Check current authority for synchronous consumption by the coordinator."""
        return self._check_execution(binding, session_id, lease_id, evidence, confirmed=None)

    def release(self, binding: ControlBinding, session_id: str, lease_id: str) -> AuthorityResult:
        return self._end_lease(binding, session_id, lease_id, AuthorityLossReason.RELEASED)

    def deactivate(self, binding: ControlBinding, session_id: str, lease_id: str) -> AuthorityResult:
        return self._end_lease(binding, session_id, lease_id, AuthorityLossReason.DEACTIVATED)

    def snapshot(self, binding: ControlBinding) -> AuthorityResult:
        """Observe the binding after doing its required protection-clock maintenance."""
        with self._lock:
            entry = self._entry_for(binding)
            if entry.binding != binding:
                return self._result(entry, denial=AuthorityDenial.STALE_BINDING)
            _, denial, losses = self._maintain(entry)
            return self._result(entry, denial=denial, losses=losses)

    def poll_expired(self) -> tuple[AuthorityLost, ...]:
        """Read the shared clock once and hand off every new expiry in robot order."""
        with self._lock:
            now, losses = self._read_clock()
            if now is None:
                return losses
            return tuple(
                self._lose(entry, AuthorityLossReason.EXPIRED)
                for entry in self._entries.values() if self._expired(entry, now)
            )

    def revoke(
        self, binding: ControlBinding, reason: AuthorityLossReason, *, lease_id: str | None = None,
    ) -> AuthorityResult:
        """Apply a trusted protective loss, optionally scoped to one original lease."""
        _require_type(reason, AuthorityLossReason, 'reason')
        if lease_id is not None:
            _validate_token(lease_id, 'lease_id')
        if reason not in _PROTECTIVE_REASONS:
            raise ValueError('reason must be a trusted binding revocation reason')
        if reason is AuthorityLossReason.EXECUTION_TIMEOUT and lease_id is None:
            raise ValueError('execution timeout requires the original lease ID')
        with self._lock:
            entry = self._entry_for(binding)
            if entry.binding != binding:
                return self._result(entry, denial=AuthorityDenial.STALE_BINDING)
            if lease_id is not None and (entry.lease is None or entry.lease.lease_id != lease_id):
                return self._result(entry, denial=AuthorityDenial.STALE_LEASE)
            return self._result(entry, losses=(self._lose(entry, reason),))

    def revoke_session(self, session_id: str, reason: AuthorityLossReason) -> tuple[AuthorityLost, ...]:
        """Permanently revoke a registered session and hand off all its current leases."""
        _validate_token(session_id, 'session_id')
        _require_type(reason, AuthorityLossReason, 'reason')
        if reason not in _SESSION_REASONS:
            raise ValueError('reason must be a session revocation reason')
        with self._lock:
            if self._sessions[session_id] is None:
                return ()
            self._sessions[session_id] = None
            return tuple(
                self._lose(entry, reason)
                for entry in self._entries.values()
                if entry.lease is not None and entry.lease.session_id == session_id
            )

    def mark_execution_unresolved(self, binding: ControlBinding) -> tuple[ExecutionHold, AuthorityResult]:
        """Advance the aggregate hold and atomically revoke current authority."""
        with self._lock:
            entry = self._entry_for(binding)
            if entry.binding != binding:
                raise ValueError('unresolved execution requires the exact configured binding')
            entry.hold_revision += 1
            hold = ExecutionHold(entry.binding, self._new_token(), entry.hold_revision)
            entry.hold = hold
            loss = self._lose(entry, AuthorityLossReason.EXECUTION_UNRESOLVED)
            return hold, self._result(entry, losses=(loss,))

    def resolve_execution(self, hold: ExecutionHold) -> AuthorityResult:
        """Accept the coordinator's disposition for every cause in the current hold."""
        _require_type(hold, ExecutionHold, 'hold')
        with self._lock:
            entry = self._entry_for(hold.binding)
            if entry.binding != hold.binding:
                return self._result(entry, denial=AuthorityDenial.STALE_BINDING)
            if entry.hold != hold:
                return self._result(entry, denial=AuthorityDenial.STALE_HOLD)
            entry.hold = None
            return self._result(entry)

    def _check_execution(
        self, binding: ControlBinding, session_id: str, lease_id: str,
        evidence: ActivationEvidence, *, confirmed: bool | None,
    ) -> AuthorityResult:
        self._validate_lease_request(session_id, lease_id)
        _require_type(evidence, ActivationEvidence, 'evidence')
        with self._lock:
            entry, now, rejected = self._enter(binding, session_id, lease_id)
            if rejected is not None:
                return rejected
            assert now is not None
            rejected = self._evaluate_evidence(entry, evidence, now)
            if rejected is not None:
                return rejected
            if confirmed is None:
                denial = None if entry.arming_state is ArmingState.ARMED else AuthorityDenial.NOT_ARMED
                return self._result(entry, denial=denial)
            if not confirmed:
                return self._result(entry, denial=AuthorityDenial.CONFIRMATION_REQUIRED)
            failures = policy_failures(entry.binding, evidence, now, require_stopped=True)
            if failures:
                return self._result(entry, denial=AuthorityDenial.INELIGIBLE, policy_failures=failures)
            entry.arming_state = ArmingState.ARMED
            return self._result(entry)

    def _end_lease(
        self, binding: ControlBinding, session_id: str, lease_id: str, reason: AuthorityLossReason,
    ) -> AuthorityResult:
        self._validate_lease_request(session_id, lease_id)
        with self._lock:
            entry, _, rejected = self._enter(binding, session_id, lease_id)
            if rejected is not None:
                return rejected
            return self._result(entry, losses=(self._lose(entry, reason),))

    @staticmethod
    def _validate_lease_request(session_id: str, lease_id: str) -> None:
        _validate_token(session_id, 'session_id')
        _validate_token(lease_id, 'lease_id')

    def _validate_duration(self, duration_ns: int) -> None:
        _require_count(duration_ns, 'duration_ns', minimum=1)
        if duration_ns > self._max_lease_ns:
            raise ValueError('duration_ns exceeds max_lease_ns')

    def _lookup(self, robot_id: RobotId) -> _Entry:
        entry = self._entries.get(robot_id)
        if entry is None:
            raise UnknownControlBinding(robot_id.value)
        return entry

    def _entry_for(self, binding: ControlBinding) -> _Entry:
        _require_type(binding, ControlBinding, 'binding')
        return self._lookup(binding.robot_id)

    def _new_token(self) -> str:
        self._token_sequence += 1
        return f'{self._token_namespace}-{self._token_sequence:x}'

    @staticmethod
    def _deadline(now: MonotonicInstant, duration_ns: int) -> MonotonicInstant:
        return MonotonicInstant(now.clock_id, now.tick_ns + duration_ns)

    def _enter(
        self, binding: ControlBinding, session_id: str, lease_id: str | None = None,
    ) -> tuple[_Entry, MonotonicInstant | None, AuthorityResult | None]:
        """Run binding, maintenance, session and lease gates under the caller's lock."""
        entry = self._entry_for(binding)
        if entry.binding != binding:
            return entry, None, self._result(entry, denial=AuthorityDenial.STALE_BINDING)
        now, maintenance_denial, losses = self._maintain(entry)
        scope = self._sessions.get(session_id)
        lease = entry.lease
        if scope is None or binding.robot_id not in scope:
            denial = AuthorityDenial.FORBIDDEN
        elif maintenance_denial is AuthorityDenial.CLOCK_UNHEALTHY:
            denial = AuthorityDenial.CLOCK_UNHEALTHY
        elif entry.binding.read_only:
            denial = AuthorityDenial.READ_ONLY
        elif maintenance_denial is AuthorityDenial.LEASE_EXPIRED:
            denial = AuthorityDenial.LEASE_EXPIRED
        elif entry.retired:
            denial = AuthorityDenial.CONTEXT_CHANGED
        elif lease_id is None:
            denial = AuthorityDenial.BUSY if lease is not None else None
        elif lease is None:
            denial = AuthorityDenial.LEASE_REQUIRED
        elif lease.session_id != session_id:
            denial = AuthorityDenial.FORBIDDEN
        elif lease.lease_id != lease_id:
            denial = AuthorityDenial.STALE_LEASE
        else:
            denial = None
        rejected = self._result(entry, denial=denial, losses=losses) if denial is not None else None
        return entry, now, rejected

    def _evaluate_evidence(
        self, entry: _Entry, evidence: ActivationEvidence, now: MonotonicInstant,
    ) -> AuthorityResult | None:
        scoped = evidence.binding == entry.binding
        adopted = entry.adopted_capabilities
        if scoped and adopted is not None and evidence.capabilities != adopted:
            loss = self._lose(entry, AuthorityLossReason.CONTEXT_CHANGED)
            return self._result(entry, denial=AuthorityDenial.CONTEXT_CHANGED, losses=(loss,))
        failures = policy_failures(entry.binding, evidence, now, require_stopped=False)
        if not failures:
            return None
        losses = ()
        if scoped and entry.lease is not None:
            losses = (self._lose(entry, AuthorityLossReason.CRITICAL_FAULT),)
        return self._result(entry, denial=AuthorityDenial.INELIGIBLE, policy_failures=failures, losses=losses)

    def _maintain(
        self, entry: _Entry,
    ) -> tuple[MonotonicInstant | None, AuthorityDenial | None, tuple[AuthorityLost, ...]]:
        now, losses = self._read_clock()
        if now is None:
            return None, AuthorityDenial.CLOCK_UNHEALTHY, losses
        if self._expired(entry, now):
            return now, AuthorityDenial.LEASE_EXPIRED, (self._lose(entry, AuthorityLossReason.EXPIRED),)
        return now, None, ()

    def _read_clock(self) -> tuple[MonotonicInstant | None, tuple[AuthorityLost, ...]]:
        if self._clock_faulted:
            return None, ()
        try:
            now = self._clock.now()
            _validate_instant(now, 'clock reading')
            now.elapsed_ns_since(self._last_reading)
        except Exception:
            self._clock_faulted = True
            return None, tuple(
                self._lose(entry, AuthorityLossReason.CLOCK_FAULT)
                for entry in self._entries.values() if entry.lease is not None
            )
        self._last_reading = now
        return now, ()

    @staticmethod
    def _expired(entry: _Entry, now: MonotonicInstant) -> bool:
        return entry.lease is not None and now.tick_ns >= entry.lease.expires_at.tick_ns

    @staticmethod
    def _lose(entry: _Entry, reason: AuthorityLossReason) -> AuthorityLost:
        lease = entry.lease
        entry.lease = None
        entry.arming_state = ArmingState.DISARMED
        entry.revoke_generation += 1
        if reason is AuthorityLossReason.CONTEXT_CHANGED:
            entry.retired = True
        return AuthorityLost(
            entry.binding, reason, entry.revoke_generation,
            lease.session_id if lease is not None else None,
            lease.lease_id if lease is not None else None,
        )

    def _result(
        self, entry: _Entry, *, lease: ControlLease | None = None, denial: AuthorityDenial | None = None,
        policy_failures: tuple[PolicyFailure, ...] = (), losses: tuple[AuthorityLost, ...] = (),
    ) -> AuthorityResult:
        current = entry.lease
        snapshot = AuthoritySnapshot(
            entry.binding, entry.arming_state, current.session_id if current is not None else None,
            current.expires_at if current is not None else None, entry.hold is not None,
            entry.revoke_generation, self._clock_faulted, entry.retired,
        )
        return AuthorityResult(snapshot, lease, denial, policy_failures, losses)
