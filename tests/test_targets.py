"""T28/values: typed, complete, frame-scoped tool goals."""
from dataclasses import FrozenInstanceError
from math import sqrt

import pytest

from framework.domain.geometry import FrameMismatch, Quaternion, RigidTransform
from framework.domain.targets import PoseGoal
from framework.domain.values import DeviceId, FrameId, RobotId, ToolId, Vector3

pytestmark = pytest.mark.t28_values
QUARTER_TURN = sqrt(0.5)
APPROX = {'abs': 1e-9, 'rel': 0}


def _goal_arguments():
    return {
        'robot_id': RobotId('arm-fixture'),
        'frame_id': FrameId('arm-fixture/base'),
        'tool_id': ToolId('tool0'),
        'position_m': Vector3(1, 0, 0),
        'orientation_xyzw': Quaternion(QUARTER_TURN, 0, 0, QUARTER_TURN),
    }


def test_transformed_goal_keeps_robot_and_tool_and_accepts_a_shared_world_frame():
    arguments = _goal_arguments()
    goal = PoseGoal(**arguments)

    world = FrameId('cell/world')
    transform = RigidTransform(world, FrameId('arm-fixture/base'), Vector3(1, 2, 3),
                               Quaternion(0, 0, QUARTER_TURN, QUARTER_TURN))
    moved = goal.transformed(transform)
    assert moved is not goal
    assert moved.robot_id == RobotId('arm-fixture')
    assert moved.frame_id == world
    assert moved.tool_id == ToolId('tool0')
    assert moved.position_m.as_tuple() == pytest.approx((1, 3, 3), **APPROX)
    assert moved.orientation_xyzw.as_tuple() == pytest.approx((0.5, 0.5, 0.5, 0.5), **APPROX)
    assert goal == PoseGoal(**arguments)
    assert goal.frame_id == FrameId('arm-fixture/base')
    assert goal.position_m.as_tuple() == (1.0, 0.0, 0.0)
    assert goal.orientation_xyzw.as_tuple() == pytest.approx((QUARTER_TURN, 0, 0, QUARTER_TURN), **APPROX)
    assert not hasattr(goal, '__dict__')
    with pytest.raises(FrozenInstanceError):
        goal.frame_id = world


@pytest.mark.parametrize('field', ['robot_id', 'frame_id', 'tool_id', 'position_m', 'orientation_xyzw'])
def test_goal_requires_every_field_and_rejects_implicit_conversion(field):
    arguments = _goal_arguments()

    with pytest.raises(TypeError):
        PoseGoal(**{key: value for key, value in arguments.items() if key != field})
    arguments[field] = None
    with pytest.raises(TypeError):
        PoseGoal(**arguments)
    arguments[field] = {
        'robot_id': DeviceId('arm-fixture'),
        'frame_id': 'arm-fixture/base',
        'tool_id': RobotId('tool0'),
        'position_m': [1, 0, 0],
        'orientation_xyzw': (0, 0, 0, 1),
    }[field]
    with pytest.raises(TypeError):
        PoseGoal(**arguments)


def test_goal_rejects_a_transform_with_a_different_source_frame():
    arguments = _goal_arguments()
    goal = PoseGoal(**arguments)

    wrong_source = RigidTransform(goal.frame_id, FrameId('cell/world'), Vector3(0, 0, 0),
                                  Quaternion(0, 0, 0, 1))
    with pytest.raises(FrameMismatch):
        goal.transformed(wrong_source)
    with pytest.raises(TypeError):
        goal.transformed(None)
