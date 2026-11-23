"""Right-handed active rotations and frame-labelled rigid transforms."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
from sys import float_info
from typing import TypeVar

from .values import FrameId, Vector3, _finite_float

__all__ = ['Quaternion', 'FrameMismatch', 'RigidTransform']

_NORM_TOLERANCE = 1e-6
_EXACT_ROTATION_THRESHOLD = float_info.max / 4.0
_Number = TypeVar('_Number', float, Fraction)


def _rotation_matrix_numerators(
    x: _Number, y: _Number, z: _Number, w: _Number,
) -> tuple[tuple[tuple[_Number, _Number, _Number], ...], _Number]:
    """Return homogeneous matrix rows and their common squared-norm divisor."""
    xx, yy, zz, ww = x * x, y * y, z * z, w * w
    rows = (
        ((ww + xx) - (yy + zz), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), (ww + yy) - (xx + zz), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), (ww + zz) - (xx + yy)),
    )
    return rows, xx + yy + zz + ww


def _rotate_exact(
    xyzw: tuple[float, float, float, float], xyz: tuple[float, float, float],
) -> Vector3:
    x, y, z, w = (Fraction.from_float(component) for component in xyzw)
    vx, vy, vz = (Fraction.from_float(component) for component in xyz)
    rows, norm_squared = _rotation_matrix_numerators(x, y, z, w)
    result = tuple((a * vx + b * vy + c * vz) / norm_squared for a, b, c in rows)
    if any(abs(component) > float_info.max for component in result):
        raise ValueError('rotated vector component exceeds the finite float range')
    return Vector3(*(float(component) for component in result))


@dataclass(frozen=True, slots=True)
class Quaternion:
    """A unit quaternion with components in xyzw order."""

    x: float
    y: float
    z: float
    w: float

    def __post_init__(self) -> None:
        x = _finite_float(self.x, 'x')
        y = _finite_float(self.y, 'y')
        z = _finite_float(self.z, 'z')
        w = _finite_float(self.w, 'w')
        norm = math.hypot(x, y, z, w)
        if not 1.0 - _NORM_TOLERANCE <= norm <= 1.0 + _NORM_TOLERANCE:
            raise ValueError('quaternion norm is outside the unit tolerance')
        object.__setattr__(self, 'x', x / norm)
        object.__setattr__(self, 'y', y / norm)
        object.__setattr__(self, 'z', z / norm)
        object.__setattr__(self, 'w', w / norm)

    @classmethod
    def from_xyzw(cls, xyzw: list[int | float] | tuple[int | float, ...]) -> Quaternion:
        if not isinstance(xyzw, (list, tuple)):
            raise TypeError('xyzw must be a list or tuple')
        if len(xyzw) != 4:
            raise ValueError('xyzw must contain four components')
        x, y, z, w = xyzw
        return cls(x, y, z, w)

    def as_tuple(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.z, self.w

    def rotate(self, vector: Vector3) -> Vector3:
        """Rotate a vector, evaluating extreme inputs exactly before rounding."""
        if not isinstance(vector, Vector3):
            raise TypeError('vector must be a Vector3')
        xyz = vector.as_tuple()
        # Each matrix row has three coefficients within [-1, 1]. Below
        # this threshold, even the sum of three absolute products fits
        # in binary64 with ample room for coefficient rounding.
        if max(map(abs, xyz)) > _EXACT_ROTATION_THRESHOLD:
            return _rotate_exact(self.as_tuple(), xyz)
        rows, norm_squared = _rotation_matrix_numerators(*self.as_tuple())
        vx, vy, vz = xyz
        return Vector3(*(
            math.fsum(((a / norm_squared) * vx,
                       (b / norm_squared) * vy,
                       (c / norm_squared) * vz))
            for a, b, c in rows
        ))

    def inverse(self) -> Quaternion:
        return Quaternion(-self.x, -self.y, -self.z, self.w)

    def compose(self, other: Quaternion) -> Quaternion:
        """Return the Hamilton product self * other, applying other first."""
        if not isinstance(other, Quaternion):
            raise TypeError('other must be a Quaternion')
        x, y, z, w = self.as_tuple()
        ox, oy, oz, ow = other.as_tuple()
        return Quaternion(
            w * ox + x * ow + y * oz - z * oy,
            w * oy - x * oz + y * ow + z * ox,
            w * oz + x * oy - y * ox + z * ow,
            w * ow - x * ox - y * oy - z * oz,
        )


class FrameMismatch(ValueError):
    """Raised when an operation would combine incompatible frame labels."""


@dataclass(frozen=True, slots=True)
class RigidTransform:
    """T_A_B maps source B to target A by p_A = R_A_B p_B + t_A_B."""

    target_frame: FrameId
    source_frame: FrameId
    translation_m: Vector3
    rotation: Quaternion

    def __post_init__(self) -> None:
        if not isinstance(self.target_frame, FrameId):
            raise TypeError('target_frame must be a FrameId')
        if not isinstance(self.source_frame, FrameId):
            raise TypeError('source_frame must be a FrameId')
        if not isinstance(self.translation_m, Vector3):
            raise TypeError('translation_m must be a Vector3')
        if not isinstance(self.rotation, Quaternion):
            raise TypeError('rotation must be a Quaternion')

    def apply_point(self, point: Vector3) -> Vector3:
        rotated = self.rotation.rotate(point)
        return Vector3(rotated.x + self.translation_m.x,
                       rotated.y + self.translation_m.y,
                       rotated.z + self.translation_m.z)

    def apply_direction(self, direction: Vector3) -> Vector3:
        return self.rotation.rotate(direction)

    def apply_orientation(self, orientation: Quaternion) -> Quaternion:
        return self.rotation.compose(orientation)

    def inverse(self) -> RigidTransform:
        inverse_rotation = self.rotation.inverse()
        x, y, z = self.translation_m.as_tuple()
        return RigidTransform(
            self.source_frame, self.target_frame,
            inverse_rotation.rotate(Vector3(-x, -y, -z)), inverse_rotation,
        )

    def compose(self, other: RigidTransform) -> RigidTransform:
        """Return T_A_C for self = T_A_B and other = T_B_C."""
        if not isinstance(other, RigidTransform):
            raise TypeError('other must be a RigidTransform')
        if self.source_frame != other.target_frame:
            raise FrameMismatch(
                f'source frame {self.source_frame.value!r} must match '
                f'the other target frame {other.target_frame.value!r}'
            )
        return RigidTransform(
            self.target_frame, other.source_frame,
            self.apply_point(other.translation_m), self.rotation.compose(other.rotation),
        )
