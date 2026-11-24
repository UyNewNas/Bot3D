"""Exercise ordinary installed APIs in each caller's isolated consumer."""
from dataclasses import replace
import sys

from framework.adapters.clocks import ManualMonotonicClock, SystemMonotonicClock
from framework.adapters.mock_robot import ReadOnlyMockBackend
from framework.adapters.memory_journal import InMemoryJournal
from framework.application.control_authority import ControlAuthority
from framework.application.ports import JournalPort, MonotonicClock
from framework.application.registry import RobotRegistry
from framework.application.state_projection import StateProjection
from framework.domain.capabilities import CapabilityInputs, UnavailableReason, revise_capabilities
from framework.domain.control import (
    ActivationEvidence, ArmingState, AuthorityDenial, AuthorityLossReason, ControlBinding,
    Readiness, SessionAuthorization,
)
from framework.domain.discovery import (
    BackendDescription, BackendIdentity, BackendKind, BackendState, JointObservation, MotionState, ReadOnlyObservation,
)
from framework.domain.geometry import Quaternion, RigidTransform
from framework.domain.commands import (
    CommandContext, CommandKey, CommandTiming, PoseCommand, PoseConstraints,
)
from framework.domain.journal import (
    BackendReceipt, CommandAcceptance, CommandEvent, CommandState, DispatchIntent,
    IdempotencyConflict, JournalEntry, ReconciliationFact, ResultCertainty,
)
from framework.domain.projection import (
    ClockMapping, ControllerFeedback, DataOrigin, DataQuality, FeedbackSample,
    ForwardKinematicsResult, JointFeedback, ProjectionConfig, ProjectionContext,
    ProjectionDisposition, ProjectionTarget, ToolPose,
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

# Projected observations are separate from target display and command facts.
# Every threshold here is an artificial fixture, never a device safety default.
projection_context = ProjectionContext(1, 'model-1', 'scene-1', 'cal-1')
projection_config = ProjectionConfig(
    robot_id=robot, backend=backend, source_id='joint-feedback',
    source_clock_id='source-clock', protection_clock_id='projection-clock',
    joint_names=['j1'], frame_id=base, tool_id=tool, feedback_origin=DataOrigin.SIMULATED,
    max_source_age_ns=30, max_receive_age_ns=20, max_clock_uncertainty_ns=2,
    stationary_window_ns=10, max_sample_gap_ns=6,
    max_velocity_rad_s=.01, max_position_delta_rad=.001,
)
projection = StateProjection(projection_config, projection_context)
projection_clock = ManualMonotonicClock(clock_id='projection-clock')
projection.set_mapping(ClockMapping(
    'source-clock', 0, 0, projection_clock.now(), MonotonicInstant('projection-clock', 1000), 'sync-1',
), now=projection_clock.now())
target_state = projection.set_target(ProjectionTarget('probe-command', goal, projection_context),
                                     now=projection_clock.now())
assert target_state.tool_pose.value is None and target_state.motion_state is MotionState.UNKNOWN
for source_seq in (1, 2, 3):
    sample = FeedbackSample(
        robot, backend, projection_context, 'joint-feedback', source_seq,
        MonotonicInstant('source-clock', projection_clock.now().tick_ns), projection_clock.now(),
        JointFeedback([JointObservation('j1', 0, 0)], DataOrigin.SIMULATED), None,
        ControllerFeedback(MotionState.STOPPED, 'automatic', False, None, DataOrigin.SIMULATED),
    )
    projected = projection.ingest(sample, now=projection_clock.now()).state
    if source_seq < 3:
        assert projected.stationary is None
        projection_clock.advance_ns(5)
assert projected.motion_state is MotionState.STOPPED and projected.stationary.end_seq == 3
assert projected.controller.value.protective_stop_active is None
fk = ForwardKinematicsResult(robot, backend, projection_context, 'joint-feedback', 3,
                             ToolPose(base, tool, Vector3(1, 0, 0), identity))
assert projection.apply_fk(fk, now=projection_clock.now())
assert projection.snapshot(now=projection_clock.now()).tool_pose.origin is DataOrigin.DERIVED
projection_clock.advance_ns(20)
duplicate = projection.ingest(replace(sample, received_at=projection_clock.now()), now=projection_clock.now())
assert duplicate.disposition is ProjectionDisposition.DUPLICATE
assert duplicate.state.source_age_ns == duplicate.state.receive_age_ns == 20
assert duplicate.state.transport_age_ns == 0
assert duplicate.state.joints.quality is DataQuality.STALE and duplicate.state.stationary is None
assert duplicate.state.motion_state is MotionState.UNKNOWN
assert written.record.state is None and written.record.revision == 0
assert journal.record_acceptance(candidate).record == current
