"""Pure composition and revision of the effective pose-goal capability."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .values import _validate_id

__all__ = [
    'CapabilityInputs', 'UnavailableReason', 'PoseGoalCapability', 'CapabilitySnapshot',
    'compose_pose_goal', 'revise_capabilities',
]


def _validate_revision(revision: int) -> None:
    if type(revision) is not int:
        raise TypeError('capability revision must be a built-in int')
    if revision <= 0:
        raise ValueError('capability revision must be positive')


def _validate_token(value: str, field: str) -> None:
    if type(value) is not str:
        raise TypeError(f'{field} must be a built-in str')
    _validate_id(value)


def _validate_context(configuration_revision: str, mode: str | None) -> None:
    _validate_token(configuration_revision, 'configuration_revision')
    if mode is not None:
        _validate_token(mode, 'mode')


@dataclass(frozen=True, slots=True)
class CapabilityInputs:
    """Explicit prerequisites and the declared context of one binding."""

    planning: bool
    model: bool
    frames: bool
    policy: bool
    execution: bool
    configuration_revision: str
    mode: str | None

    def __post_init__(self) -> None:
        for field in ('planning', 'model', 'frames', 'policy', 'execution'):
            if type(getattr(self, field)) is not bool:
                raise TypeError(f'{field} must be a built-in bool')
        _validate_context(self.configuration_revision, self.mode)


class UnavailableReason(StrEnum):
    PLANNING_UNAVAILABLE = 'planning_unavailable'
    MODEL_UNAVAILABLE = 'model_unavailable'
    FRAMES_UNAVAILABLE = 'frames_unavailable'
    POLICY_UNAVAILABLE = 'policy_unavailable'
    EXECUTION_UNAVAILABLE = 'execution_unavailable'


@dataclass(frozen=True, slots=True)
class PoseGoalCapability:
    """A pose-goal declaration with canonically ordered missing prerequisites."""

    reasons: tuple[UnavailableReason, ...] | list[UnavailableReason]

    def __post_init__(self) -> None:
        if type(self.reasons) is not list and type(self.reasons) is not tuple:
            raise TypeError('reasons must be a list or tuple')
        reasons = tuple(self.reasons)
        if any(type(reason) is not UnavailableReason for reason in reasons):
            raise TypeError('reasons must contain only UnavailableReason members')
        unique_reasons = set(reasons)
        if len(unique_reasons) != len(reasons):
            raise ValueError('reasons must not contain duplicates')
        ordered = tuple(reason for reason in UnavailableReason if reason in unique_reasons)
        object.__setattr__(self, 'reasons', ordered)

    @property
    def capability_id(self) -> str:
        return 'manipulation.pose_goal'

    @property
    def version(self) -> str:
        return '1.0'

    @property
    def available(self) -> bool:
        return not self.reasons


def compose_pose_goal(inputs: CapabilityInputs) -> PoseGoalCapability:
    if type(inputs) is not CapabilityInputs:
        raise TypeError('inputs must be CapabilityInputs')
    requirements = (
        (inputs.planning, UnavailableReason.PLANNING_UNAVAILABLE),
        (inputs.model, UnavailableReason.MODEL_UNAVAILABLE),
        (inputs.frames, UnavailableReason.FRAMES_UNAVAILABLE),
        (inputs.policy, UnavailableReason.POLICY_UNAVAILABLE),
        (inputs.execution, UnavailableReason.EXECUTION_UNAVAILABLE),
    )
    return PoseGoalCapability(tuple(reason for available, reason in requirements if not available))


@dataclass(frozen=True, slots=True)
class CapabilitySnapshot:
    revision: int
    configuration_revision: str
    mode: str | None
    pose_goal: PoseGoalCapability

    def __post_init__(self) -> None:
        _validate_revision(self.revision)
        _validate_context(self.configuration_revision, self.mode)
        if type(self.pose_goal) is not PoseGoalCapability:
            raise TypeError('pose_goal must be a PoseGoalCapability')


def revise_capabilities(
    inputs: CapabilityInputs, previous: CapabilitySnapshot | None = None,
) -> CapabilitySnapshot:
    """Compute the next capability snapshot for the same logical binding."""
    if previous is not None and type(previous) is not CapabilitySnapshot:
        raise TypeError('previous must be a CapabilitySnapshot or None')
    pose_goal = compose_pose_goal(inputs)
    if previous is None:
        revision = 1
    elif (inputs.configuration_revision, inputs.mode, pose_goal) == (
        previous.configuration_revision, previous.mode, previous.pose_goal,
    ):
        return previous
    else:
        revision = previous.revision + 1
    return CapabilitySnapshot(revision, inputs.configuration_revision, inputs.mode, pose_goal)
