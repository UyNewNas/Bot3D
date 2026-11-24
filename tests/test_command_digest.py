"""T02 / T03: execution identity is independent of transport correlation."""
from dataclasses import FrozenInstanceError, replace
import hashlib
import math

import pytest

from framework.domain.geometry import Quaternion
from framework.domain.targets import PoseGoal
from framework.domain.values import FrameId, RobotId, ToolId, Vector3


CANONICAL = (
    b'{"api_version":"1.0","backend_epoch":"epoch-a",'
    b'"capability":"manipulation.pose_goal","capability_revision":1,'
    b'"constraints":{"orientation_tolerance_rad":0.05,"position_tolerance_m":0.005,"speed_scale":0.1},'
    b'"context":{"calibration_revision":"cal-1","robot_model_revision":"model-1","scene_revision":"scene-1"},'
    b'"goal":{"frame_id":"cell/world","orientation_xyzw":[0.0,0.0,0.0,1.0],'
    b'"position_m":[1.0,0.0,0.25],"tool_id":"tool0"},"lease_id":"lease-a",'
    b'"robot_id":"arm-fixture","schema":"bot3d.pose-command.v1",'
    b'"timing":{"admit_before_ns":100,"clock_id":"control-clock",'
    b'"execution_timeout_ns":300,"start_before_ns":200}}'
)


@pytest.mark.t02_digest
def test_canonical_bytes_have_independent_fixed_semantics(command_case):
    case = command_case()
    assert case.domain.canonical_execution(case.command) == CANONICAL
    assert case.domain.execution_digest(case.command) == hashlib.sha256(CANONICAL).hexdigest()
    assert 'lease-a' not in repr(case.command)


@pytest.mark.t02_digest
def test_transport_and_command_identity_do_not_change_execution_digest(command_case):
    case = command_case()
    original = case.domain.execution_digest(case.command)
    assert case.domain.execution_digest(replace(case.command, request_id='request-2')) == original
    other_key = replace(case.command.key, command_id='12345678-1234-5678-1234-567812345679')
    assert case.domain.execution_digest(replace(case.command, key=other_key)) == original


@pytest.mark.t02_digest
@pytest.mark.parametrize('xyzw', [(0, 0, 0, -1), (-1, 0, 0, 0), (0, -.6, 0, -.8)])
def test_quaternion_sign_and_negative_zero_are_semantically_equal(xyzw, command_case):
    case = command_case()
    q = Quaternion(*xyzw)
    minus_q = Quaternion(*(-v for v in xyzw))
    first = replace(case.command, goal=replace(case.command.goal, orientation_xyzw=q))
    second = replace(first, goal=replace(first.goal, orientation_xyzw=minus_q,
                                       position_m=Vector3(1.0, -0.0, .25)))
    assert first.goal.orientation_xyzw != second.goal.orientation_xyzw
    assert case.domain.canonical_execution(first) == case.domain.canonical_execution(second)


@pytest.mark.t03_conflict
@pytest.mark.parametrize('field', [
    'epoch', 'lease', 'revision', 'frame', 'tool', 'x', 'y', 'z', 'orientation',
    'model', 'scene', 'calibration', 'clock', 'admit', 'start', 'timeout',
    'speed', 'position_tolerance', 'orientation_tolerance', 'robot',
])
def test_each_execution_field_changes_the_digest(field, command_case):
    case = command_case()
    c = case.command
    changes = {
        'epoch': lambda: replace(c, backend_epoch='epoch-b'),
        'lease': lambda: replace(c, lease_id='lease-b'),
        'revision': lambda: replace(c, capability_revision=2),
        'frame': lambda: replace(c, goal=replace(c.goal, frame_id=FrameId('cell/base'))),
        'tool': lambda: replace(c, goal=replace(c.goal, tool_id=ToolId('tool1'))),
        'x': lambda: replace(c, goal=replace(c.goal, position_m=Vector3(math.nextafter(1, 2), 0, .25))),
        'y': lambda: replace(c, goal=replace(c.goal, position_m=Vector3(1, .01, .25))),
        'z': lambda: replace(c, goal=replace(c.goal, position_m=Vector3(1, 0, .5))),
        'orientation': lambda: replace(c, goal=replace(c.goal, orientation_xyzw=Quaternion(1, 0, 0, 0))),
        'model': lambda: replace(c, context=replace(c.context, robot_model_revision='model-2')),
        'scene': lambda: replace(c, context=replace(c.context, scene_revision='scene-2')),
        'calibration': lambda: replace(c, context=replace(c.context, calibration_revision='cal-2')),
        'clock': lambda: replace(c, timing=replace(c.timing, clock_id='other-clock')),
        'admit': lambda: replace(c, timing=replace(c.timing, admit_before_ns=101)),
        'start': lambda: replace(c, timing=replace(c.timing, start_before_ns=201)),
        'timeout': lambda: replace(c, timing=replace(c.timing, execution_timeout_ns=301)),
        'speed': lambda: replace(c, constraints=replace(c.constraints, speed_scale=.2)),
        'position_tolerance': lambda: replace(c, constraints=replace(c.constraints, position_tolerance_m=.01)),
        'orientation_tolerance': lambda: replace(c, constraints=replace(c.constraints, orientation_tolerance_rad=.1)),
        'robot': lambda: replace(c, key=replace(c.key, robot_id=RobotId('other-arm')),
                                goal=replace(c.goal, robot_id=RobotId('other-arm'))),
    }
    assert case.domain.execution_digest(changes[field]()) != case.domain.execution_digest(c)


@pytest.mark.t02_digest
def test_uuid_key_normalizes_uuid_spelling_but_not_robot_identity(command_case):
    case = command_case()
    a = case.domain.CommandKey(RobotId('Arm'), 'ABCDEFAB123456781234567812345678')
    b = case.domain.CommandKey(RobotId('Arm'), '{abcdefab-1234-5678-1234-567812345678}')
    assert a == b and a.command_id == 'abcdefab-1234-5678-1234-567812345678'
    assert a != replace(b, robot_id=RobotId('arm'))


@pytest.mark.t03_conflict
@pytest.mark.parametrize(('kind', 'field', 'value', 'error'), [
    ('command', 'api_version', '2.0', ValueError),
    ('command', 'capability', 'gripper.set_width', ValueError),
    ('command', 'backend_epoch', '', ValueError),
    ('command', 'request_id', 'bad request', ValueError),
    ('command', 'lease_id', None, TypeError),
    ('command', 'capability_revision', True, TypeError),
    ('command', 'capability_revision', 0, ValueError),
    ('key', 'command_id', 'cmd-1', ValueError),
    ('key', 'command_id', 1, TypeError),
    ('timing', 'admit_before_ns', True, TypeError),
    ('timing', 'admit_before_ns', -1, ValueError),
    ('timing', 'admit_before_ns', 201, ValueError),
    ('timing', 'start_before_ns', 99, ValueError),
    ('timing', 'execution_timeout_ns', 0, ValueError),
    ('timing', 'clock_id', '', ValueError),
    ('constraints', 'speed_scale', 0, ValueError),
    ('constraints', 'speed_scale', 1.01, ValueError),
    ('constraints', 'speed_scale', True, TypeError),
    ('constraints', 'position_tolerance_m', float('nan'), ValueError),
    ('constraints', 'position_tolerance_m', -1, ValueError),
    ('constraints', 'orientation_tolerance_rad', float('inf'), ValueError),
    ('constraints', 'orientation_tolerance_rad', 0, ValueError),
    ('context', 'scene_revision', '', ValueError),
])
def test_invalid_execution_inputs_are_rejected(kind, field, value, error, command_case):
    c = command_case().command
    value_object = c if kind == 'command' else getattr(c, kind)
    with pytest.raises(error):
        replace(value_object, **{field: value})


@pytest.mark.t03_conflict
def test_goal_scope_and_concrete_nested_values_are_required(command_case):
    c = command_case().command
    with pytest.raises(ValueError):
        replace(c, goal=replace(c.goal, robot_id=RobotId('other-arm')))

    class GoalSubclass(PoseGoal):
        pass

    class RobotSubclass(RobotId):
        pass

    class TextSubclass(str):
        pass

    with pytest.raises(TypeError):
        replace(c, goal=GoalSubclass(c.goal.robot_id, c.goal.frame_id, c.goal.tool_id,
                                    c.goal.position_m, c.goal.orientation_xyzw))
    with pytest.raises(TypeError):
        replace(c, goal=replace(c.goal, robot_id=RobotSubclass('arm-fixture')))
    with pytest.raises(TypeError):
        replace(c, goal=replace(c.goal, frame_id=FrameId(TextSubclass('cell/world'))))
    with pytest.raises(FrozenInstanceError):
        c.request_id = 'changed'


@pytest.mark.t03_conflict
def test_invalid_outer_objects_never_become_a_digest(command_case):
    d = command_case().domain
    for value in (None, {}, 'command'):
        with pytest.raises(TypeError):
            d.execution_digest(value)


@pytest.mark.t03_conflict
@pytest.mark.parametrize('field', [
    'epoch', 'lease', 'clock', 'model', 'scene', 'calibration', 'robot', 'frame', 'tool',
])
def test_surrogate_identifiers_cannot_alias_valid_unicode(field, command_case):
    c = command_case().command
    invalid = 'scope-\ud83d\ude80'
    changes = {
        'epoch': lambda: replace(c, backend_epoch=invalid),
        'lease': lambda: replace(c, lease_id=invalid),
        'clock': lambda: replace(c, timing=replace(c.timing, clock_id=invalid)),
        'model': lambda: replace(c, context=replace(c.context, robot_model_revision=invalid)),
        'scene': lambda: replace(c, context=replace(c.context, scene_revision=invalid)),
        'calibration': lambda: replace(c, context=replace(c.context, calibration_revision=invalid)),
        'robot': lambda: replace(c.key, robot_id=RobotId(invalid)),
        'frame': lambda: replace(c, goal=replace(c.goal, frame_id=FrameId('cell/' + invalid))),
        'tool': lambda: replace(c, goal=replace(c.goal, tool_id=ToolId(invalid))),
    }
    with pytest.raises(ValueError, match='surrogate'):
        changes[field]()


@pytest.mark.t02_digest
def test_valid_unicode_identifiers_remain_exact_and_distinct(command_case):
    c = command_case()
    # Valid Unicode scalars remain supported; canonical equivalence is not ID equality.
    values = ('lease-\U0001f680', 'lease-\U0001f6f0', 'lease-\u00e9', 'lease-e\u0301')
    digests = {c.domain.execution_digest(replace(c.command, lease_id=value)) for value in values}
    assert len(digests) == 4
    rocket = c.domain.canonical_execution(replace(c.command, lease_id=values[0]))
    assert b'lease-\\ud83d\\ude80' in rocket
