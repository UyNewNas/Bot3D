"""T28/quaternion: xyzw order, right-handed action and unit-norm validation."""
from dataclasses import FrozenInstanceError
from math import inf, isfinite, nan, nextafter, sqrt
from sys import float_info

import pytest

from framework.domain.geometry import Quaternion
from framework.domain.values import Vector3

pytestmark = pytest.mark.t28_quaternion
QUARTER_TURN = sqrt(0.5)
LOW_NORM = 1.0 - 1e-6
HIGH_NORM = 1.0 + 1e-6
APPROX = {'abs': 1e-9, 'rel': 0}


def test_quaternion_uses_xyzw_and_copies_mutable_input():
    source = [0, 0, QUARTER_TURN, QUARTER_TURN]
    rotation = Quaternion.from_xyzw(source)
    source[3] = 0
    assert rotation.as_tuple() == pytest.approx((0, 0, QUARTER_TURN, QUARTER_TURN), **APPROX)
    assert all(type(component) is float for component in rotation.as_tuple())
    assert rotation == Quaternion.from_xyzw((0, 0, QUARTER_TURN, QUARTER_TURN))
    assert not hasattr(rotation, '__dict__')
    with pytest.raises(FrozenInstanceError):
        rotation.w = 0


def test_quaternion_composition_applies_other_first():
    qx = Quaternion(QUARTER_TURN, 0, 0, QUARTER_TURN)
    qy = Quaternion(0, QUARTER_TURN, 0, QUARTER_TURN)
    point = Vector3(1, 2, 3)
    product = qx.compose(qy)
    assert product.as_tuple() == pytest.approx((0.5, 0.5, 0.5, 0.5), **APPROX)
    assert product.rotate(point).as_tuple() == pytest.approx((3, 1, 2), **APPROX)
    assert qy.compose(qx).rotate(point).as_tuple() == pytest.approx((2, -3, -1), **APPROX)
    assert product.inverse().rotate(point).as_tuple() == pytest.approx((2, 3, 1), **APPROX)


def test_quaternion_opposite_signs_rotate_equally_but_keep_distinct_values():
    positive = Quaternion(0, 0, QUARTER_TURN, QUARTER_TURN)
    negative = Quaternion(0, 0, -QUARTER_TURN, -QUARTER_TURN)
    assert len({positive, negative}) == 2
    direction = Vector3(1, 0, 0)
    assert positive.rotate(direction).as_tuple() == pytest.approx((0, 1, 0), **APPROX)
    assert negative.rotate(direction).as_tuple() == pytest.approx((0, 1, 0), **APPROX)


def test_near_unit_quaternion_is_normalized_without_scaling_vectors():
    rotation = Quaternion(0.50000025, 0.50000025, 0.50000025, 0.50000025)
    assert rotation.as_tuple() == pytest.approx((0.5, 0.5, 0.5, 0.5), **APPROX)
    assert rotation.rotate(Vector3(1, 2, 3)).as_tuple() == pytest.approx((3, 1, 2), **APPROX)


@pytest.mark.parametrize('w', [LOW_NORM, nextafter(LOW_NORM, 1.0),
                               HIGH_NORM, nextafter(HIGH_NORM, 1.0)])
def test_quaternion_accepts_norm_at_and_just_inside_endpoints(w):
    assert Quaternion(0, 0, 0, w).as_tuple() == (0.0, 0.0, 0.0, 1.0)


@pytest.mark.parametrize('w', [nextafter(LOW_NORM, -inf), nextafter(HIGH_NORM, inf), 0, 2])
def test_quaternion_rejects_norm_outside_the_closed_interval(w):
    with pytest.raises(ValueError):
        Quaternion(0, 0, 0, w)


@pytest.mark.parametrize('value', [nan, inf, -inf])
def test_quaternion_rejects_nonfinite_components(value):
    with pytest.raises(ValueError):
        Quaternion(0, value, 0, 1)


@pytest.mark.parametrize('value', [None, '1', True])
def test_quaternion_rejects_non_numeric_components(value):
    with pytest.raises(TypeError):
        Quaternion(0, 0, 0, value)


def test_quaternion_rejects_non_array_and_wrong_arity():
    for value in (None, '0001', range(4)):
        with pytest.raises(TypeError):
            Quaternion.from_xyzw(value)
    for value in ((0, 0, 1), [0, 0, 0, 1, 1]):
        with pytest.raises(ValueError):
            Quaternion.from_xyzw(value)


def test_quaternion_operations_require_typed_operands():
    rotation = Quaternion(0, 0, 0, 1)
    with pytest.raises(TypeError):
        rotation.rotate((1, 0, 0))
    with pytest.raises(TypeError):
        rotation.compose((0, 0, 0, 1))


def test_rotation_preserves_representable_large_components():
    maximum = float_info.max
    vector = Vector3(maximum, maximum, 0)
    assert Quaternion(0, 0, 0, 1).rotate(vector) == vector
    turn = Quaternion(0, 0, QUARTER_TURN, QUARTER_TURN)
    assert turn.rotate(Vector3(maximum, 0, 0)) == Vector3(0, maximum, 0)


def test_rotation_preserves_finite_result_after_large_term_cancellation():
    rotation = Quaternion(0.25, 0.25, 0.25, sqrt(13) / 4)
    magnitude = 0.875 * float_info.max
    # The vector lies along the (1, 1, 1) rotation axis and stays fixed.
    result = rotation.rotate(Vector3(magnitude, magnitude, magnitude)).as_tuple()
    assert all(isfinite(component) for component in result)
    assert tuple(component / magnitude for component in result) == pytest.approx((1, 1, 1), **APPROX)


def test_rotation_preserves_largest_float_on_an_exact_axis_mapping():
    a = 0.001
    b = sqrt(0.5 - a * a)
    rotation = Quaternion(a, a, b, b)
    maximum = float_info.max
    # Equal x/y and z/w pairs map the positive x axis exactly onto positive y.
    assert rotation.rotate(Vector3(maximum, 0, 0)) == Vector3(0, maximum, 0)


def test_rotation_fixes_largest_float_vector_along_its_axis():
    a = 0.03125
    rotation = Quaternion(a, a, a, sqrt(1 - 3 * a * a))
    maximum = float_info.max
    # Exactly the rotation axis, with no headroom for rounding the result up.
    direction = Vector3(maximum, maximum, maximum)
    assert rotation.rotate(direction) == direction


def test_rotation_rejects_unrepresentable_result_component():
    turn = Quaternion(0, 0, 0.3826834323650898, 0.9238795325112867)
    with pytest.raises(ValueError):
        turn.rotate(Vector3(float_info.max, float_info.max, 0))
