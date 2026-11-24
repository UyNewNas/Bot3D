"""Concrete pose commands and versioned, transport-independent execution identity."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from uuid import UUID

from .capabilities import _validate_revision, _validate_token as _base_token
from .geometry import Quaternion
from .targets import PoseGoal
from .values import FrameId, RobotId, ToolId, Vector3, _finite_float

__all__ = [
    'CommandKey', 'CommandTiming', 'CommandContext', 'PoseConstraints', 'PoseCommand',
    'canonical_execution', 'execution_digest',
]


def _require(value: object, expected: type, name: str) -> None:
    if type(value) is not expected:
        raise TypeError(f'{name} must be a concrete {expected.__name__}')


def _validate_token(value: str, name: str) -> None:
    _base_token(value, name)
    # JSON escapes a non-BMP scalar as a surrogate pair. A Python string that
    # literally contains those surrogate code points must not alias that ID.
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError(f'{name} must not contain Unicode surrogate code points')


def _count(value: int, name: str, *, minimum: int = 0) -> None:
    _require(value, int, name)
    if value < minimum:
        raise ValueError(f'{name} must be at least {minimum}')


def _identifier(value: object, expected: type, name: str) -> None:
    _require(value, expected, name)
    _validate_token(value.value, name)


@dataclass(frozen=True, slots=True)
class CommandKey:
    robot_id: RobotId
    command_id: str

    def __post_init__(self) -> None:
        _identifier(self.robot_id, RobotId, 'robot_id')
        _require(self.command_id, str, 'command_id')
        object.__setattr__(self, 'command_id', str(UUID(self.command_id)))


@dataclass(frozen=True, slots=True)
class CommandTiming:
    """Absolute internal ns deadlines; this value does not consult a clock."""

    clock_id: str
    admit_before_ns: int
    start_before_ns: int
    execution_timeout_ns: int

    def __post_init__(self) -> None:
        _validate_token(self.clock_id, 'clock_id')
        _count(self.admit_before_ns, 'admit_before_ns')
        _count(self.start_before_ns, 'start_before_ns')
        _count(self.execution_timeout_ns, 'execution_timeout_ns', minimum=1)
        if self.admit_before_ns > self.start_before_ns:
            raise ValueError('admission deadline must not follow start deadline')


@dataclass(frozen=True, slots=True)
class CommandContext:
    robot_model_revision: str
    scene_revision: str
    calibration_revision: str

    def __post_init__(self) -> None:
        for name in ('robot_model_revision', 'scene_revision', 'calibration_revision'):
            _validate_token(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class PoseConstraints:
    """Structural bounds only; device-approved ranges are a separate policy."""

    speed_scale: float
    position_tolerance_m: float
    orientation_tolerance_rad: float

    def __post_init__(self) -> None:
        for name in ('speed_scale', 'position_tolerance_m', 'orientation_tolerance_rad'):
            number = _finite_float(getattr(self, name), name)
            if number <= 0:
                raise ValueError(f'{name} must be positive')
            object.__setattr__(self, name, number)
        if self.speed_scale > 1:
            raise ValueError('speed_scale must not exceed one')


@dataclass(frozen=True, slots=True)
class PoseCommand:
    """Submitted execution meaning, never enriched from current backend state."""

    key: CommandKey
    request_id: str
    backend_epoch: str
    lease_id: str = field(repr=False)
    capability_revision: int
    goal: PoseGoal
    context: CommandContext
    timing: CommandTiming
    constraints: PoseConstraints
    api_version: str = '1.0'
    capability: str = 'manipulation.pose_goal'

    def __post_init__(self) -> None:
        for name, cls in (
            ('key', CommandKey), ('goal', PoseGoal), ('context', CommandContext),
            ('timing', CommandTiming), ('constraints', PoseConstraints),
        ):
            _require(getattr(self, name), cls, name)
        for name in ('request_id', 'backend_epoch', 'lease_id', 'api_version', 'capability'):
            _validate_token(getattr(self, name), name)
        if self.api_version != '1.0' or self.capability != 'manipulation.pose_goal':
            raise ValueError('unsupported command API version or capability')
        _validate_revision(self.capability_revision)
        # Foundation goals allow subclasses; command boundaries accept only plain data.
        _identifier(self.goal.robot_id, RobotId, 'goal.robot_id')
        _identifier(self.goal.frame_id, FrameId, 'goal.frame_id')
        _identifier(self.goal.tool_id, ToolId, 'goal.tool_id')
        _require(self.goal.position_m, Vector3, 'goal.position_m')
        _require(self.goal.orientation_xyzw, Quaternion, 'goal.orientation_xyzw')
        if self.goal.robot_id != self.key.robot_id:
            raise ValueError('goal robot must match the command key')


def _zero(value: float) -> float:
    return 0.0 if value == 0 else value


def canonical_execution(command: PoseCommand) -> bytes:
    """Versioned canonical UTF-8; contains the lease token, so do not log raw bytes."""
    _require(command, PoseCommand, 'command')
    q = command.goal.orientation_xyzw
    sign = next(value for value in (q.w, q.x, q.y, q.z) if value != 0)
    orientation = [_zero(value if sign > 0 else -value) for value in q.as_tuple()]
    payload = {
        'schema': 'bot3d.pose-command.v1',
        'api_version': command.api_version,
        'robot_id': command.key.robot_id.value,
        'backend_epoch': command.backend_epoch,
        'lease_id': command.lease_id,
        'capability': command.capability,
        'capability_revision': command.capability_revision,
        'context': {
            'robot_model_revision': command.context.robot_model_revision,
            'scene_revision': command.context.scene_revision,
            'calibration_revision': command.context.calibration_revision,
        },
        'goal': {
            'frame_id': command.goal.frame_id.value,
            'tool_id': command.goal.tool_id.value,
            'position_m': [_zero(value) for value in command.goal.position_m.as_tuple()],
            'orientation_xyzw': orientation,
        },
        'constraints': {
            'speed_scale': command.constraints.speed_scale,
            'position_tolerance_m': command.constraints.position_tolerance_m,
            'orientation_tolerance_rad': command.constraints.orientation_tolerance_rad,
        },
        'timing': {
            'clock_id': command.timing.clock_id,
            'admit_before_ns': command.timing.admit_before_ns,
            'start_before_ns': command.timing.start_before_ns,
            'execution_timeout_ns': command.timing.execution_timeout_ns,
        },
    }
    return json.dumps(payload, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('utf-8')


def execution_digest(command: PoseCommand) -> str:
    """Stable SHA-256 execution identity; request_id and command_id are separate."""
    return hashlib.sha256(canonical_execution(command)).hexdigest()
