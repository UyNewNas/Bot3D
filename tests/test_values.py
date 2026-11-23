"""T28/values: scoped identifiers, finite vector components and explicit units."""
from dataclasses import FrozenInstanceError
from math import inf, nan, pi
from sys import float_info

import pytest

from framework.domain import values

pytestmark = pytest.mark.t28_values


def test_identifiers_preserve_their_type_and_spelling():
    robot = values.RobotId('arm-fixture')
    device = values.DeviceId('mock-device-a')
    tool = values.ToolId('tool0')
    assert (robot.value, device.value, tool.value) == ('arm-fixture', 'mock-device-a', 'tool0')
    assert robot == values.RobotId('arm-fixture')
    assert robot != values.DeviceId('arm-fixture')
    assert robot != values.ToolId('arm-fixture')
    assert device != values.ToolId('mock-device-a')
    assert len({values.RobotId('cell/world'), values.DeviceId('cell/world'),
                values.FrameId('cell/world'), values.ToolId('cell/world')}) == 4


@pytest.mark.parametrize('identifier, valid', [
    (values.RobotId, 'arm-fixture'),
    (values.DeviceId, 'mock-device-a'),
    (values.FrameId, 'cell/world'),
    (values.ToolId, 'tool0'),
])
def test_identifiers_are_immutable_and_reject_missing_values(identifier, valid):
    value = identifier(valid)
    with pytest.raises(FrozenInstanceError):
        value.value = valid + '2'
    assert not hasattr(value, '__dict__')

    for wrong_type in (None, 1, ['value']):
        with pytest.raises(TypeError):
            identifier(wrong_type)
    for invalid in ('', ' ', ' leading', 'inside space', 'trailing\t'):
        with pytest.raises(ValueError):
            identifier(invalid)


@pytest.mark.parametrize('value', ['cell/world', 'arm-fixture/base', 'cell/arm/tool0'])
def test_frame_preserves_a_scoped_name(value):
    assert values.FrameId(value).value == value


@pytest.mark.parametrize('value', [
    'world', '/cell/world', 'cell/world/', 'cell//world', 'cell/./world', 'cell/../world',
])
def test_frame_rejects_invalid_scope(value):
    with pytest.raises(ValueError):
        values.FrameId(value)


def test_vector_copies_its_components_and_is_immutable():
    coordinates = [1, 2.5, -3]
    value = values.Vector3.from_xyz(coordinates)
    coordinates[0] = 0
    assert value.as_tuple() == (1.0, 2.5, -3.0)
    assert all(type(component) is float for component in value.as_tuple())
    assert value == values.Vector3(1, 2.5, -3) == values.Vector3.from_xyz((1, 2.5, -3))
    assert hash(value) == hash(values.Vector3(1, 2.5, -3))
    assert not hasattr(value, '__dict__')
    with pytest.raises(FrozenInstanceError):
        value.x = 0


def test_vector_accepts_finite_components_when_its_norm_cannot_fit():
    maximum = float_info.max
    assert values.Vector3(maximum, maximum, 0).as_tuple() == (maximum, maximum, 0.0)


@pytest.mark.parametrize('coordinates', [None, '123', {'x': 1, 'y': 2, 'z': 3}, range(3)])
def test_vector_rejects_non_array_input(coordinates):
    with pytest.raises(TypeError):
        values.Vector3.from_xyz(coordinates)


@pytest.mark.parametrize('coordinates', [[], (1, 2), (1, 2, 3, 4)])
def test_vector_rejects_wrong_dimension(coordinates):
    with pytest.raises(ValueError):
        values.Vector3.from_xyz(coordinates)


class IntSubclass(int):
    pass


@pytest.mark.parametrize('value', ['1', True, None, IntSubclass(1)])
def test_numeric_boundaries_reject_non_builtin_numbers(value):
    with pytest.raises(TypeError):
        values.Vector3(1, value, 3)
    with pytest.raises(TypeError):
        values.Vector3.from_xyz((1, 2, value))
    for convert in (values.mm_to_m, values.m_to_mm, values.deg_to_rad, values.rad_to_deg):
        with pytest.raises(TypeError):
            convert(value)


@pytest.mark.parametrize('value', [
    pytest.param(nan, id='nan'),
    pytest.param(inf, id='positive-infinity'),
    pytest.param(-inf, id='negative-infinity'),
    pytest.param(10 ** 400, id='unrepresentable-integer'),
])
def test_numeric_boundaries_reject_nonfinite_components(value):
    with pytest.raises(ValueError):
        values.Vector3(value, 2, 3)
    for convert in (values.mm_to_m, values.m_to_mm, values.deg_to_rad, values.rad_to_deg):
        with pytest.raises(ValueError):
            convert(value)


@pytest.mark.parametrize('function, value, expected', [
    (values.mm_to_m, 1000, 1.0),
    (values.m_to_mm, 1, 1000.0),
    (values.deg_to_rad, 180, pi),
    (values.rad_to_deg, pi, 180.0),
    (values.mm_to_m, -125, -0.125),
])
def test_unit_conversion_uses_explicit_input_and_output_units(function, value, expected):
    result = function(value)
    assert type(result) is float
    assert result == pytest.approx(expected, abs=1e-9, rel=0)


@pytest.mark.parametrize('convert', [values.m_to_mm, values.rad_to_deg])
def test_unit_conversion_rejects_output_overflow(convert):
    with pytest.raises(ValueError):
        convert(float_info.max)
