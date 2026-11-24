"""Function-scoped clocks; no sleep, device connection or global time patching."""
import pytest

from framework.adapters.clocks import ManualMonotonicClock


@pytest.fixture
def projection_case():
    """Artificial two-joint source, with explicit non-device timing limits."""
    from dataclasses import replace
    from importlib import import_module
    from types import SimpleNamespace
    from framework.domain.discovery import BackendIdentity, BackendKind, JointObservation, MotionState
    from framework.domain.geometry import Quaternion
    from framework.domain.targets import PoseGoal
    from framework.domain.time import MonotonicInstant
    from framework.domain.values import DeviceId, FrameId, RobotId, ToolId, Vector3

    def build(*, mapped=True, **config_changes):
        try:
            d = import_module('framework.domain.projection')
            a = import_module('framework.application.state_projection')
        except ModuleNotFoundError as exc:
            if exc.name not in {'framework.domain.projection', 'framework.application.state_projection'}:
                raise
            raise AssertionError('missing installed state projection API') from exc
        robot = RobotId('arm-fixture')
        backend = BackendIdentity(DeviceId('device-a'), 'backend-a', BackendKind.SIM, 'epoch-a')
        context = d.ProjectionContext(1, 'model-1', 'scene-1', 'cal-1')
        config = d.ProjectionConfig(
            robot_id=robot, backend=backend, source_id='encoder-a',
            source_clock_id='source-clock', protection_clock_id='control-clock',
            joint_names=['j1', 'j2'], frame_id=FrameId('cell/world'), tool_id=ToolId('tool0'),
            feedback_origin=d.DataOrigin.SIMULATED,
            max_source_age_ns=30, max_receive_age_ns=20, max_clock_uncertainty_ns=2,
            stationary_window_ns=10, max_sample_gap_ns=6,
            max_velocity_rad_s=.01, max_position_delta_rad=.001,
        )
        config = replace(config, **config_changes)
        clock = ManualMonotonicClock(clock_id='control-clock')
        def at(tick):
            return MonotonicInstant('control-clock', tick)
        mapping = d.ClockMapping('source-clock', 0, 0, at(0), at(1000), 'sync-1')
        projection = a.StateProjection(config, context)
        if mapped and config.source_clock_id != config.protection_clock_id:
            projection.set_mapping(mapping, now=at(0))
        pose = d.ToolPose(config.frame_id, config.tool_id, Vector3(1, 0, .25), Quaternion(0, 0, 0, 1))
        goal = PoseGoal(robot, config.frame_id, config.tool_id, Vector3(2, 0, .5), Quaternion(0, 0, 0, 1))
        def sample(seq=1, tick=0, *, received=None, position=0, velocity=0, **changes):
            joints = d.JointFeedback([
                JointObservation('j1', position, velocity), JointObservation('j2', 0, 0),
            ], d.DataOrigin.SIMULATED)
            controller = d.ControllerFeedback(MotionState.STOPPED, 'automatic', False, False,
                                              d.DataOrigin.SIMULATED)
            value = d.FeedbackSample(robot, backend, context, 'encoder-a', seq,
                                     MonotonicInstant(config.source_clock_id, tick),
                                     at(tick if received is None else received), joints,
                                     d.PoseFeedback(pose, d.DataOrigin.SIMULATED), controller)
            return replace(value, **changes)
        def feed(seq=1, tick=0, *, now=None, **changes):
            value = sample(seq, tick, **changes)
            return projection.ingest(value, now=at(value.received_at.tick_ns if now is None else now))
        return SimpleNamespace(domain=d, application=a, config=config, context=context,
                               backend=backend, robot=robot, clock=clock, at=at, mapping=mapping,
                               projection=projection, pose=pose, goal=goal, sample=sample, feed=feed)
    return build


@pytest.fixture
def command_case():
    """Fixed submitted command; imports inside the test give an explicit RED."""
    from importlib import import_module
    from types import SimpleNamespace

    from framework.domain.geometry import Quaternion
    from framework.domain.targets import PoseGoal
    from framework.domain.values import FrameId, RobotId, ToolId, Vector3

    def build():
        try:
            d = import_module('framework.domain.commands')
        except ModuleNotFoundError as exc:
            if exc.name != 'framework.domain.commands':
                raise
            raise AssertionError('missing installed command digest API') from exc
        robot = RobotId('arm-fixture')
        command = d.PoseCommand(
            key=d.CommandKey(robot, '12345678-1234-5678-1234-567812345678'),
            request_id='request-1', backend_epoch='epoch-a', lease_id='lease-a',
            capability_revision=1,
            goal=PoseGoal(robot, FrameId('cell/world'), ToolId('tool0'),
                          Vector3(1, 0, .25), Quaternion(0, 0, 0, 1)),
            context=d.CommandContext('model-1', 'scene-1', 'cal-1'),
            timing=d.CommandTiming('control-clock', 100, 200, 300),
            constraints=d.PoseConstraints(.1, .005, .05),
        )
        return SimpleNamespace(domain=d, command=command)

    return build


@pytest.fixture
def journal_case(command_case):
    from importlib import import_module
    from types import SimpleNamespace

    from framework.domain.discovery import BackendIdentity, BackendKind
    from framework.domain.time import MonotonicInstant
    from framework.domain.values import DeviceId

    def build():
        case = command_case()
        try:
            d = import_module('framework.domain.journal')
            adapter = import_module('framework.adapters.memory_journal')
        except ModuleNotFoundError as exc:
            if exc.name not in {'framework.domain.journal', 'framework.adapters.memory_journal'}:
                raise
            raise AssertionError('missing installed journal API') from exc
        acceptance = d.CommandAcceptance(
            case.command,
            BackendIdentity(DeviceId('device-a'), 'backend-a', BackendKind.SIM, 'epoch-a'),
            'operator-a', MonotonicInstant('control-clock', 0), 'validation-1',
        )
        journal = adapter.InMemoryJournal()

        def entry(payload, event_id='event-1', tick=1):
            return d.JournalEntry(event_id, MonotonicInstant('control-clock', tick), payload)

        def event(state, certainty=None, reason='fixture evidence'):
            return d.CommandEvent(state, certainty or d.ResultCertainty.PENDING, reason)

        def planning():
            journal.record_acceptance(acceptance)
            journal.append(case.command.key, entry(event(d.CommandState.ACCEPTED), 'accepted', 1),
                           expected_revision=0)
            return journal.append(case.command.key, entry(event(d.CommandState.PLANNING), 'planning', 2),
                                  expected_revision=1)

        def executing():
            planning()
            journal.append(case.command.key, entry(d.DispatchIntent('attempt-1', 'a' * 64, 'query-1'), 'intent', 3),
                           expected_revision=2)
            journal.append(case.command.key, entry(event(d.CommandState.DISPATCHING), 'dispatching', 4),
                           expected_revision=3)
            journal.append(case.command.key, entry(d.BackendReceipt('attempt-1', 'handle-1'), 'receipt', 5),
                           expected_revision=4)
            return journal.append(case.command.key, entry(event(d.CommandState.EXECUTING), 'executing', 6),
                                  expected_revision=5)

        return SimpleNamespace(domain=d, command=case.command, acceptance=acceptance, journal=journal,
                               entry=entry, event=event, planning=planning, executing=executing)

    return build


@pytest.fixture
def manual_clock():
    return ManualMonotonicClock(clock_id='test/protection')


@pytest.fixture
def source_clock():
    return ManualMonotonicClock(clock_id='test/source')


@pytest.fixture
def authority_case():
    """Build the fixed authority fixture when called inside a test body."""
    from importlib import import_module
    from types import SimpleNamespace

    from framework.domain.capabilities import CapabilityInputs, revise_capabilities
    from framework.domain.discovery import BackendIdentity, BackendKind, MotionState
    from framework.domain.time import MonotonicInstant
    from framework.domain.values import DeviceId, RobotId

    def build(*, clock=None, extra_bindings=False):
        try:
            domain = import_module('framework.domain.control')
            application = import_module('framework.application.control_authority')
        except ModuleNotFoundError as exc:
            if exc.name not in {
                'framework.domain.control', 'framework.application.control_authority',
            }:
                raise
            raise AssertionError(f'missing installed control authority API: {exc.name}') from exc

        robot = RobotId('arm-fixture')
        backend = BackendIdentity(
            DeviceId('mock-device-a'), 'mock-backend-a', BackendKind.SIM, 'fixture-epoch-a',
        )
        binding = domain.ControlBinding(robot, backend, False)
        mirror = domain.ControlBinding(RobotId('arm-fixture-mirror'), backend, True)
        other = domain.ControlBinding(
            RobotId('other-fixture'),
            BackendIdentity(
                DeviceId('mock-device-b'), 'mock-backend-b', BackendKind.SIM, 'fixture-epoch-b',
            ),
            False,
        )
        capabilities = revise_capabilities(
            CapabilityInputs(True, True, True, True, True, 'fixture-config-1', 'automatic'),
        )
        evidence = domain.ActivationEvidence(
            binding, capabilities, domain.Readiness.READY, MotionState.STOPPED,
            MonotonicInstant('control-clock', 0), MonotonicInstant('control-clock', 1000),
            True, True, True, True, True, True,
        )
        if clock is None:
            clock = ManualMonotonicClock(clock_id='control-clock')
        bindings = [binding, mirror, other] if extra_bindings else [binding]
        authority = application.ControlAuthority(bindings, clock, max_lease_ns=100)
        for session_id, robot_ids in [('operator-a', [robot]), ('operator-b', [robot]), ('viewer', [])]:
            authority.register_session(domain.SessionAuthorization(session_id, robot_ids))
        return SimpleNamespace(
            domain=domain, application=application, authority=authority, clock=clock,
            binding=binding, mirror=mirror, other=other, evidence=evidence,
        )

    return build
