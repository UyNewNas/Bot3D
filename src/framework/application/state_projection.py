"""Single-owner projection; callers serialize inputs in their coordinator."""
from __future__ import annotations

from dataclasses import dataclass, replace

from framework.domain.discovery import MotionState
from framework.domain.projection import (
    ClockMapping, DataOrigin, DataQuality, FeedbackSample, ForwardKinematicsResult,
    PoseFeedback, ProjectedDatum, ProjectedState, ProjectionConfig, ProjectionContext,
    ProjectionDisposition, ProjectionPlan, ProjectionTarget, ProjectionUpdate,
    SourceTimeBounds, StationaryEvidence, _concrete, _instant,
)
from framework.domain.time import MonotonicInstant

__all__ = ['StateProjection']


@dataclass(frozen=True, slots=True)
class _Timing:
    quality: DataQuality
    reason: str | None
    bounds: SourceTimeBounds | None = None
    source_age: int | None = None
    receive_age: int | None = None
    valid_until: MonotonicInstant | None = None


@dataclass(slots=True)
class _Window:
    first: FeedbackSample
    first_bounds: SourceTimeBounds
    last: FeedbackSample
    last_bounds: SourceTimeBounds
    members: dict[int, FeedbackSample]


class StateProjection:
    """No I/O or locking; one owner supplies trusted protection-clock readings.

    A snapshot is evidence at observed_at, not proof that it remains the newest
    adopted state. The future execution/STOP coordinator must check it again.
    """

    def __init__(self, config: ProjectionConfig, context: ProjectionContext) -> None:
        _concrete(config, ProjectionConfig, 'config')
        _concrete(context, ProjectionContext, 'context')
        self._config = config
        self._context = context
        self._context_generation = 0
        self._sample_context_generation = 0
        self._mapping: ClockMapping | None = None
        self._mapping_generation = 0
        self._mapping_resume_after: int | None = None
        self._sample: FeedbackSample | None = None
        self._sample_mapping: ClockMapping | None = None
        self._sample_mapping_generation = 0
        self._source_watermark: int | None = None
        self._last_received: MonotonicInstant | None = None
        self._last_now: int | None = None
        self._clock_fault = False
        self._stream_fault: tuple[DataQuality, str] | None = None
        self._target: ProjectionTarget | None = None
        self._plan: ProjectionPlan | None = None
        self._fk_pose: PoseFeedback | None = None
        self._window: _Window | None = None
        self._not_before: MonotonicInstant | None = None
        self._position_moving = False
        self._state_seq = 0
        self._signature: ProjectedState | None = None

    def set_mapping(self, mapping: ClockMapping | None, *, now: MonotonicInstant) -> ProjectedState:
        if mapping is not None:
            _concrete(mapping, ClockMapping, 'mapping')
            if self._config.source_clock_id == self._config.protection_clock_id:
                raise ValueError('a shared clock must not be remapped')
            if (mapping.source_clock_id != self._config.source_clock_id
                    or mapping.valid_from.clock_id != self._config.protection_clock_id):
                raise ValueError('mapping clock scope does not match the projection')
        self._observe(now)
        if mapping != self._mapping:
            self._mapping = mapping
            self._mapping_generation += 1
            self._mapping_resume_after = self._source_watermark
            self._window = None
        return self.snapshot(now=now)

    def change_context(self, context: ProjectionContext, *, now: MonotonicInstant) -> ProjectedState:
        _concrete(context, ProjectionContext, 'context')
        if context.capability_revision < self._context.capability_revision:
            raise ValueError('capability revision must not move backward')
        self._observe(now)
        if context != self._context:
            self._context = context
            self._context_generation += 1
            self._target = self._plan = None
            self._window = None
            self._fk_pose = None
            self._position_moving = False
        return self.snapshot(now=now)

    def set_target(self, target: ProjectionTarget | None, *, now: MonotonicInstant) -> ProjectedState:
        if target is not None:
            _concrete(target, ProjectionTarget, 'target')
            if (target.context != self._context or target.goal.robot_id != self._config.robot_id
                    or target.goal.frame_id != self._config.frame_id or target.goal.tool_id != self._config.tool_id):
                raise ValueError('target must match the configured scope and current context')
        self._observe(now)
        if target != self._target:
            self._target = target
            self._plan = None
        return self.snapshot(now=now)

    def set_plan(self, plan: ProjectionPlan | None, *, now: MonotonicInstant) -> ProjectedState:
        if plan is not None:
            _concrete(plan, ProjectionPlan, 'plan')
            if (self._target is None or plan.command_id != self._target.command_id
                    or plan.context != self._context):
                raise ValueError('plan must refer to the current target and context')
        self._observe(now)
        self._plan = plan
        return self.snapshot(now=now)

    def begin_stationary_check(self, not_before: MonotonicInstant, *, now: MonotonicInstant) -> ProjectedState:
        _instant(not_before, 'not_before')
        _instant(now, 'now')
        if (not_before.clock_id != self._config.protection_clock_id
                or now.clock_id != not_before.clock_id or not_before.tick_ns > now.tick_ns
                or (self._not_before is not None and not_before.tick_ns < self._not_before.tick_ns)):
            raise ValueError('stationary boundary must be current, same-clock and nondecreasing')
        self._observe(now)
        self._not_before = not_before
        self._window = None
        return self.snapshot(now=now)

    def apply_fk(self, result: ForwardKinematicsResult, *, now: MonotonicInstant) -> bool:
        _concrete(result, ForwardKinematicsResult, 'result')
        self._observe(now)
        sample = self._sample
        if (sample is None or result.robot_id != self._config.robot_id or result.backend != self._config.backend
                or result.context != self._context or sample.context != self._context
                or result.source_id != sample.source_id or result.source_seq != sample.source_seq
                or result.pose.frame_id != self._config.frame_id or result.pose.tool_id != self._config.tool_id):
            return False
        joints, _, _ = self._data(self._timing(now))
        if joints.quality not in (DataQuality.FRESH, DataQuality.STALE):
            return False
        self._fk_pose = PoseFeedback(result.pose, DataOrigin.DERIVED)
        return True

    def ingest(self, sample: FeedbackSample, *, now: MonotonicInstant) -> ProjectionUpdate:
        _concrete(sample, FeedbackSample, 'sample')
        self._observe(now)
        c = self._config
        if (sample.robot_id != c.robot_id or sample.backend != c.backend or sample.source_id != c.source_id):
            return self._result(ProjectionDisposition.IDENTITY_MISMATCH, now)
        if sample.context != self._context:
            return self._result(ProjectionDisposition.CONTEXT_MISMATCH, now)
        old = self._sample
        if (sample.received_at.clock_id != c.protection_clock_id or now.clock_id != c.protection_clock_id
                or sample.received_at.tick_ns > now.tick_ns
                or (old is not None and sample.source_seq > old.source_seq
                    and sample.received_at.tick_ns < old.received_at.tick_ns)):
            self._fault(DataQuality.INVALID, 'INVALID_RECEIVE_TIME')
            return self._result(ProjectionDisposition.INVALID_RECEIVE_TIME, now)
        if self._last_received is None or sample.received_at.tick_ns > self._last_received.tick_ns:
            self._last_received = sample.received_at
        if sample.source_time is not None and sample.source_time.clock_id != c.source_clock_id:
            self._fault(DataQuality.UNSYNCED, 'SOURCE_CLOCK_CHANGED')
            return self._result(ProjectionDisposition.CLOCK_MISMATCH, now)
        # A retired/stale proof need not retain arbitrary old packet history.
        if self._timing(now).quality is not DataQuality.FRESH:
            self._window = None
        if old is not None:
            if sample.source_seq < old.source_seq:
                witnessed = self._window.members.get(sample.source_seq) if self._window else None
                if witnessed is not None and replace(sample, received_at=witnessed.received_at) != witnessed:
                    self._fault(DataQuality.INVALID, 'WINDOW_SEQUENCE_CONFLICT')
                    return self._result(ProjectionDisposition.CONFLICT, now)
                return self._result(ProjectionDisposition.OUT_OF_ORDER, now)
            if sample.source_seq == old.source_seq:
                if replace(sample, received_at=old.received_at) == old:
                    return self._result(ProjectionDisposition.DUPLICATE, now)
                self._fault(DataQuality.INVALID, 'SEQUENCE_CONFLICT')
                return self._result(ProjectionDisposition.CONFLICT, now)
        if (sample.source_time is not None and self._source_watermark is not None
                and sample.source_time.tick_ns < self._source_watermark):
            self._fault(DataQuality.INVALID, 'SOURCE_TIME_REGRESSED')
            return self._result(ProjectionDisposition.SOURCE_REGRESSION, now)
        # Expire the previous window at adoption time, even without an intervening poll.
        previous_timing = self._timing(now)
        if previous_timing.quality is not DataQuality.FRESH:
            self._window = None
        self._sample = sample
        self._sample_context_generation = self._context_generation
        # A new estimate cannot relabel the same source instant as a new sample,
        # even if a missing-timestamp packet arrived between the two copies.
        if (self._mapping_resume_after is None or sample.source_time is not None
                and sample.source_time.tick_ns > self._mapping_resume_after):
            self._sample_mapping = self._mapping
            self._sample_mapping_generation = self._mapping_generation
            self._mapping_resume_after = None
        self._fk_pose = None
        self._position_moving = False
        if sample.source_time is not None:
            self._source_watermark = sample.source_time.tick_ns
        timing = self._timing(now)
        joints, _, controller = self._data(timing)
        self._advance_window(sample, timing, joints, controller)
        return self._result(ProjectionDisposition.ACCEPTED, now)

    def snapshot(self, *, now: MonotonicInstant) -> ProjectedState:
        self._observe(now)
        timing = self._timing(now)
        joints, pose, controller = self._data(timing)
        if not self._stationary_inputs(joints, controller):
            self._window = None
        motion = MotionState.UNKNOWN
        stationary = None
        if (controller.quality is DataQuality.FRESH and controller.value.motion_state is MotionState.MOVING
                or joints.quality is DataQuality.FRESH and (
                    any(abs(joint.velocity_rad_s) > self._config.max_velocity_rad_s for joint in joints.value)
                    or self._position_moving)):
            motion = MotionState.MOVING
        elif self._window is not None:
            w = self._window
            if w.last_bounds.earliest.tick_ns - w.first_bounds.latest.tick_ns >= self._config.stationary_window_ns:
                motion = MotionState.STOPPED
                stationary = StationaryEvidence(
                    self._config.robot_id, self._config.backend, self._context, self._config.source_id,
                    w.first.source_seq, w.last.source_seq, w.first.source_time, w.last.source_time,
                    w.first_bounds, w.last_bounds, w.last.received_at, self._not_before, timing.valid_until,
                )
        sample = self._sample
        state = ProjectedState(
            self._config.robot_id, self._config.backend, self._context, 0, now, self._config.source_id,
            sample.source_seq if sample else None, sample.source_time if sample else None,
            sample.context if sample else None, sample.received_at if sample else None, self._last_received,
            timing.bounds, timing.source_age, timing.receive_age, self._age(self._last_received, now),
            self._sample_mapping.revision if self._sample_mapping else None,
            joints, pose, controller, self._target, self._plan, motion, stationary, self._clock_fault,
        )
        # Ages/as_of are derived from fixed timestamps; they do not create stream events.
        signature = replace(state, observed_at=MonotonicInstant(self._config.protection_clock_id, 0),
                            source_age_ns=None, receive_age_ns=None, transport_age_ns=None)
        if signature != self._signature:
            self._state_seq += 1
            self._signature = signature
        return replace(state, state_seq=self._state_seq)

    def _result(self, disposition: ProjectionDisposition, now: MonotonicInstant) -> ProjectionUpdate:
        return ProjectionUpdate(disposition, self.snapshot(now=now))

    def _observe(self, now: MonotonicInstant) -> None:
        _instant(now, 'now')
        if (now.clock_id != self._config.protection_clock_id
                or self._last_now is not None and now.tick_ns < self._last_now):
            self._clock_fault = True
            self._window = None
        elif not self._clock_fault:
            self._last_now = now.tick_ns

    def _fault(self, quality: DataQuality, reason: str) -> None:
        if self._stream_fault is None or quality is DataQuality.INVALID:
            self._stream_fault = quality, reason
        self._window = None

    def _age(self, time: MonotonicInstant | None, now: MonotonicInstant) -> int | None:
        if self._clock_fault or time is None or time.clock_id != now.clock_id or time.tick_ns > now.tick_ns:
            return None
        return now.tick_ns - time.tick_ns

    def _timing(self, now: MonotonicInstant) -> _Timing:
        c, s, mapping = self._config, self._sample, self._sample_mapping
        if s is None:
            return _Timing(DataQuality.INVALID, 'NO_FEEDBACK')
        receive_age = self._age(s.received_at, now)
        bounds = None
        source_age = None
        negative_bound = False
        if s.source_time is not None:
            if c.source_clock_id == c.protection_clock_id:
                low = high = s.source_time.tick_ns
            elif mapping is not None:
                low = s.source_time.tick_ns + mapping.offset_ns - mapping.uncertainty_ns
                high = s.source_time.tick_ns + mapping.offset_ns + mapping.uncertainty_ns
            else:
                low = high = None
            if low is not None:
                negative_bound = low < 0
                if low >= 0:
                    bounds = SourceTimeBounds(MonotonicInstant(c.protection_clock_id, low),
                                              MonotonicInstant(c.protection_clock_id, high))
                    source_age = self._age(bounds.earliest, now)
        def result(quality, reason, valid_until=None):
            return _Timing(quality, reason, bounds, source_age, receive_age, valid_until)
        if self._clock_fault:
            return result(DataQuality.INVALID, 'PROTECTION_CLOCK_FAULT')
        if self._stream_fault is not None:
            return result(*self._stream_fault)
        if s.context != self._context or self._sample_context_generation != self._context_generation:
            return result(DataQuality.INVALID, 'CONTEXT_CHANGED')
        if s.source_time is None:
            return result(DataQuality.UNSYNCED, 'SOURCE_TIME_MISSING')
        if self._sample_mapping_generation != self._mapping_generation:
            return result(DataQuality.UNSYNCED, 'MAPPING_CHANGED')
        if c.source_clock_id != c.protection_clock_id:
            if mapping is None:
                return result(DataQuality.UNSYNCED, 'MAPPING_MISSING')
            if mapping.uncertainty_ns > c.max_clock_uncertainty_ns:
                return result(DataQuality.UNSYNCED, 'MAPPING_UNCERTAIN')
            # The mapping must cover both adoption/observation and the original receive time.
            if not (mapping.valid_from.tick_ns <= s.received_at.tick_ns <= now.tick_ns < mapping.valid_until.tick_ns):
                return result(DataQuality.UNSYNCED, 'MAPPING_EXPIRED')
        if negative_bound:
            return result(DataQuality.INVALID, 'SOURCE_BEFORE_CLOCK')
        if mapping is not None and not (mapping.valid_from.tick_ns <= bounds.earliest.tick_ns
                                        and bounds.latest.tick_ns < mapping.valid_until.tick_ns):
            return result(DataQuality.UNSYNCED, 'SOURCE_OUTSIDE_MAPPING')
        if bounds.earliest.tick_ns > s.received_at.tick_ns:
            return result(DataQuality.INVALID, 'SOURCE_IN_FUTURE')
        if bounds.latest.tick_ns > s.received_at.tick_ns:
            return result(DataQuality.UNSYNCED, 'SOURCE_TIME_UNCERTAIN')
        if source_age >= c.max_source_age_ns:
            return result(DataQuality.STALE, 'SOURCE_STALE')
        if receive_age >= c.max_receive_age_ns:
            return result(DataQuality.STALE, 'RECEIVE_STALE')
        expiry = min(bounds.earliest.tick_ns + c.max_source_age_ns,
                     s.received_at.tick_ns + c.max_receive_age_ns)
        if mapping is not None:
            expiry = min(expiry, mapping.valid_until.tick_ns)
        return result(DataQuality.FRESH, None, MonotonicInstant(c.protection_clock_id, expiry))

    def _data(self, timing: _Timing) -> tuple[ProjectedDatum, ProjectedDatum, ProjectedDatum]:
        s, c = self._sample, self._config
        raw_joints = s.joints if s else None
        raw_pose = self._fk_pose or (s.tool_pose if s else None)
        raw_controller = s.controller if s else None
        def datum(raw, value, reason=None, *, allow_derived=False):
            if raw is None:
                return ProjectedDatum(None, None, DataQuality.INVALID, 'MISSING_DATA', None)
            if raw.invalid_reason is not None:
                reason = raw.invalid_reason
            if raw.origin is not c.feedback_origin and not (allow_derived and raw.origin is DataOrigin.DERIVED):
                reason = 'UNTRUSTED_ORIGIN'
            if reason is not None:
                return ProjectedDatum(value, raw.origin, DataQuality.INVALID, reason, None)
            return ProjectedDatum(value, raw.origin, timing.quality, timing.reason, timing.valid_until)
        joint_reason = None
        if raw_joints is not None:
            if tuple(joint.name for joint in raw_joints.joints) != c.joint_names:
                joint_reason = 'JOINT_LAYOUT_MISMATCH'
            elif any(joint.position_rad is None or joint.velocity_rad_s is None for joint in raw_joints.joints):
                joint_reason = 'JOINT_VALUE_UNKNOWN'
        joints = datum(raw_joints, raw_joints.joints if raw_joints else None, joint_reason)
        pose_reason = None
        if raw_pose is not None and (raw_pose.pose.frame_id != c.frame_id or raw_pose.pose.tool_id != c.tool_id):
            pose_reason = 'POSE_SCOPE_MISMATCH'
        pose = datum(raw_pose, raw_pose.pose if raw_pose else None, pose_reason, allow_derived=True)
        if raw_pose is not None and raw_pose.origin is DataOrigin.DERIVED:
            severity = {DataQuality.FRESH: 0, DataQuality.STALE: 1,
                        DataQuality.UNSYNCED: 2, DataQuality.INVALID: 3}
            if severity[joints.quality] > severity[pose.quality]:
                pose = replace(pose, quality=joints.quality, reason=joints.reason, valid_until=None)
        controller = datum(raw_controller, raw_controller)
        return joints, pose, controller

    def _stationary_inputs(self, joints: ProjectedDatum, controller: ProjectedDatum) -> bool:
        return (joints.quality is DataQuality.FRESH and controller.quality is DataQuality.FRESH
                and controller.value.motion_state is MotionState.STOPPED
                and all(abs(joint.velocity_rad_s) <= self._config.max_velocity_rad_s for joint in joints.value))

    def _advance_window(self, sample: FeedbackSample, timing: _Timing,
                        joints: ProjectedDatum, controller: ProjectedDatum) -> None:
        if not self._stationary_inputs(joints, controller):
            self._window = None
            return
        bounds = timing.bounds
        if self._not_before is not None and bounds.earliest.tick_ns < self._not_before.tick_ns:
            self._window = None
            return
        previous = self._window
        if previous is not None:
            if (sample.source_seq != previous.last.source_seq + 1
                    or sample.source_time.tick_ns <= previous.last.source_time.tick_ns
                    or bounds.latest.tick_ns - previous.last_bounds.earliest.tick_ns > self._config.max_sample_gap_ns
                    or sample.received_at.tick_ns - previous.last.received_at.tick_ns > self._config.max_sample_gap_ns):
                previous = None
        if previous is not None:
            members = dict(previous.members)
            members[sample.source_seq] = sample
            # Keep the shortest observed suffix that still spans the required
            # guaranteed duration. Retain members for contradictory replay checks.
            while len(members) > 1:
                candidates = iter(members.values())
                next(candidates)
                candidate = next(candidates)
                candidate_latest = bounds.latest.tick_ns - (sample.source_time.tick_ns - candidate.source_time.tick_ns)
                if bounds.earliest.tick_ns - candidate_latest < self._config.stationary_window_ns:
                    break
                del members[next(iter(members))]
            samples = tuple(members.values())
            by_joint = tuple(zip(*(tuple(j.position_rad for j in member.joints.joints)
                                   for member in samples), strict=True))
            low = tuple(min(values) for values in by_joint)
            high = tuple(max(values) for values in by_joint)
            if any(high_value - low_value > self._config.max_position_delta_rad
                   for low_value, high_value in zip(low, high, strict=True)):
                self._position_moving = True
                previous = None
            else:
                previous.last, previous.last_bounds = sample, bounds
                previous.members = members
                previous.first = samples[0]
                elapsed = sample.source_time.tick_ns - previous.first.source_time.tick_ns
                previous.first_bounds = SourceTimeBounds(
                    MonotonicInstant(self._config.protection_clock_id, bounds.earliest.tick_ns - elapsed),
                    MonotonicInstant(self._config.protection_clock_id, bounds.latest.tick_ns - elapsed),
                )
        if previous is None:
            previous = _Window(sample, bounds, sample, bounds, {sample.source_seq: sample})
        self._window = previous
