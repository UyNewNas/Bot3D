"""Immutable identifiers, finite vector components, and explicit unit conversions."""
from __future__ import annotations

from dataclasses import dataclass
import math

__all__ = [
    'RobotId', 'DeviceId', 'FrameId', 'ToolId', 'Vector3',
    'mm_to_m', 'm_to_mm', 'deg_to_rad', 'rad_to_deg',
]


def _validate_id(value: str) -> None:
    if not isinstance(value, str):
        raise TypeError('identifier value must be a string')
    if not value or any(character.isspace() for character in value):
        raise ValueError('identifier value must be nonempty and contain no whitespace')


def _finite_float(value: int | float, field: str) -> float:
    if type(value) is not int and type(value) is not float:
        raise TypeError(f'{field} must be a built-in int or float')
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f'{field} must be representable as a finite float') from exc
    if not math.isfinite(number):
        raise ValueError(f'{field} must be finite')
    return number


@dataclass(frozen=True, slots=True)
class RobotId:
    value: str

    def __post_init__(self) -> None:
        _validate_id(self.value)


@dataclass(frozen=True, slots=True)
class DeviceId:
    value: str

    def __post_init__(self) -> None:
        _validate_id(self.value)


@dataclass(frozen=True, slots=True)
class FrameId:
    """A name scoped by at least two slash-separated path segments."""

    value: str

    def __post_init__(self) -> None:
        _validate_id(self.value)
        segments = self.value.split('/')
        if len(segments) < 2 or any(segment in ('', '.', '..') for segment in segments):
            raise ValueError('frame identifier must have at least two valid path segments')


@dataclass(frozen=True, slots=True)
class ToolId:
    value: str

    def __post_init__(self) -> None:
        _validate_id(self.value)


@dataclass(frozen=True, slots=True)
class Vector3:
    """Three finite Cartesian components whose units follow their usage."""

    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        object.__setattr__(self, 'x', _finite_float(self.x, 'x'))
        object.__setattr__(self, 'y', _finite_float(self.y, 'y'))
        object.__setattr__(self, 'z', _finite_float(self.z, 'z'))

    @classmethod
    def from_xyz(cls, xyz: list[int | float] | tuple[int | float, ...]) -> Vector3:
        if not isinstance(xyz, (list, tuple)):
            raise TypeError('xyz must be a list or tuple')
        if len(xyz) != 3:
            raise ValueError('xyz must contain three coordinates')
        x, y, z = xyz
        return cls(x, y, z)

    def as_tuple(self) -> tuple[float, float, float]:
        return self.x, self.y, self.z


def mm_to_m(value: int | float) -> float:
    return _finite_float(_finite_float(value, 'millimeters') / 1000.0, 'meters')


def m_to_mm(value: int | float) -> float:
    return _finite_float(_finite_float(value, 'meters') * 1000.0, 'millimeters')


def deg_to_rad(value: int | float) -> float:
    return _finite_float(math.radians(_finite_float(value, 'degrees')), 'radians')


def rad_to_deg(value: int | float) -> float:
    return _finite_float(math.degrees(_finite_float(value, 'radians')), 'degrees')
