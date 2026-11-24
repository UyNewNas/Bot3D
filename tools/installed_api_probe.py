"""Exercise ordinary installed APIs in each caller's isolated consumer."""
from dataclasses import replace
import sys

from framework.adapters.clocks import ManualMonotonicClock, SystemMonotonicClock
from framework.adapters.mock_robot import ReadOnlyMockBackend
from framework.adapters.memory_journal import InMemoryJournal
from framework.application.control_authority import ControlAuthority
from framework.application.ports import JournalPort, MonotonicClock
from framework.application.registry import RobotRegistry
from framework.domain.capabilities import CapabilityInputs, UnavailableReason, revise_capabilities
from framework.domain.control import (
    ActivationEvidence, ArmingState, AuthorityDenial, AuthorityLossReason, ControlBinding,
    Readiness, SessionAuthorization,
)
from framework.domain.discovery import (
    BackendDescription, BackendIdentity, BackendKind, BackendState, MotionState, ReadOnlyObservation,
)
from framework.domain.geometry import Quaternion, RigidTransform
from framework.domain.commands import (
    CommandContext, CommandKey, CommandTiming, PoseCommand, PoseConstraints,
)
from framework.domain.journal import (
    BackendReceipt, CommandAcceptance, CommandEvent, CommandState, DispatchIntent,
    IdempotencyConflict, JournalEntry, ReconciliationFact, ResultCertainty,
)
from framework.domain.targets import PoseGoal
from framework.domain.time import ClockDomainMismatch, MonotonicInstant
from framework.domain.values import DeviceId, FrameId, RobotId, ToolId, Vector3, mm_to_m

assert sys.version_info[:2] == (3, 12)
clock = ManualMonotonicClock(clock_id='installed-probe-clock')
start = clock.now()
assert start == MonotonicInstant('installed-probe-clock', 0)
clock.advance_ns(9)
assert clock.now().elapsed_ns_since(start) == 9
assert isinstance(SystemMonotonicClock().now(), MonotonicInstant)
try:
    start.elapsed_ns_since(MonotonicInstant('other-clock', 0))
except ClockDomainMismatch:
    pass
else:
    raise AssertionError('cross-clock arithmetic accepted')

base = FrameId('arm-fixture/base')
world = FrameId('cell/world')
robot = RobotId('arm-fixture')
tool = ToolId('tool0')
identity = Quaternion.from_xyzw([0, 0, 0, 1])
goal = PoseGoal(robot, base, tool, Vector3(mm_to_m(1000), 0, 0), identity)
moved = goal.transformed(RigidTransform(world, base, Vector3(1, 2, 3), identity))
assert (moved.robot_id, moved.frame_id, moved.tool_id) == (robot, world, tool)
assert moved.position_m.as_tuple() == (2.0, 2.0, 3.0)
assert moved.orientation_xyzw == identity and goal.frame_id == base

backend = BackendIdentity(DeviceId('mock-device-a'), 'mock-backend-a', BackendKind.SIM, 'fixture-epoch-a')
inputs = CapabilityInputs(True, True, True, True, True, 'fixture-config-1', 'automatic')
unknown = ReadOnlyObservation(None, MotionState.UNKNOWN, None, None)
mock = ReadOnlyMockBackend(BackendDescription(backend, 'Fixture arm', inputs), BackendState(backend, unknown))
registry = RobotRegistry()
registered = registry.register(robot, mock)
assert registry.discover() == (registered,)
state = registry.read_state(robot)
assert registered.binding.robot_id == robot and registered.binding.backend == backend
assert state.binding == registered.binding and state.observation == unknown
assert state.capability_revision == registered.capabilities.revision == 1
assert registered.capabilities.pose_goal.available is False
assert registered.capabilities.pose_goal.reasons == (UnavailableReason.EXECUTION_UNAVAILABLE,)

# Synthetic trusted inputs for an independent control authority, with no backend attached.
protection_clock = ManualMonotonicClock(clock_id='control-clock')
authority_clock: MonotonicClock = protection_clock
binding = ControlBinding(robot, backend, False)
authority = ControlAuthority([binding], authority_clock, max_lease_ns=100)
authority.register_session(SessionAuthorization('operator-a', [robot]))
evidence = ActivationEvidence(
    binding, revise_capabilities(inputs), Readiness.READY, MotionState.STOPPED,
    protection_clock.now(), MonotonicInstant('control-clock', 1000), True, True, True, True, True, True,
)
grant = authority.acquire(binding, 'operator-a', evidence, duration_ns=10)
assert grant.accepted and grant.snapshot.arming_state is ArmingState.DISARMED
assert grant.lease.expires_at == MonotonicInstant('control-clock', 10)
active = authority.activate(binding, 'operator-a', grant.lease.lease_id, evidence, confirmed=True)
assert active.accepted and active.snapshot.arming_state is ArmingState.ARMED
protection_clock.advance_ns(10)
expired = authority.snapshot(binding)
assert expired.denial is AuthorityDenial.LEASE_EXPIRED
assert expired.snapshot.arming_state is ArmingState.DISARMED and expired.snapshot.lease_owner is None
assert len(expired.losses) == 1
assert expired.losses[0].reason is AuthorityLossReason.EXPIRED
assert expired.losses[0].binding == binding and expired.losses[0].lease_id == grant.lease.lease_id
assert authority.poll_expired() == ()

# Journal facts are independent of an expired lease; an application authorizes
# the reader first. These synthetic facts do not submit a robot operation.
command = PoseCommand(
    CommandKey(robot, '12345678-1234-5678-1234-567812345678'), 'probe-request',
    backend.backend_epoch, grant.lease.lease_id, 1, goal,
    CommandContext('model-1', 'scene-1', 'cal-1'),
    CommandTiming('control-clock', 100, 200, 300), PoseConstraints(.1, .005, .05),
)
journal: JournalPort = InMemoryJournal()
candidate = CommandAcceptance(command, backend, 'operator-a', protection_clock.now(), 'validation-1')
written = journal.record_acceptance(candidate)
assert written.created and written.record.state is None and not journal.retention.durable
retry = journal.record_acceptance(replace(candidate, command=replace(command, request_id='retry')))
assert not retry.created and retry.record == written.record
try:
    journal.record_acceptance(replace(candidate, command=replace(command, lease_id='different-lease')))
except IdempotencyConflict:
    pass
else:
    raise AssertionError('changed execution meaning overwrote the journal')

payloads = (
    CommandEvent(CommandState.ACCEPTED, ResultCertainty.PENDING, 'checks confirmed'),
    CommandEvent(CommandState.PLANNING, ResultCertainty.PENDING, 'planning begun'),
    DispatchIntent('attempt-1', 'a' * 64, 'original-query'),
    CommandEvent(CommandState.DISPATCHING, ResultCertainty.PENDING, 'intent confirmed'),
    BackendReceipt('attempt-1', 'original-handle'),
    CommandEvent(CommandState.EXECUTING, ResultCertainty.PENDING, 'backend accepted'),
    CommandEvent(CommandState.INTERRUPTED, ResultCertainty.UNKNOWN, 'feedback lost'),
    ReconciliationFact('attempt-1', 'later-observation', 'original handle subsequently queried'),
)
for revision, payload in enumerate(payloads):
    entry = JournalEntry(f'probe-entry-{revision}', MonotonicInstant('control-clock', 11 + revision), payload)
    current = journal.append(command.key, entry, expected_revision=revision)
assert current.state is CommandState.INTERRUPTED and current.certainty is ResultCertainty.UNKNOWN
assert current.receipt.backend_handle == 'original-handle'
assert current.intent.query_key == 'original-query' and current.revision == 8
assert written.record.state is None and written.record.revision == 0
assert journal.record_acceptance(candidate).record == current
