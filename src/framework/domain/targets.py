"""Validated mathematical goals scoped to a robot, frame, and tool."""
from __future__ import annotations

from dataclasses import dataclass

from .geometry import FrameMismatch, Quaternion, RigidTransform
from .values import FrameId, RobotId, ToolId, Vector3

__all__ = ['PoseGoal']


@dataclass(frozen=True, slots=True)
class PoseGoal:
    """A complete tool pose expressed in the given frame."""

    robot_id: RobotId
    frame_id: FrameId
    tool_id: ToolId
    position_m: Vector3
    orientation_xyzw: Quaternion

    def __post_init__(self) -> None:
        if not isinstance(self.robot_id, RobotId):
            raise TypeError('robot_id must be a RobotId')
        if not isinstance(self.frame_id, FrameId):
            raise TypeError('frame_id must be a FrameId')
        if not isinstance(self.tool_id, ToolId):
            raise TypeError('tool_id must be a ToolId')
        if not isinstance(self.position_m, Vector3):
            raise TypeError('position_m must be a Vector3')
        if not isinstance(self.orientation_xyzw, Quaternion):
            raise TypeError('orientation_xyzw must be a Quaternion')

    def transformed(self, transform: RigidTransform) -> PoseGoal:
        if not isinstance(transform, RigidTransform):
            raise TypeError('transform must be a RigidTransform')
        if self.frame_id != transform.source_frame:
            raise FrameMismatch(
                f'goal frame {self.frame_id.value!r} must match '
                f'transform source frame {transform.source_frame.value!r}'
            )
        return PoseGoal(
            self.robot_id, transform.target_frame, self.tool_id,
            transform.apply_point(self.position_m),
            transform.apply_orientation(self.orientation_xyzw),
        )
