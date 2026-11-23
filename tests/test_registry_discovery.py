"""T46/discovery: logical identities and revisions stay tied to each binding."""
from dataclasses import FrozenInstanceError, replace
from importlib import import_module
from importlib.util import find_spec
from types import SimpleNamespace

import pytest

from framework.domain.values import DeviceId, RobotId

pytestmark = pytest.mark.t46_discovery
ROBOT = RobotId('arm-fixture')
MIRROR = RobotId('arm-fixture-mirror')
DEVICE = DeviceId('mock-device-a')


def _registry():
    module = 'framework.application.registry'
    assert find_spec(module) is not None, f'API unavailable: {module}'
    return import_module(module)


class _ReadSource:
    """Mutable script for changing responses across reads of a static binding."""

    def __init__(self):
        from framework.domain.capabilities import CapabilityInputs
        from framework.domain.discovery import (
            BackendDescription, BackendIdentity, BackendKind, BackendState,
            JointObservation, MotionState, ReadOnlyObservation,
        )

        identity = BackendIdentity(DEVICE, 'mock-backend-a', BackendKind.SIM, 'fixture-epoch-a')
        inputs = CapabilityInputs(True, True, True, True, True, 'fixture-config-1', None)
        observation = ReadOnlyObservation(
            [JointObservation('joint-a', 0.25, None)], MotionState.MOVING, None, None,
        )
        self.description = BackendDescription(identity, 'Fixture arm', inputs)
        self.state = BackendState(identity, observation)
        self.reads = []

    def describe(self):
        self.reads.append('describe')
        return self.description

    def read_state(self):
        self.reads.append('read_state')
        return self.state


def test_new_registry_is_empty():
    api = _registry()
    assert api.RobotRegistry().discover() == ()


def test_discovery_sorts_mirrors_and_preserves_identity_in_state():
    api = _registry()
    registry = api.RobotRegistry()
    backend = _ReadSource()
    mirror = registry.register(MIRROR, backend)
    primary = registry.register(ROBOT, backend)

    assert registry.discover() == (primary, mirror)
    for robot, expected in ((ROBOT, primary), (MIRROR, mirror)):
        state = registry.read_state(robot)
        assert state.binding == expected.binding
        assert state.binding.robot_id == robot
        assert state.binding.backend == backend.description.identity
        assert state.binding.read_only is True
        assert state.capability_revision == 1
        assert state.observation == backend.state.observation

    with pytest.raises(FrozenInstanceError):
        primary.binding.robot_id = MIRROR


def test_failed_discovery_preserves_revisions_until_successful_retry():
    api = _registry()
    registry = api.RobotRegistry()
    primary, mirror = _ReadSource(), _ReadSource()
    initial_mirror = registry.register(MIRROR, mirror)
    initial_primary = registry.register(ROBOT, primary)
    original_primary, original_mirror = primary.description, mirror.description

    changed = replace(
        original_primary, capability_inputs=replace(original_primary.capability_inputs, mode='fixture-mode'),
    )
    primary.description = changed
    mirror.description = replace(
        original_mirror, identity=replace(original_mirror.identity, backend_epoch='fixture-epoch-b'),
    )
    primary.reads.clear()
    mirror.reads.clear()
    with pytest.raises(api.BindingMismatch):
        registry.discover()
    assert primary.reads == mirror.reads == ['describe']

    primary.description = original_primary
    assert registry.describe(ROBOT) == initial_primary

    primary.description, mirror.description = changed, original_mirror
    primary.reads.clear()
    mirror.reads.clear()
    updated = replace(
        initial_primary, capabilities=replace(initial_primary.capabilities, revision=2, mode='fixture-mode'),
    )
    assert registry.discover() == (updated, initial_mirror)
    assert primary.reads == mirror.reads == ['describe']

    primary.description = original_primary
    assert registry.describe(ROBOT).capabilities.revision == 3


def test_duplicate_is_rejected_before_replacement_backend_is_read():
    api = _registry()
    registry = api.RobotRegistry()
    original = _ReadSource()
    registered = registry.register(ROBOT, original)
    replacement = _ReadSource()

    with pytest.raises(api.DuplicateRobot):
        registry.register(ROBOT, replacement)
    assert replacement.reads == []
    assert registry.describe(ROBOT) == registered
    assert original.reads == ['describe', 'describe']


@pytest.mark.parametrize('method', ['describe', 'read_state'])
def test_unknown_robot_id_raises_and_is_not_created(method):
    api = _registry()
    registry = api.RobotRegistry()
    with pytest.raises(api.UnknownRobot):
        getattr(registry, method)(ROBOT)
    assert registry.discover() == ()


@pytest.mark.parametrize('bad_id', [DEVICE, ROBOT.value])
def test_public_methods_require_robot_id(bad_id):
    api = _registry()
    registry = api.RobotRegistry()
    backend = _ReadSource()
    for method in (registry.describe, registry.read_state):
        with pytest.raises(TypeError):
            method(bad_id)
    with pytest.raises(TypeError):
        registry.register(bad_id, backend)
    assert backend.reads == []


@pytest.mark.parametrize('field', ['device_id', 'backend_id', 'backend_kind', 'backend_epoch'])
@pytest.mark.parametrize('method', ['describe', 'read_state'])
def test_full_identity_drift_raises_without_rebinding(method, field):
    api = _registry()
    registry = api.RobotRegistry()
    backend = _ReadSource()
    registered = registry.register(ROBOT, backend)
    description, state = backend.description, backend.state
    changed = {
        'device_id': DeviceId('mock-device-b'),
        'backend_id': 'mock-backend-b',
        'backend_kind': type(description.identity.backend_kind).REAL,
        'backend_epoch': 'fixture-epoch-b',
    }
    drifted = replace(description.identity, **{field: changed[field]})
    new_inputs = replace(description.capability_inputs, configuration_revision='fixture-config-2')
    backend.description = replace(description, capability_inputs=new_inputs)
    if method == 'describe':
        backend.description = replace(backend.description, identity=drifted)
    else:
        backend.state = replace(state, identity=drifted)

    with pytest.raises(api.BindingMismatch):
        getattr(registry, method)(ROBOT)

    backend.description, backend.state = description, state
    assert registry.describe(ROBOT) == registered
    assert registry.read_state(ROBOT).binding == registered.binding


def test_revisions_are_kept_per_mirror_and_display_renames_do_not_increment():
    api = _registry()
    registry = api.RobotRegistry()
    backend = _ReadSource()
    primary = registry.register(ROBOT, backend)
    mirror = registry.register(MIRROR, backend)
    original_inputs = backend.description.capability_inputs

    backend.description = replace(backend.description, name='Fixture arm renamed')
    renamed = registry.describe(ROBOT)
    assert renamed.name == 'Fixture arm renamed'
    assert renamed.capabilities == primary.capabilities
    assert registry.read_state(ROBOT).capability_revision == 1

    backend.description = replace(
        backend.description, capability_inputs=replace(original_inputs, frames=False),
    )
    assert registry.read_state(ROBOT).capability_revision == 2
    assert backend.reads[-2:] == ['describe', 'read_state']
    backend.description = replace(backend.description, capability_inputs=original_inputs)

    descriptions = registry.discover()
    assert tuple(item.capabilities.revision for item in descriptions) == (3, 1)
    assert primary.capabilities.revision == mirror.capabilities.revision == 1


def test_backend_execution_changes_are_not_public_semantic_changes():
    api = _registry()
    registry = api.RobotRegistry()
    backend = _ReadSource()
    registered = registry.register(ROBOT, backend)
    backend.description = replace(
        backend.description, capability_inputs=replace(backend.description.capability_inputs, execution=False),
    )
    assert registry.describe(ROBOT).capabilities == registered.capabilities


def test_registration_requires_both_read_methods_before_describing():
    api = _registry()
    registry = api.RobotRegistry()
    backend = _ReadSource()
    partial_backend = SimpleNamespace(describe=backend.describe, read_state=None)
    with pytest.raises(TypeError):
        registry.register(ROBOT, partial_backend)
    with pytest.raises(TypeError):
        registry.register(ROBOT, SimpleNamespace(read_state=backend.read_state))
    assert backend.reads == []
    assert registry.discover() == ()


def test_invalid_description_does_not_leave_a_registration():
    api = _registry()
    registry = api.RobotRegistry()
    backend = _ReadSource()
    description = backend.description
    backend.description = SimpleNamespace(identity=description.identity, name=description.name)
    with pytest.raises(TypeError):
        registry.register(ROBOT, backend)
    assert registry.discover() == ()
    backend.description = description
    assert registry.register(ROBOT, backend).capabilities.revision == 1


def test_backend_exceptions_propagate_and_failed_registration_leaves_no_entry():
    api = _registry()
    registry = api.RobotRegistry()
    backend = _ReadSource()
    failure = RuntimeError('fixture describe failure')

    def failing_read():
        raise failure

    with pytest.raises(RuntimeError) as raised:
        registry.register(ROBOT, SimpleNamespace(describe=failing_read, read_state=backend.read_state))
    assert raised.value is failure
    assert registry.discover() == ()
    assert registry.register(ROBOT, backend).capabilities.revision == 1
    backend.read_state = failing_read
    with pytest.raises(RuntimeError) as raised:
        registry.read_state(ROBOT)
    assert raised.value is failure


def test_non_state_result_is_rejected_after_registration():
    api = _registry()
    registry = api.RobotRegistry()
    backend = _ReadSource()
    registered = registry.register(ROBOT, backend)
    backend.state = backend.description
    with pytest.raises(TypeError):
        registry.read_state(ROBOT)
    assert registry.describe(ROBOT) == registered


@pytest.mark.parametrize('field,value,error', [
    ('device_id', ROBOT, TypeError),
    ('backend_id', 12, TypeError),
    ('backend_id', 'mock backend', ValueError),
    ('backend_kind', 'SIM', TypeError),
    ('backend_epoch', '', ValueError),
    ('backend_epoch', 'fixture\tepoch', ValueError),
])
def test_backend_identity_rejects_invalid_fields(field, value, error):
    _registry()
    identity = _ReadSource().description.identity
    with pytest.raises(error):
        replace(identity, **{field: value})


def test_binding_does_not_accept_swapped_identity_types_or_writable_flag():
    api = _registry()
    backend = _ReadSource()
    binding = api.RobotRegistry().register(ROBOT, backend).binding
    with pytest.raises(TypeError):
        replace(binding, robot_id=DEVICE)
    with pytest.raises(TypeError):
        replace(binding, backend=DEVICE)
    with pytest.raises(TypeError):
        type(binding)(ROBOT, backend.description.identity, read_only=False)


@pytest.mark.parametrize('field,value,error', [
    ('identity', DEVICE, TypeError),
    ('name', 12, TypeError),
    ('name', '', ValueError),
    ('name', ' \t', ValueError),
    ('capability_inputs', object(), TypeError),
])
def test_backend_description_validates_its_fields(field, value, error):
    _registry()
    with pytest.raises(error):
        replace(_ReadSource().description, **{field: value})


def test_public_robot_description_validates_its_value_fields():
    api = _registry()
    robot = api.RobotRegistry().register(ROBOT, _ReadSource())
    for field, value, error in (
        ('binding', ROBOT, TypeError),
        ('name', ' ', ValueError),
        ('capabilities', object(), TypeError),
    ):
        with pytest.raises(error):
            replace(robot, **{field: value})


def test_registry_rejects_robot_id_subtypes_before_reading_backend():
    api = _registry()
    backend = _ReadSource()

    class ExtendedRobotId(RobotId):
        pass

    class ExtendedText(str):
        pass

    registry = api.RobotRegistry()
    for robot_id in (ExtendedRobotId(ROBOT.value), RobotId(ExtendedText(ROBOT.value))):
        with pytest.raises(TypeError):
            registry.register(robot_id, backend)
        with pytest.raises(TypeError):
            registry.describe(robot_id)
        with pytest.raises(TypeError):
            registry.read_state(robot_id)
    assert backend.reads == []
    assert registry.discover() == ()
