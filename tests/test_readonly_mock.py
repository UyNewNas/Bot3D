"""T46/readonly: backend and Registry expose only read-only observations."""
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from importlib import import_module
from importlib.util import find_spec
from types import SimpleNamespace
from typing import Callable

import pytest

from framework.domain.values import DeviceId, RobotId

pytestmark = pytest.mark.t46_readonly
ROBOT = RobotId('arm-fixture')
DEVICE = DeviceId('mock-device-a')
CONTROL_METHODS = ('connect', 'submit', 'execute', 'plan', 'stop', 'reset', 'activate')


def _discovery():
    module = 'framework.domain.discovery'
    assert find_spec(module) is not None, f'API unavailable: {module}'
    return import_module(module)


def _backend_values(observation=None):
    api = _discovery()
    from framework.domain.capabilities import CapabilityInputs

    identity = api.BackendIdentity(DEVICE, 'mock-backend-a', api.BackendKind.SIM, 'fixture-epoch-a')
    inputs = CapabilityInputs(True, True, True, True, True, 'fixture-config-1', None)
    if observation is None:
        observation = api.ReadOnlyObservation(None, api.MotionState.UNKNOWN, None, None)
    return api.BackendDescription(identity, 'Fixture arm', inputs), api.BackendState(identity, observation)


def test_mock_normalizes_execution_and_returns_frozen_data():
    description, state = _backend_values()
    from framework.adapters.mock_robot import ReadOnlyMockBackend

    mock = ReadOnlyMockBackend(description, state)
    assert mock.describe() == replace(
        description, capability_inputs=replace(description.capability_inputs, execution=False),
    )
    assert description.capability_inputs.execution is True
    assert mock.read_state() == state
    assert all(not hasattr(mock, method) for method in CONTROL_METHODS)
    with pytest.raises(FrozenInstanceError):
        mock.description = description


def test_read_only_port_contract_and_registry_never_use_extra_backend_methods():
    description, state = _backend_values()
    from framework.application.ports import ReadOnlyBackend
    from framework.application.registry import DuplicateRobot, RobotRegistry
    from framework.domain.capabilities import UnavailableReason
    from framework.domain.discovery import RobotDescription, RobotState

    def control_trap():
        pytest.fail('control or connection method was invoked')

    backend = SimpleNamespace(
        describe=lambda: description,
        read_state=lambda: state,
        **dict.fromkeys(CONTROL_METHODS, control_trap),
    )
    registry = RobotRegistry()
    registered = registry.register(ROBOT, backend)

    assert {name for name in vars(ReadOnlyBackend) if not name.startswith('_')} == {'describe', 'read_state'}
    assert all(not hasattr(registry, method) for method in CONTROL_METHODS)
    assert type(registered) is RobotDescription
    for published in (registered, registry.describe(ROBOT), *registry.discover()):
        assert published.binding.read_only is True
        assert published.capabilities.pose_goal.available is False
        assert published.capabilities.pose_goal.reasons == (UnavailableReason.EXECUTION_UNAVAILABLE,)
        assert published.capabilities.revision == 1

    for _ in range(2):
        published_state = registry.read_state(ROBOT)
        assert type(published_state) is RobotState
        assert published_state.binding == registered.binding
        assert published_state.observation == state.observation
        assert published_state.arming_state == 'DISARMED'

    with pytest.raises(DuplicateRobot):
        registry.register(ROBOT, backend)
    assert {field.name for field in fields(registered)} == {'binding', 'name', 'capabilities'}
    assert {field.name for field in fields(registered.binding)} == {'robot_id', 'backend'}
    assert {field.name for field in fields(published_state)} == {
        'binding', 'observation', 'capability_revision',
    }


def test_registered_mock_keeps_missing_physical_feedback_unknown():
    description, state = _backend_values()
    from framework.adapters.mock_robot import ReadOnlyMockBackend
    from framework.application.registry import RobotRegistry
    from framework.domain.discovery import MotionState

    registry = RobotRegistry()
    result = registry.register(ROBOT, ReadOnlyMockBackend(description, state))
    observed = registry.read_state(ROBOT)
    assert observed.binding == result.binding
    assert observed.capability_revision == result.capabilities.revision == 1
    assert observed.arming_state == 'DISARMED'
    assert observed.observation.joints is None
    assert observed.observation.motion_state is MotionState.UNKNOWN
    assert observed.observation.control_mode is None
    assert observed.observation.estop_active is None


def test_registered_mock_returns_explicit_joint_values_without_inference():
    api = _discovery()
    from framework.adapters.mock_robot import ReadOnlyMockBackend
    from framework.application.registry import RobotRegistry

    sample = api.JointObservation('joint-a', 0.25, None)
    joints = [sample]
    observation = api.ReadOnlyObservation(joints, api.MotionState.MOVING, 'fixture mode', False)
    description, state = _backend_values(observation)
    registry = RobotRegistry()
    registry.register(ROBOT, ReadOnlyMockBackend(description, state))

    joints.clear()
    output = registry.read_state(ROBOT).observation
    assert output.joints == (sample,)
    assert output.joints[0].position_rad == 0.25
    assert output.joints[0].velocity_rad_s is None
    assert output.motion_state is api.MotionState.MOVING
    assert output.control_mode == 'fixture mode'
    assert output.estop_active is False
    with pytest.raises(FrozenInstanceError):
        output.joints[0].position_rad = 0.0
    with pytest.raises(FrozenInstanceError):
        output.joints = ()


def test_empty_joints_are_distinct_from_unknown_joints():
    api = _discovery()
    empty = api.ReadOnlyObservation([], api.MotionState.UNKNOWN, None, None)
    unknown = api.ReadOnlyObservation(None, api.MotionState.UNKNOWN, None, None)
    assert empty.joints == ()
    assert unknown.joints is None
    assert empty != unknown


def test_joint_known_values_are_floats():
    api = _discovery()
    joint = api.JointObservation('joint-a', 1, -2)
    assert joint.position_rad == 1.0 and type(joint.position_rad) is float
    assert joint.velocity_rad_s == -2.0 and type(joint.velocity_rad_s) is float


@pytest.mark.parametrize('field,value,error', [
    ('name', False, TypeError),
    ('name', 'joint a', ValueError),
    ('position_rad', True, TypeError),
    ('position_rad', float('nan'), ValueError),
    ('position_rad', float('-inf'), ValueError),
    ('velocity_rad_s', '1.0', TypeError),
    ('velocity_rad_s', float('inf'), ValueError),
])
def test_joint_observations_validate_names_and_finite_values(field, value, error):
    api = _discovery()
    sample = api.JointObservation('joint-a', 0.25, None)
    with pytest.raises(error):
        replace(sample, **{field: value})


@pytest.mark.parametrize('field,value,error', [
    ('joints', 'joint-a', TypeError),
    ('joints', ['joint-a'], TypeError),
    ('motion_state', 'STOPPED', TypeError),
    ('motion_state', None, TypeError),
    ('control_mode', '', ValueError),
    ('control_mode', '  \t', ValueError),
    ('control_mode', 1, TypeError),
    ('estop_active', 0, TypeError),
    ('estop_active', 'false', TypeError),
])
def test_observation_validates_fields(field, value, error):
    api = _discovery()
    missing = api.ReadOnlyObservation(None, api.MotionState.UNKNOWN, None, None)
    with pytest.raises(error):
        replace(missing, **{field: value})


def test_observation_rejects_duplicate_joint_names():
    api = _discovery()
    first = api.JointObservation('joint-a', 0.25, None)
    second = api.JointObservation('joint-a', None, 1.0)
    with pytest.raises(ValueError):
        api.ReadOnlyObservation((first, second), api.MotionState.UNKNOWN, None, None)


def test_mock_rejects_non_sim_and_inconsistent_identities():
    description, state = _backend_values()
    from framework.adapters.mock_robot import ReadOnlyMockBackend
    from framework.domain.discovery import BackendKind

    drifted = replace(state.identity, backend_epoch='fixture-epoch-b')
    with pytest.raises(ValueError):
        ReadOnlyMockBackend(description, replace(state, identity=drifted))
    real = replace(state.identity, backend_kind=BackendKind.REAL)
    with pytest.raises(ValueError):
        ReadOnlyMockBackend(replace(description, identity=real), replace(state, identity=real))


def test_mock_constructor_requires_description_and_state():
    description, state = _backend_values()
    from framework.adapters.mock_robot import ReadOnlyMockBackend

    with pytest.raises(TypeError):
        ReadOnlyMockBackend(state, state)
    with pytest.raises(TypeError):
        ReadOnlyMockBackend(description, description)


def test_backend_and_robot_state_require_valid_identities_and_observations():
    _, state = _backend_values()
    from framework.domain.discovery import ReadOnlyBinding, RobotState

    binding = ReadOnlyBinding(ROBOT, state.identity)
    for field in ('identity', 'observation'):
        with pytest.raises(TypeError):
            replace(state, **{field: object()})
    for field, value, error in (
        ('binding', state.identity, TypeError),
        ('observation', object(), TypeError),
        ('capability_revision', True, TypeError),
        ('capability_revision', -1, ValueError),
    ):
        with pytest.raises(error):
            replace(RobotState(binding, state.observation, 1), **{field: value})


def _read_supplied_backend(consumer, description, state):
    from framework.adapters.mock_robot import ReadOnlyMockBackend
    from framework.application.registry import RobotRegistry

    if consumer == 'mock':
        mock = ReadOnlyMockBackend(description, state)
        return mock.describe(), mock.read_state()
    source = SimpleNamespace(describe=lambda: description, read_state=lambda: state)
    registry = RobotRegistry()
    return registry.register(ROBOT, source), registry.read_state(ROBOT)


@pytest.mark.parametrize('consumer', ['mock', 'registry'])
def test_read_boundaries_reject_subtyped_inputs_that_restore_execution(consumer):
    description, state = _backend_values()
    from framework.domain.capabilities import CapabilityInputs

    @dataclass(frozen=True, slots=True)
    class AlwaysExecutingInputs(CapabilityInputs):
        def __post_init__(self):
            CapabilityInputs.__post_init__(self)
            object.__setattr__(self, 'execution', True)

    inputs = AlwaysExecutingInputs(True, True, True, True, False, 'fixture-config-1', None)
    with pytest.raises(TypeError):
        _read_supplied_backend(consumer, replace(description, capability_inputs=inputs), state)


@pytest.mark.parametrize('consumer', ['mock', 'registry'])
def test_read_boundaries_reject_subtyped_observations_with_control_handles(consumer):
    description, state = _backend_values()
    from framework.domain.discovery import MotionState, ReadOnlyObservation

    @dataclass(frozen=True, slots=True)
    class ExtendedObservation(ReadOnlyObservation):
        control: Callable[[], None]

    def control():
        pytest.fail('unexpected invocation of a control handle')

    observation = ExtendedObservation(None, MotionState.UNKNOWN, None, None, control)
    with pytest.raises(TypeError):
        _read_supplied_backend(consumer, description, replace(state, observation=observation))


@pytest.mark.parametrize('consumer', ['mock', 'registry'])
@pytest.mark.parametrize('response', ['description', 'state'])
def test_read_boundaries_require_concrete_backend_responses(consumer, response):
    description, state = _backend_values()
    from framework.domain.discovery import BackendDescription, BackendState

    class ExtendedDescription(BackendDescription):
        pass

    class ExtendedState(BackendState):
        pass

    if response == 'description':
        description = ExtendedDescription(description.identity, description.name, description.capability_inputs)
    else:
        state = ExtendedState(state.identity, state.observation)
    with pytest.raises(TypeError):
        _read_supplied_backend(consumer, description, state)


@pytest.mark.parametrize('response', ['description', 'state'])
def test_backend_results_reject_identity_subtypes(response):
    description, state = _backend_values()
    from framework.domain.discovery import BackendIdentity

    class ExtendedIdentity(BackendIdentity):
        pass

    identity = ExtendedIdentity(DEVICE, 'mock-backend-a', description.identity.backend_kind, 'fixture-epoch-a')
    with pytest.raises(TypeError):
        replace(description if response == 'description' else state, identity=identity)


class _ExtendedText(str):
    pass


@pytest.mark.parametrize('field,value', [
    ('backend_id', _ExtendedText('mock-backend-a')),
    ('backend_epoch', _ExtendedText('fixture-epoch-a')),
    ('device_id', DeviceId(_ExtendedText('mock-device-a'))),
])
def test_backend_identity_rejects_nonconcrete_text_values(field, value):
    description, _ = _backend_values()
    with pytest.raises(TypeError):
        replace(description.identity, **{field: value})


def test_backend_identity_rejects_device_id_subtypes():
    description, _ = _backend_values()

    class ExtendedDeviceId(DeviceId):
        pass

    with pytest.raises(TypeError):
        replace(description.identity, device_id=ExtendedDeviceId('mock-device-a'))


def test_backend_description_rejects_display_name_subtypes():
    description, _ = _backend_values()
    with pytest.raises(TypeError):
        replace(description, name=_ExtendedText('Fixture arm'))


@pytest.mark.parametrize('field,value', [
    ('joints', type('ExtendedJointList', (list,), {})()),
    ('control_mode', _ExtendedText('fixture mode')),
])
def test_observations_reject_nonconcrete_field_values(field, value):
    _, state = _backend_values()
    with pytest.raises(TypeError):
        replace(state.observation, **{field: value})


def test_observations_reject_joint_subtypes():
    _, state = _backend_values()
    from framework.domain.discovery import JointObservation

    class ExtendedJoint(JointObservation):
        pass

    with pytest.raises(TypeError):
        replace(state.observation, joints=[ExtendedJoint('joint-a', 0.25, None)])


def test_joints_reject_name_subtypes():
    api = _discovery()
    with pytest.raises(TypeError):
        api.JointObservation(_ExtendedText('joint-a'), 0.25, None)
