"""T06: observed state retains its scope, source, quality and sample identity."""
from dataclasses import FrozenInstanceError, replace

import pytest

from framework.domain.discovery import JointObservation, MotionState
from framework.domain.time import MonotonicInstant
from framework.domain.values import FrameId, RobotId, ToolId


@pytest.mark.t06_projection
def test_unknown_actual_remains_unknown_while_target_and_plan_change(projection_case):
    c = projection_case()
    d, p = c.domain, c.projection
    before = p.snapshot(now=c.at(0))
    assert before.joints.value is before.tool_pose.value is before.controller.value is None
    assert before.motion_state is MotionState.UNKNOWN and before.stationary is None
    assert before.joints.quality is d.DataQuality.INVALID
    target = d.ProjectionTarget('command-1', c.goal, c.context)
    p.set_target(target, now=c.at(0))
    plan = d.ProjectionPlan('command-1', 'plan-1', 'a' * 64, c.context)
    planned = p.set_plan(plan, now=c.at(0))
    assert planned.target == target and planned.plan == plan
    assert planned.joints == before.joints and planned.tool_pose == before.tool_pose
    assert planned.source_seq is None and planned.stationary is None
    changed = p.set_target(replace(target, command_id='command-2'), now=c.at(0))
    assert changed.plan is None
    with pytest.raises(ValueError):
        p.set_plan(plan, now=c.at(0))
    assert p.snapshot(now=c.at(0)) == changed
    with pytest.raises(FrozenInstanceError):
        planned.state_seq = 20


@pytest.mark.t06_projection
def test_per_class_quality_preserves_partial_unknowns_and_input_origin(projection_case):
    c = projection_case()
    value = c.sample(joints=c.domain.JointFeedback([
        JointObservation('j1', None, None), JointObservation('j2', 0, 0),
    ], c.domain.DataOrigin.SIMULATED), tool_pose=None)
    state = c.projection.ingest(value, now=c.at(0)).state
    assert state.joints.value[0].position_rad is None
    assert state.joints.value[0].velocity_rad_s is None
    assert state.joints.quality is c.domain.DataQuality.INVALID
    assert state.joints.origin is c.domain.DataOrigin.SIMULATED
    assert state.tool_pose.value is None and state.tool_pose.origin is None
    assert state.controller.quality is c.domain.DataQuality.FRESH
    assert state.motion_state is MotionState.UNKNOWN
    unknown = replace(value.controller, control_mode=None, estop_active=None,
                      protective_stop_active=None, motion_state=MotionState.UNKNOWN)
    state = c.feed(2, 1, controller=unknown).state
    assert state.controller.value.estop_active is None
    assert state.controller.value.protective_stop_active is None
    assert state.controller.value.control_mode is None
    assert state.motion_state is MotionState.UNKNOWN


@pytest.mark.t06_projection
@pytest.mark.parametrize('field', ['robot_id', 'backend', 'source_id', 'context'])
def test_foreign_feedback_does_not_replace_the_current_sample(field, projection_case):
    c = projection_case()
    first = c.feed().state
    changes = {'robot_id': RobotId('other'), 'backend': replace(c.backend, backend_epoch='epoch-old'),
               'source_id': 'other-source', 'context': replace(c.context, scene_revision='old-scene')}
    result = c.feed(2, 1, **{field: changes[field]})
    expected = (c.domain.ProjectionDisposition.CONTEXT_MISMATCH if field == 'context'
                else c.domain.ProjectionDisposition.IDENTITY_MISMATCH)
    assert result.disposition is expected
    assert result.state.source_seq == 1 and result.state.received_at == first.received_at
    assert result.state.joints == first.joints


@pytest.mark.t06_projection
@pytest.mark.parametrize('part', ['joints-order', 'joints-extra', 'pose-frame', 'pose-tool', 'origin', 'invalid'])
def test_configuration_and_adapter_faults_are_visible_per_class(part, projection_case):
    c = projection_case()
    raw = c.sample()
    changes = {
        'joints-order': {'joints': replace(raw.joints, joints=list(reversed(raw.joints.joints)))},
        'joints-extra': {'joints': replace(raw.joints, joints=(*raw.joints.joints, JointObservation('j3', 0, 0)))},
        'pose-frame': {'tool_pose': replace(raw.tool_pose, pose=replace(c.pose, frame_id=FrameId('cell/other')))},
        'pose-tool': {'tool_pose': replace(raw.tool_pose, pose=replace(c.pose, tool_id=ToolId('other')))},
        'origin': {'joints': replace(raw.joints, origin=c.domain.DataOrigin.DERIVED)},
        'invalid': {'joints': replace(raw.joints, invalid_reason='encoder-fault')},
    }
    state = c.projection.ingest(replace(raw, **changes[part]), now=c.at(0)).state
    invalid = state.tool_pose if part.startswith('pose') else state.joints
    assert invalid.quality is c.domain.DataQuality.INVALID and invalid.reason
    assert invalid.value is not None
    assert state.controller.quality is c.domain.DataQuality.FRESH


@pytest.mark.t06_projection
@pytest.mark.parametrize('field,value', [
    ('capability_revision', 2), ('robot_model_revision', 'model-2'),
    ('scene_revision', 'scene-2'), ('calibration_revision', 'cal-2'),
])
def test_context_change_invalidates_actual_target_and_plan_until_new_feedback(field, value, projection_case):
    c = projection_case()
    c.feed()
    c.projection.set_target(c.domain.ProjectionTarget('command-1', c.goal, c.context), now=c.at(0))
    c.projection.set_plan(c.domain.ProjectionPlan('command-1', 'plan-1', 'a' * 64, c.context), now=c.at(0))
    context = replace(c.context, **{field: value})
    state = c.projection.change_context(context, now=c.at(1))
    assert state.context == context and state.sample_context == c.context
    assert state.joints.value is not None and state.joints.quality is c.domain.DataQuality.INVALID
    assert state.target is state.plan is state.stationary is None
    assert c.feed(2, 2).disposition is c.domain.ProjectionDisposition.CONTEXT_MISMATCH
    fresh = c.feed(3, 3, context=context).state
    assert fresh.joints.quality is c.domain.DataQuality.FRESH
    assert fresh.sample_context == context and fresh.stationary is None


@pytest.mark.t06_projection
def test_fk_is_derived_and_keeps_original_sample_age_and_expiration(projection_case):
    c = projection_case()
    before = c.feed(1, 10, received=12, tool_pose=None).state
    result = c.domain.ForwardKinematicsResult(c.robot, c.backend, c.context, 'encoder-a', 1, c.pose)
    assert c.projection.apply_fk(result, now=c.at(15))
    state = c.projection.snapshot(now=c.at(15))
    assert state.tool_pose.origin is c.domain.DataOrigin.DERIVED
    assert state.tool_pose.value == c.pose
    assert state.received_at == before.received_at and state.source_time == before.source_time
    assert state.source_age_ns == 5 and state.receive_age_ns == 3
    assert state.tool_pose.valid_until == before.joints.valid_until == c.at(32)
    stale = c.projection.snapshot(now=c.at(32))
    assert stale.tool_pose.quality is c.domain.DataQuality.STALE


@pytest.mark.t06_projection
@pytest.mark.parametrize('change', ['sequence', 'context', 'robot', 'epoch', 'frame', 'tool', 'missing-joints'])
def test_late_or_unbound_fk_cannot_populate_actual(change, projection_case):
    c = projection_case()
    c.feed(2, 10, tool_pose=None, **({'joints': None} if change == 'missing-joints' else {}))
    result = c.domain.ForwardKinematicsResult(c.robot, c.backend, c.context, 'encoder-a', 2, c.pose)
    changes = {'sequence': {'source_seq': 1}, 'context': {'context': replace(c.context, scene_revision='old')},
               'robot': {'robot_id': RobotId('other')}, 'epoch': {'backend': replace(c.backend, backend_epoch='old')},
               'frame': {'pose': replace(c.pose, frame_id=FrameId('other/world'))},
               'tool': {'pose': replace(c.pose, tool_id=ToolId('other'))}, 'missing-joints': {}}
    assert not c.projection.apply_fk(replace(result, **changes[change]), now=c.at(10))
    assert c.projection.snapshot(now=c.at(10)).tool_pose.value is None


@pytest.mark.t06_order
def test_duplicate_and_older_sample_only_update_transport_receipt(projection_case):
    c = projection_case()
    first = c.feed(4, 10, received=11).state
    duplicate = c.feed(4, 10, received=15)
    assert duplicate.disposition is c.domain.ProjectionDisposition.DUPLICATE
    assert duplicate.state.source_seq == 4 and duplicate.state.received_at == c.at(11)
    assert duplicate.state.source_age_ns == 5 and duplicate.state.receive_age_ns == 4
    assert duplicate.state.last_received_at == c.at(15) and duplicate.state.transport_age_ns == 0
    older = c.feed(3, 9, received=16, position=1)
    assert older.disposition is c.domain.ProjectionDisposition.OUT_OF_ORDER
    assert older.state.joints.value == first.joints.value and older.state.source_seq == 4
    stale = c.feed(4, 10, received=31).state
    assert stale.joints.quality is c.domain.DataQuality.STALE
    assert stale.receive_age_ns == 20 and stale.transport_age_ns == 0
    assert first.joints.quality is c.domain.DataQuality.FRESH and first.source_age_ns == 1


@pytest.mark.t06_order
@pytest.mark.parametrize('fault', ['conflict', 'regression', 'clock'])
def test_inconsistent_stream_latches_quality_and_cannot_recover_with_favorable_packets(fault, projection_case):
    c = projection_case()
    c.feed(2, 10)
    if fault == 'conflict':
        result = c.feed(2, 10, received=11, position=1)
        disposition = c.domain.ProjectionDisposition.CONFLICT
    elif fault == 'regression':
        result = c.feed(3, 9, received=11)
        disposition = c.domain.ProjectionDisposition.SOURCE_REGRESSION
    else:
        result = c.feed(3, 11, source_time=MonotonicInstant('new-source-clock', 0))
        disposition = c.domain.ProjectionDisposition.CLOCK_MISMATCH
    assert result.disposition is disposition
    quality = c.domain.DataQuality.UNSYNCED if fault == 'clock' else c.domain.DataQuality.INVALID
    assert result.state.joints.quality is quality
    assert c.feed(4, 12).state.joints.quality is quality
    assert result.state.stationary is None and result.state.motion_state is MotionState.UNKNOWN


@pytest.mark.t06_order
def test_new_sequence_with_paused_source_keeps_old_source_age(projection_case):
    c = projection_case()
    c.feed(1, 0)
    for seq, received in [(2, 10), (3, 20), (4, 30)]:
        state = c.feed(seq, 0, received=received).state
        assert state.source_age_ns == received and state.receive_age_ns == 0
        assert state.stationary is None
    assert state.joints.quality is c.domain.DataQuality.STALE


@pytest.mark.t06_order
def test_state_sequence_tracks_quality_changes_but_not_pure_age_reads(projection_case):
    c = projection_case()
    start = c.feed().state
    one = c.projection.snapshot(now=c.at(1))
    two = c.projection.snapshot(now=c.at(2))
    expired = c.projection.snapshot(now=c.at(20))
    assert start.state_seq == one.state_seq == two.state_seq
    assert expired.state_seq > two.state_seq
    assert one.source_age_ns == 1 and two.source_age_ns == 2


@pytest.mark.t06_projection
@pytest.mark.parametrize('field,value,error', [
    ('max_source_age_ns', 0, ValueError), ('max_receive_age_ns', True, TypeError),
    ('stationary_window_ns', -1, ValueError), ('max_sample_gap_ns', 1.5, TypeError),
    ('max_clock_uncertainty_ns', -1, ValueError), ('max_velocity_rad_s', float('nan'), ValueError),
    ('max_position_delta_rad', float('inf'), ValueError), ('max_position_delta_rad', -1, ValueError),
    ('joint_names', [], ValueError), ('joint_names', ['j1', 'j1'], ValueError),
    ('source_id', '', ValueError), ('source_clock_id', ' ', ValueError),
])
def test_projection_configuration_has_explicit_validated_units(field, value, error, projection_case):
    c = projection_case()
    with pytest.raises(error):
        replace(c.config, **{field: value})


@pytest.mark.t06_projection
def test_input_values_are_concrete_immutable_and_do_not_alias_lists(projection_case):
    c = projection_case()
    joints = [JointObservation('j1', 0, 0), JointObservation('j2', 0, 0)]
    feedback = c.domain.JointFeedback(joints, c.domain.DataOrigin.SIMULATED)
    joints.clear()
    assert len(feedback.joints) == 2 and type(feedback.joints) is tuple
    with pytest.raises(ValueError):
        replace(feedback, joints=[feedback.joints[0], feedback.joints[0]])
    with pytest.raises(TypeError):
        replace(c.sample(), source_seq=True)
    with pytest.raises(ValueError):
        replace(c.sample(), source_seq=-1)
    with pytest.raises(TypeError):
        replace(c.sample().controller, estop_active=0)
    with pytest.raises(TypeError):
        c.projection.ingest(object(), now=c.at(0))
    with pytest.raises(TypeError):
        c.projection.snapshot(now=0)
    with pytest.raises(TypeError):
        replace(c.mapping, uncertainty_ns=True)
    with pytest.raises(ValueError):
        replace(c.mapping, valid_until=c.at(0))
    with pytest.raises(ValueError):
        replace(c.config, feedback_origin=c.domain.DataOrigin.MEASURED)
