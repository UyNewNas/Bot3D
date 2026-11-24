"""Independent review regressions and legitimate neighboring cases."""
from dataclasses import replace

import pytest

from framework.domain.discovery import MotionState


@pytest.mark.t42_feedback_clock
@pytest.mark.parametrize('source,uncertainty,receive', [(8, 0, 20), (20, 1, 21)])
def test_whole_mapped_source_interval_must_be_covered(source, uncertainty, receive, projection_case):
    c = projection_case(mapped=False)
    mapping = replace(c.mapping, valid_from=c.at(20), uncertainty_ns=uncertainty)
    c.projection.set_mapping(mapping, now=c.at(20))
    state = c.feed(1, source, received=receive).state
    assert state.joints.quality is c.domain.DataQuality.UNSYNCED
    assert state.joints.reason == 'SOURCE_OUTSIDE_MAPPING'
    assert state.stationary is None


@pytest.mark.t42_feedback_clock
def test_mapping_start_equality_is_valid_for_whole_source_interval(projection_case):
    c = projection_case(mapped=False)
    c.projection.set_mapping(replace(c.mapping, valid_from=c.at(20), uncertainty_ns=1), now=c.at(20))
    state = c.feed(1, 21, received=22).state
    assert state.source_time_bounds.earliest == c.at(20)
    assert state.joints.quality is c.domain.DataQuality.FRESH


@pytest.mark.t42_feedback_clock
@pytest.mark.parametrize('missing_between', [False, True])
def test_remapping_cannot_make_repeated_source_time_fresh(missing_between, projection_case):
    c = projection_case()
    c.feed(1, 0)
    assert c.projection.snapshot(now=c.at(40)).joints.quality is c.domain.DataQuality.STALE
    c.projection.set_mapping(replace(c.mapping, revision='sync-2', offset_ns=40), now=c.at(40))
    if missing_between:
        c.feed(2, 0, received=40, source_time=None)
    repeated = c.feed(3, 0, received=40).state
    assert repeated.joints.quality is c.domain.DataQuality.UNSYNCED
    assert repeated.source_age_ns == 40 and repeated.received_at == c.at(40)
    assert repeated.stationary is None
    resumed = c.feed(4, 5, received=45).state
    assert resumed.source_age_ns == 0 and resumed.joints.quality is c.domain.DataQuality.FRESH


@pytest.mark.t06_projection
def test_context_round_trip_requires_a_new_packet_and_cannot_revive_old_fk(projection_case):
    c = projection_case()
    c.feed(1, 0, velocity=.2)
    c.projection.change_context(replace(c.context, scene_revision='B'), now=c.at(2))
    returned = c.projection.change_context(c.context, now=c.at(2))
    assert returned.joints.quality is c.domain.DataQuality.INVALID
    assert returned.motion_state is MotionState.UNKNOWN
    assert c.feed(1, 0, received=2, velocity=.2).state.joints.quality is c.domain.DataQuality.INVALID
    # Construct using keywords so this test documents the complete FK identity.
    fk = c.domain.ForwardKinematicsResult(robot_id=c.robot, backend=c.backend, context=c.context,
                                          source_id='encoder-a', source_seq=1, pose=c.pose)
    assert not c.projection.apply_fk(fk, now=c.at(2))
    assert c.feed(2, 3).state.joints.quality is c.domain.DataQuality.FRESH
    assert c.projection.apply_fk(replace(fk, source_seq=2), now=c.at(3))


@pytest.mark.t06_projection
def test_fk_is_bound_to_the_specific_source_as_well_as_binding_and_sequence(projection_case):
    a, b = projection_case(), projection_case(source_id='encoder-b')
    a.feed(1, 0, position=0, tool_pose=None)
    b.feed(1, 0, source_id='encoder-b', position=1, tool_pose=None)
    fk = a.domain.ForwardKinematicsResult(robot_id=a.robot, backend=a.backend, context=a.context,
                                          source_id='encoder-a', source_seq=1, pose=a.pose)
    assert not b.projection.apply_fk(fk, now=b.at(0))
    assert b.projection.snapshot(now=b.at(0)).tool_pose.value is None
    assert a.projection.apply_fk(fk, now=a.at(0))
    assert a.projection.snapshot(now=a.at(0)).tool_pose.origin is a.domain.DataOrigin.DERIVED


@pytest.mark.t06_projection
@pytest.mark.parametrize('problem', ['missing', 'invalid', 'untrusted'])
def test_raw_derived_pose_inherits_its_same_packet_joint_basis_quality(problem, projection_case):
    c = projection_case()
    sample = c.sample()
    joints = {'missing': None, 'invalid': replace(sample.joints, invalid_reason='encoder-fault'),
              'untrusted': replace(sample.joints, origin=c.domain.DataOrigin.DERIVED)}[problem]
    derived = replace(sample.tool_pose, origin=c.domain.DataOrigin.DERIVED)
    state = c.feed(tool_pose=derived, joints=joints).state
    assert state.tool_pose.quality is c.domain.DataQuality.INVALID
    assert state.tool_pose.origin is c.domain.DataOrigin.DERIVED and state.tool_pose.value == c.pose
    assert state.tool_pose.valid_until is None


@pytest.mark.t06_projection
def test_derived_quality_inheritance_preserves_pose_specific_fault(projection_case):
    c = projection_case()
    sample = c.sample()
    pose = replace(sample.tool_pose, origin=c.domain.DataOrigin.DERIVED, invalid_reason='fk-singular')
    state = c.feed(tool_pose=pose, joints=None).state
    assert state.tool_pose.quality is c.domain.DataQuality.INVALID
    assert state.tool_pose.reason == 'fk-singular'


@pytest.mark.t10_stationary
@pytest.mark.parametrize('conflict', ['velocity', 'position', 'controller', 'source-time', 'missing'])
def test_conflict_for_live_window_member_invalidates_parking_proof(conflict, projection_case):
    c = projection_case()
    c.feed(1, 0)
    c.feed(2, 5)
    assert c.feed(3, 10).state.stationary is not None
    sample = c.sample(2, 5, received=11)
    changes = {'velocity': {'joints': replace(sample.joints, joints=[
        replace(sample.joints.joints[0], velocity_rad_s=7), sample.joints.joints[1]])},
        'position': {'joints': replace(sample.joints, joints=[
            replace(sample.joints.joints[0], position_rad=1), sample.joints.joints[1]])},
        'controller': {'controller': replace(sample.controller, motion_state=MotionState.MOVING)},
        'source-time': {'source_time': replace(sample.source_time, tick_ns=6)}, 'missing': {'joints': None}}
    result = c.projection.ingest(replace(sample, **changes[conflict]), now=c.at(11))
    assert result.disposition is c.domain.ProjectionDisposition.CONFLICT
    assert result.state.joints.quality is c.domain.DataQuality.INVALID
    assert result.state.stationary is None and result.state.motion_state is MotionState.UNKNOWN
    assert c.feed(4, 15).state.stationary is None


@pytest.mark.t10_stationary
def test_identical_live_window_retransmission_does_not_refresh_or_break_evidence(projection_case):
    c = projection_case()
    c.feed(1, 0)
    c.feed(2, 5)
    before = c.feed(3, 10).state
    repeated = c.feed(2, 5, received=11)
    assert repeated.disposition is c.domain.ProjectionDisposition.OUT_OF_ORDER
    assert repeated.state.stationary == before.stationary
    assert repeated.state.received_at == c.at(10)


@pytest.mark.t10_stationary
def test_old_outside_window_counter_packet_does_not_poison_recent_evidence(projection_case):
    c = projection_case()
    for seq, tick in [(1, 0), (2, 5), (3, 10), (4, 15), (5, 20)]:
        current = c.feed(seq, tick).state
    assert current.stationary.start_seq == 3  # Retain only the rolling proof interval.
    old = c.feed(2, 5, received=21, velocity=7)
    assert old.disposition is c.domain.ProjectionDisposition.OUT_OF_ORDER
    assert old.state.motion_state is MotionState.STOPPED
    assert old.state.stationary == current.stationary
