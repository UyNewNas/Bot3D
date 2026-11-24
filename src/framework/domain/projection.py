"""Immutable feedback, provenance, clock bounds and projected observations."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .capabilities import _validate_revision, _validate_token
from .discovery import BackendIdentity, BackendKind, JointObservation, MotionState, _validate_robot_id
from .geometry import Quaternion
from .targets import PoseGoal
from .time import MonotonicInstant
from .values import FrameId, RobotId, ToolId, Vector3, _finite_float

__all__ = [
    'DataOrigin', 'DataQuality', 'ProjectionDisposition', 'ProjectionContext', 'ProjectionConfig',
    'ToolPose', 'JointFeedback', 'PoseFeedback', 'ControllerFeedback', 'FeedbackSample',
    'ClockMapping', 'ProjectionTarget', 'ProjectionPlan', 'ForwardKinematicsResult',
    'SourceTimeBounds', 'ProjectedDatum', 'StationaryEvidence', 'ProjectedState', 'ProjectionUpdate',
]


class DataOrigin(StrEnum):
    MEASURED = 'MEASURED'
    SIMULATED = 'SIMULATED'
    DERIVED = 'DERIVED'


class DataQuality(StrEnum):
    FRESH = 'FRESH'
    STALE = 'STALE'
    UNSYNCED = 'UNSYNCED'
    INVALID = 'INVALID'


class ProjectionDisposition(StrEnum):
    ACCEPTED = 'ACCEPTED'
    DUPLICATE = 'DUPLICATE'
    OUT_OF_ORDER = 'OUT_OF_ORDER'
    IDENTITY_MISMATCH = 'IDENTITY_MISMATCH'
    CONTEXT_MISMATCH = 'CONTEXT_MISMATCH'
    CLOCK_MISMATCH = 'CLOCK_MISMATCH'
    CONFLICT = 'CONFLICT'
    SOURCE_REGRESSION = 'SOURCE_REGRESSION'
    INVALID_RECEIVE_TIME = 'INVALID_RECEIVE_TIME'


def _concrete(value: object, cls: type, name: str) -> None:
    if type(value) is not cls:
        raise TypeError(f'{name} must be a concrete {cls.__name__}')


def _count(value: int, name: str, minimum: int = 0) -> None:
    _concrete(value, int, name)
    if value < minimum:
        raise ValueError(f'{name} must be at least {minimum}')


def _instant(value: MonotonicInstant, name: str) -> None:
    _concrete(value, MonotonicInstant, name)
    _validate_token(value.clock_id, f'{name}.clock_id')


def _identifier(value: object, cls: type, name: str) -> None:
    _concrete(value, cls, name)
    _concrete(value.value, str, f'{name}.value')


def _feedback(origin: DataOrigin, invalid_reason: str | None) -> None:
    _concrete(origin, DataOrigin, 'origin')
    if invalid_reason is not None:
        _validate_token(invalid_reason, 'invalid_reason')


@dataclass(frozen=True, slots=True)
class ProjectionContext:
    capability_revision: int
    robot_model_revision: str
    scene_revision: str
    calibration_revision: str

    def __post_init__(self) -> None:
        _validate_revision(self.capability_revision)
        for name in ('robot_model_revision', 'scene_revision', 'calibration_revision'):
            _validate_token(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class ProjectionConfig:
    """Explicit validated fixture/deployment policy; no device safety defaults."""

    robot_id: RobotId
    backend: BackendIdentity
    source_id: str
    source_clock_id: str
    protection_clock_id: str
    joint_names: tuple[str, ...] | list[str]
    frame_id: FrameId
    tool_id: ToolId
    feedback_origin: DataOrigin
    max_source_age_ns: int
    max_receive_age_ns: int
    max_clock_uncertainty_ns: int
    stationary_window_ns: int
    max_sample_gap_ns: int
    max_velocity_rad_s: float
    max_position_delta_rad: float

    def __post_init__(self) -> None:
        _validate_robot_id(self.robot_id)
        _concrete(self.backend, BackendIdentity, 'backend')
        for name in ('source_id', 'source_clock_id', 'protection_clock_id'):
            _validate_token(getattr(self, name), name)
        if type(self.joint_names) not in (list, tuple):
            raise TypeError('joint_names must be a list or tuple')
        names = tuple(self.joint_names)
        for name in names:
            _validate_token(name, 'joint name')
        if not names or len(set(names)) != len(names):
            raise ValueError('joint_names must be nonempty and unique')
        object.__setattr__(self, 'joint_names', names)
        _identifier(self.frame_id, FrameId, 'frame_id')
        _identifier(self.tool_id, ToolId, 'tool_id')
        _concrete(self.feedback_origin, DataOrigin, 'feedback_origin')
        expected = DataOrigin.SIMULATED if self.backend.backend_kind is BackendKind.SIM else DataOrigin.MEASURED
        if self.feedback_origin is not expected:
            raise ValueError('feedback origin must match the configured backend kind')
        for name in ('max_source_age_ns', 'max_receive_age_ns', 'stationary_window_ns', 'max_sample_gap_ns'):
            _count(getattr(self, name), name, 1)
        _count(self.max_clock_uncertainty_ns, 'max_clock_uncertainty_ns')
        for name in ('max_velocity_rad_s', 'max_position_delta_rad'):
            value = _finite_float(getattr(self, name), name)
            if value < 0:
                raise ValueError(f'{name} must be nonnegative')
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class ToolPose:
    """An observed pose, deliberately distinct from a commanded PoseGoal."""

    frame_id: FrameId
    tool_id: ToolId
    position_m: Vector3
    orientation_xyzw: Quaternion

    def __post_init__(self) -> None:
        _identifier(self.frame_id, FrameId, 'frame_id')
        _identifier(self.tool_id, ToolId, 'tool_id')
        _concrete(self.position_m, Vector3, 'position_m')
        _concrete(self.orientation_xyzw, Quaternion, 'orientation_xyzw')


@dataclass(frozen=True, slots=True)
class JointFeedback:
    joints: tuple[JointObservation, ...] | list[JointObservation]
    origin: DataOrigin
    invalid_reason: str | None = None

    def __post_init__(self) -> None:
        _feedback(self.origin, self.invalid_reason)
        if type(self.joints) not in (list, tuple):
            raise TypeError('joints must be a list or tuple')
        values = tuple(self.joints)
        for item in values:
            _concrete(item, JointObservation, 'joint')
        if len({item.name for item in values}) != len(values):
            raise ValueError('joint names must be unique')
        object.__setattr__(self, 'joints', values)


@dataclass(frozen=True, slots=True)
class PoseFeedback:
    """DERIVED attests an FK pose computed from this packet's joint basis."""

    pose: ToolPose
    origin: DataOrigin
    invalid_reason: str | None = None

    def __post_init__(self) -> None:
        _concrete(self.pose, ToolPose, 'pose')
        _feedback(self.origin, self.invalid_reason)


@dataclass(frozen=True, slots=True)
class ControllerFeedback:
    motion_state: MotionState
    control_mode: str | None
    estop_active: bool | None
    protective_stop_active: bool | None
    origin: DataOrigin
    invalid_reason: str | None = None

    def __post_init__(self) -> None:
        _feedback(self.origin, self.invalid_reason)
        _concrete(self.motion_state, MotionState, 'motion_state')
        if self.control_mode is not None:
            _validate_token(self.control_mode, 'control_mode')
        for name in ('estop_active', 'protective_stop_active'):
            value = getattr(self, name)
            if value is not None:
                _concrete(value, bool, name)


@dataclass(frozen=True, slots=True)
class FeedbackSample:
    robot_id: RobotId
    backend: BackendIdentity
    context: ProjectionContext
    source_id: str
    source_seq: int
    source_time: MonotonicInstant | None
    received_at: MonotonicInstant
    joints: JointFeedback | None
    tool_pose: PoseFeedback | None
    controller: ControllerFeedback | None

    def __post_init__(self) -> None:
        _validate_robot_id(self.robot_id)
        _concrete(self.backend, BackendIdentity, 'backend')
        _concrete(self.context, ProjectionContext, 'context')
        _validate_token(self.source_id, 'source_id')
        _count(self.source_seq, 'source_seq')
        if self.source_time is not None:
            _instant(self.source_time, 'source_time')
        _instant(self.received_at, 'received_at')
        for name, cls in (('joints', JointFeedback), ('tool_pose', PoseFeedback), ('controller', ControllerFeedback)):
            value = getattr(self, name)
            if value is not None:
                _concrete(value, cls, name)


@dataclass(frozen=True, slots=True)
class ClockMapping:
    """Trusted offset estimate, not a client assertion that clocks are synced."""

    source_clock_id: str
    offset_ns: int
    uncertainty_ns: int
    valid_from: MonotonicInstant
    valid_until: MonotonicInstant
    revision: str

    def __post_init__(self) -> None:
        _validate_token(self.source_clock_id, 'source_clock_id')
        _concrete(self.offset_ns, int, 'offset_ns')
        _count(self.uncertainty_ns, 'uncertainty_ns')
        _instant(self.valid_from, 'valid_from')
        _instant(self.valid_until, 'valid_until')
        if self.valid_from.clock_id != self.valid_until.clock_id or self.valid_from.tick_ns >= self.valid_until.tick_ns:
            raise ValueError('mapping validity must be an increasing same-clock window')
        _validate_token(self.revision, 'revision')


@dataclass(frozen=True, slots=True)
class ProjectionTarget:
    command_id: str
    goal: PoseGoal
    context: ProjectionContext

    def __post_init__(self) -> None:
        _validate_token(self.command_id, 'command_id')
        _concrete(self.goal, PoseGoal, 'goal')
        _validate_robot_id(self.goal.robot_id)
        ToolPose(self.goal.frame_id, self.goal.tool_id, self.goal.position_m, self.goal.orientation_xyzw)
        _concrete(self.context, ProjectionContext, 'context')


@dataclass(frozen=True, slots=True)
class ProjectionPlan:
    """A reference for display; trajectory validation belongs to the coordinator."""

    command_id: str
    plan_id: str
    plan_digest: str
    context: ProjectionContext

    def __post_init__(self) -> None:
        for name in ('command_id', 'plan_id'):
            _validate_token(getattr(self, name), name)
        _concrete(self.plan_digest, str, 'plan_digest')
        if len(self.plan_digest) != 64 or any(ch not in '0123456789abcdef' for ch in self.plan_digest):
            raise ValueError('plan_digest must be 64 lowercase hexadecimal characters')
        _concrete(self.context, ProjectionContext, 'context')


@dataclass(frozen=True, slots=True)
class ForwardKinematicsResult:
    robot_id: RobotId
    backend: BackendIdentity
    context: ProjectionContext
    source_id: str
    source_seq: int
    pose: ToolPose

    def __post_init__(self) -> None:
        _validate_robot_id(self.robot_id)
        _concrete(self.backend, BackendIdentity, 'backend')
        _concrete(self.context, ProjectionContext, 'context')
        _validate_token(self.source_id, 'source_id')
        _count(self.source_seq, 'source_seq')
        _concrete(self.pose, ToolPose, 'pose')


@dataclass(frozen=True, slots=True)
class SourceTimeBounds:
    earliest: MonotonicInstant
    latest: MonotonicInstant


@dataclass(frozen=True, slots=True)
class ProjectedDatum[T]:
    value: T | None
    origin: DataOrigin | None
    quality: DataQuality
    reason: str | None
    valid_until: MonotonicInstant | None


@dataclass(frozen=True, slots=True)
class StationaryEvidence:
    robot_id: RobotId
    backend: BackendIdentity
    context: ProjectionContext
    source_id: str
    start_seq: int
    end_seq: int
    source_start: MonotonicInstant
    source_end: MonotonicInstant
    start_bounds: SourceTimeBounds
    end_bounds: SourceTimeBounds
    received_end_at: MonotonicInstant
    not_before: MonotonicInstant | None
    valid_until: MonotonicInstant


@dataclass(frozen=True, slots=True)
class ProjectedState:
    """Immutable observation slice; authority/command facts have other owners."""

    robot_id: RobotId
    backend: BackendIdentity
    context: ProjectionContext
    state_seq: int
    observed_at: MonotonicInstant
    source_id: str
    source_seq: int | None
    source_time: MonotonicInstant | None
    sample_context: ProjectionContext | None
    received_at: MonotonicInstant | None
    last_received_at: MonotonicInstant | None
    source_time_bounds: SourceTimeBounds | None
    source_age_ns: int | None
    receive_age_ns: int | None
    transport_age_ns: int | None
    mapping_revision: str | None
    joints: ProjectedDatum[tuple[JointObservation, ...]]
    tool_pose: ProjectedDatum[ToolPose]
    controller: ProjectedDatum[ControllerFeedback]
    target: ProjectionTarget | None
    plan: ProjectionPlan | None
    motion_state: MotionState
    stationary: StationaryEvidence | None
    clock_fault: bool


@dataclass(frozen=True, slots=True)
class ProjectionUpdate:
    disposition: ProjectionDisposition
    state: ProjectedState
