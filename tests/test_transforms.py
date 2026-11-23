"""T28/basis: framed active transforms with independently derived outcomes."""
from dataclasses import FrozenInstanceError
from math import sqrt
from sys import float_info

import pytest

from framework.domain.geometry import FrameMismatch, Quaternion, RigidTransform
from framework.domain.values import DeviceId, FrameId, Vector3

pytestmark = pytest.mark.t28_basis
QUARTER_TURN = sqrt(0.5)
APPROX = {'abs': 1e-9, 'rel': 0}


def _world_from_base():
    return RigidTransform(
        FrameId('cell/world'),
        FrameId('arm-fixture/base'),
        Vector3(1, 2, 3),
        Quaternion(0, 0, QUARTER_TURN, QUARTER_TURN),
    )


@pytest.mark.parametrize('point, expected', [((0, 0, 0), (1, 2, 3)), ((1, 0, 0), (1, 3, 3))])
def test_transform_rotates_and_translates_points(point, expected):
    transform = _world_from_base()
    assert transform.apply_point(Vector3(*point)).as_tuple() == pytest.approx(expected, **APPROX)


@pytest.mark.parametrize('direction, expected', [
    ((1, 0, 0), (0, 1, 0)), ((0, 1, 0), (-1, 0, 0)), ((0, 0, 1), (0, 0, 1)),
])
def test_transform_rotates_basis_directions_without_translation(direction, expected):
    transform = _world_from_base()
    assert transform.apply_direction(Vector3(*direction)).as_tuple() == pytest.approx(expected, **APPROX)


def test_inverse_swaps_frames_and_rotates_the_negated_translation():
    inverse = _world_from_base().inverse()
    assert inverse.target_frame == FrameId('arm-fixture/base')
    assert inverse.source_frame == FrameId('cell/world')
    assert inverse.translation_m.as_tuple() == pytest.approx((-2, 1, -3), **APPROX)
    assert inverse.rotation.as_tuple() == pytest.approx((0, 0, -QUARTER_TURN, QUARTER_TURN), **APPROX)
    assert inverse.apply_point(Vector3(1, 2, 3)).as_tuple() == pytest.approx((0, 0, 0), **APPROX)
    assert inverse.apply_point(Vector3(1, 3, 3)).as_tuple() == pytest.approx((1, 0, 0), **APPROX)


def test_orientation_composes_transform_rotation_on_the_left():
    transform = _world_from_base()
    orientation = Quaternion(QUARTER_TURN, 0, 0, QUARTER_TURN)
    result = transform.apply_orientation(orientation)
    assert result.as_tuple() == pytest.approx((0.5, 0.5, 0.5, 0.5), **APPROX)
    assert result.rotate(Vector3(1, 2, 3)).as_tuple() == pytest.approx((3, 1, 2), **APPROX)


def test_compose_uses_other_target_frame_and_noncommuting_rotations():
    a, b, c = FrameId('cell/world'), FrameId('arm-fixture/base'), FrameId('arm-fixture/flange')
    a_from_b = RigidTransform(a, b, Vector3(1, 2, 3),
                              Quaternion(QUARTER_TURN, 0, 0, QUARTER_TURN))
    b_from_c = RigidTransform(b, c, Vector3(4, 5, 6),
                              Quaternion(0, QUARTER_TURN, 0, QUARTER_TURN))
    composed = a_from_b.compose(b_from_c)
    assert (composed.target_frame, composed.source_frame) == (a, c)
    assert composed.translation_m.as_tuple() == pytest.approx((5, -4, 8), **APPROX)
    assert composed.apply_point(Vector3(1, 2, 3)).as_tuple() == pytest.approx((8, -3, 10), **APPROX)
    assert composed.apply_direction(Vector3(1, 2, 3)).as_tuple() == pytest.approx((3, 1, 2), **APPROX)
    inverse = composed.inverse()
    assert (inverse.target_frame, inverse.source_frame) == (c, a)
    assert inverse.translation_m.as_tuple() == pytest.approx((4, -8, -5), **APPROX)
    with pytest.raises(FrameMismatch) as mismatch:
        b_from_c.compose(a_from_b)
    assert isinstance(mismatch.value, ValueError)


@pytest.mark.parametrize('field', ['target_frame', 'source_frame', 'translation_m', 'rotation'])
def test_transform_constructor_rejects_wrong_field_type(field):
    transform = _world_from_base()
    arguments = {
        'target_frame': transform.target_frame,
        'source_frame': transform.source_frame,
        'translation_m': transform.translation_m,
        'rotation': transform.rotation,
    }
    arguments[field] = {
        'target_frame': DeviceId('cell/world'),
        'source_frame': 'arm-fixture/base',
        'translation_m': (1, 2, 3),
        'rotation': [0, 0, 0, 1],
    }[field]
    with pytest.raises(TypeError):
        type(transform)(**arguments)


@pytest.mark.parametrize('method, value', [
    ('apply_point', (0, 0, 0)),
    ('apply_direction', None),
    ('apply_orientation', (0, 0, 0, 1)),
    ('compose', 'cell/world'),
])
def test_transform_methods_require_typed_operands(method, value):
    transform = _world_from_base()
    with pytest.raises(TypeError):
        getattr(transform, method)(value)


def test_transform_is_immutable():
    transform = _world_from_base()
    assert not hasattr(transform, '__dict__')
    with pytest.raises(FrozenInstanceError):
        transform.source_frame = transform.target_frame


def test_point_and_composition_reject_translation_overflow():
    a, b, c = FrameId('cell/world'), FrameId('arm-fixture/base'), FrameId('arm-fixture/flange')
    translation = Vector3(float_info.max, 0, 0)
    identity_rotation = Quaternion(0, 0, 0, 1)
    a_from_b = RigidTransform(a, b, translation, identity_rotation)
    b_from_c = RigidTransform(b, c, translation, identity_rotation)
    with pytest.raises(ValueError):
        a_from_b.apply_point(translation)
    with pytest.raises(ValueError):
        a_from_b.compose(b_from_c)
