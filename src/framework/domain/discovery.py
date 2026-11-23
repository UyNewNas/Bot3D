"""Immutable backend identities, logical bindings, and read-only observations."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .capabilities import CapabilityInputs, CapabilitySnapshot, _validate_revision, _validate_token
from .values import DeviceId, RobotId, _finite_float

__all__ = [
    'BackendKind', 'MotionState', 'BackendIdentity', 'ReadOnlyBinding', 'BackendDescription',
    'JointObservation', 'ReadOnlyObservation', 'BackendState', 'RobotDescription', 'RobotState',
]


class BackendKind(StrEnum):
    SIM = 'SIM'
    REAL = 'REAL'


class MotionState(StrEnum):
    STOPPED = 'STOPPED'
    MOVING = 'MOVING'
    UNKNOWN = 'UNKNOWN'


def _validate_nonempty_text(value: str, field: str) -> None:
    if type(value) is not str:
        raise TypeError(f'{field} must be a built-in str')
    if not value.strip():
        raise ValueError(f'{field} must contain non-whitespace text')


def _validate_robot_id(robot_id: RobotId) -> None:
    if type(robot_id) is not RobotId:
        raise TypeError('robot_id must be a RobotId')
    if type(robot_id.value) is not str:
        raise TypeError('robot_id.value must be a built-in str')


@dataclass(frozen=True, slots=True)
class BackendIdentity:
    device_id: DeviceId
    backend_id: str
    backend_kind: BackendKind
    backend_epoch: str

    def __post_init__(self) -> None:
        if type(self.device_id) is not DeviceId:
            raise TypeError('device_id must be a DeviceId')
        if type(self.device_id.value) is not str:
            raise TypeError('device_id.value must be a built-in str')
        if type(self.backend_kind) is not BackendKind:
            raise TypeError('backend_kind must be a BackendKind')
        _validate_token(self.backend_id, 'backend_id')
        _validate_token(self.backend_epoch, 'backend_epoch')


@dataclass(frozen=True, slots=True)
class ReadOnlyBinding:
    robot_id: RobotId
    backend: BackendIdentity

    def __post_init__(self) -> None:
        _validate_robot_id(self.robot_id)
        if type(self.backend) is not BackendIdentity:
            raise TypeError('backend must be a BackendIdentity')

    @property
    def read_only(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class BackendDescription:
    identity: BackendIdentity
    name: str
    capability_inputs: CapabilityInputs

    def __post_init__(self) -> None:
        if type(self.identity) is not BackendIdentity:
            raise TypeError('identity must be a BackendIdentity')
        _validate_nonempty_text(self.name, 'name')
        if type(self.capability_inputs) is not CapabilityInputs:
            raise TypeError('capability_inputs must be CapabilityInputs')


@dataclass(frozen=True, slots=True)
class JointObservation:
    name: str
    position_rad: float | None
    velocity_rad_s: float | None

    def __post_init__(self) -> None:
        _validate_token(self.name, 'name')
        if self.position_rad is not None:
            position = _finite_float(self.position_rad, 'position_rad')
            object.__setattr__(self, 'position_rad', position)
        if self.velocity_rad_s is not None:
            velocity = _finite_float(self.velocity_rad_s, 'velocity_rad_s')
            object.__setattr__(self, 'velocity_rad_s', velocity)


@dataclass(frozen=True, slots=True)
class ReadOnlyObservation:
    """Backend observations with explicit unknown values for absent data."""

    joints: tuple[JointObservation, ...] | list[JointObservation] | None
    motion_state: MotionState
    control_mode: str | None
    estop_active: bool | None

    def __post_init__(self) -> None:
        if self.joints is not None:
            if type(self.joints) is not list and type(self.joints) is not tuple:
                raise TypeError('joints must be a list, tuple or None')
            joints = tuple(self.joints)
            if any(type(joint) is not JointObservation for joint in joints):
                raise TypeError('joints must contain only JointObservation values')
            if len({joint.name for joint in joints}) != len(joints):
                raise ValueError('joint names must be unique')
            object.__setattr__(self, 'joints', joints)
        if type(self.motion_state) is not MotionState:
            raise TypeError('motion_state must be a MotionState')
        if self.control_mode is not None:
            _validate_nonempty_text(self.control_mode, 'control_mode')
        if self.estop_active is not None and type(self.estop_active) is not bool:
            raise TypeError('estop_active must be a built-in bool or None')


@dataclass(frozen=True, slots=True)
class BackendState:
    identity: BackendIdentity
    observation: ReadOnlyObservation

    def __post_init__(self) -> None:
        if type(self.identity) is not BackendIdentity:
            raise TypeError('identity must be a BackendIdentity')
        if type(self.observation) is not ReadOnlyObservation:
            raise TypeError('observation must be a ReadOnlyObservation')


@dataclass(frozen=True, slots=True)
class RobotDescription:
    binding: ReadOnlyBinding
    name: str
    capabilities: CapabilitySnapshot

    def __post_init__(self) -> None:
        if type(self.binding) is not ReadOnlyBinding:
            raise TypeError('binding must be a ReadOnlyBinding')
        _validate_nonempty_text(self.name, 'name')
        if type(self.capabilities) is not CapabilitySnapshot:
            raise TypeError('capabilities must be a CapabilitySnapshot')


@dataclass(frozen=True, slots=True)
class RobotState:
    binding: ReadOnlyBinding
    observation: ReadOnlyObservation
    capability_revision: int

    def __post_init__(self) -> None:
        if type(self.binding) is not ReadOnlyBinding:
            raise TypeError('binding must be a ReadOnlyBinding')
        if type(self.observation) is not ReadOnlyObservation:
            raise TypeError('observation must be a ReadOnlyObservation')
        _validate_revision(self.capability_revision)

    @property
    def arming_state(self) -> str:
        return 'DISARMED'
