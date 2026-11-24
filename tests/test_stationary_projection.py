"""T10 state-evidence slice; no backend STOP call or execution unlock exists here."""
from dataclasses import replace

import pytest

from framework.domain.discovery import JointObservation, MotionState

pytestmark = pytest.mark.t10_stationary


def test_only_a_complete_fresh_new_sample_window_proves_stationarity(projection_case):
    c = projection_case()
    assert c.feed(1, 0).state.motion_state is MotionState.UNKNOWN
    assert c.feed(2, 5).state.stationary is None
    assert c.projection.snapshot(now=c.at(10)).stationary is None
    stopped = c.feed(3, 10).state
    assert stopped.motion_state is MotionState.STOPPED
    evidence = stopped.stationary
    assert evidence.robot_id == c.robot and evidence.backend == c.backend
    assert evidence.context == c.context and evidence.source_id == 'encoder-a'
    assert (evidence.start_seq, evidence.end_seq) == (1, 3)
    assert evidence.start_bounds.latest == c.at(0) and evidence.end_bounds.earliest == c.at(10)
    assert evidence.source_start.clock_id == evidence.source_end.clock_id == 'source-clock'
    assert evidence.received_end_at == c.at(10) and evidence.valid_until == c.at(30)
    expired = c.projection.snapshot(now=c.at(30))
    assert expired.stationary is None and expired.motion_state is MotionState.UNKNOWN
    assert stopped.stationary == evidence


def test_duplicate_receipts_and_polls_never_complete_a_stationary_window(projection_case):
    c = projection_case()
    c.feed(1, 0)
    for received in [5, 10, 15, 20]:
        assert c.feed(1, 0, received=received).state.stationary is None
    assert c.projection.snapshot(now=c.at(21)).motion_state is MotionState.UNKNOWN


@pytest.mark.parametrize('break_kind', [
    'gap', 'sequence-gap', 'paused', 'missing', 'empty', 'unknown-velocity',
    'moving', 'fast', 'position', 'untrusted', 'invalid',
])
def test_discontinuity_restarts_the_whole_stationary_window(break_kind, projection_case):
    c = projection_case()
    c.feed(1, 0)
    c.feed(2, 5)
    seq, tick = (4, 10) if break_kind == 'sequence-gap' else (3, 12 if break_kind == 'gap' else 10)
    kwargs = {}
    raw = c.sample(seq, tick)
    if break_kind == 'paused':
        tick, kwargs = 5, {'received': 10}
    if break_kind in {'missing', 'empty', 'unknown-velocity', 'untrusted', 'invalid'}:
        kwargs['joints'] = {
            'missing': None,
            'empty': replace(raw.joints, joints=[]),
            'unknown-velocity': replace(raw.joints, joints=[JointObservation('j1', 0, None), JointObservation('j2', 0, 0)]),
            'untrusted': replace(raw.joints, origin=c.domain.DataOrigin.DERIVED),
            'invalid': replace(raw.joints, invalid_reason='encoder-fault'),
        }[break_kind]
    if break_kind == 'moving':
        kwargs['controller'] = replace(raw.controller, motion_state=MotionState.MOVING)
    if break_kind == 'fast':
        kwargs['velocity'] = .01001
    if break_kind == 'position':
        kwargs['position'] = .00101
    state = c.feed(seq, tick, **kwargs).state
    assert state.stationary is None
    if break_kind in {'moving', 'fast', 'position'}:
        assert state.motion_state is MotionState.MOVING
    next_tick = max(tick, 10) + 5
    assert c.feed(seq + 1, next_tick).state.stationary is None


def test_velocity_and_window_position_threshold_equality_are_allowed(projection_case):
    c = projection_case()
    c.feed(1, 0, velocity=.01)
    c.feed(2, 5, position=.0005, velocity=-.01)
    state = c.feed(3, 10, position=.001, velocity=.01).state
    assert state.motion_state is MotionState.STOPPED


def test_position_range_is_over_whole_window_not_adjacent_pairs(projection_case):
    c = projection_case()
    c.feed(1, 0, position=0)
    c.feed(2, 5, position=.0006)
    state = c.feed(3, 10, position=.0012).state
    assert state.motion_state is MotionState.MOVING and state.stationary is None


def test_position_extrema_not_just_anchor_are_used(projection_case):
    c = projection_case()
    c.feed(1, 0, position=0)
    c.feed(2, 5, position=-.0006)
    assert c.feed(3, 10, position=.0006).state.stationary is None


def test_uncertainty_shortens_guaranteed_duration_and_bounds_sample_gap(projection_case):
    c = projection_case(max_sample_gap_ns=8)
    c.projection.set_mapping(replace(c.mapping, uncertainty_ns=1), now=c.at(0))
    c.feed(1, 2, received=3)
    c.feed(2, 7, received=8)
    assert c.feed(3, 12, received=13).state.stationary is None  # Guaranteed duration only 8.
    stopped = c.feed(4, 14, received=15).state
    assert stopped.stationary is not None
    assert stopped.stationary.end_bounds.earliest.tick_ns - stopped.stationary.start_bounds.latest.tick_ns == 10


def test_old_sample_arriving_after_stop_boundary_cannot_start_new_round(projection_case):
    c = projection_case()
    c.feed(1, 0)
    c.feed(2, 5)
    assert c.feed(3, 10).state.stationary is not None
    cleared = c.projection.begin_stationary_check(c.at(12), now=c.at(12))
    assert cleared.stationary is None
    assert c.feed(4, 11, received=13).state.stationary is None
    assert c.feed(5, 15).state.stationary is None
    assert c.feed(6, 20).state.stationary is None
    stopped = c.feed(7, 25).state
    assert stopped.stationary.start_seq == 5
    assert stopped.stationary.not_before == c.at(12)
    assert stopped.stationary.start_bounds.earliest.tick_ns >= 12


def test_stationary_barrier_requires_its_whole_uncertainty_interval_after_boundary(projection_case):
    c = projection_case(max_sample_gap_ns=8)
    c.projection.set_mapping(replace(c.mapping, uncertainty_ns=1), now=c.at(0))
    c.projection.begin_stationary_check(c.at(10), now=c.at(10))
    c.feed(1, 10, received=11)  # Earliest sample could predate barrier.
    c.feed(2, 15, received=16)
    c.feed(3, 20, received=21)
    assert c.feed(4, 25, received=26).state.stationary is None
    stopped = c.feed(5, 27, received=28).state
    assert stopped.stationary.start_seq == 2


def test_stale_gap_cannot_be_bridged_after_no_intermediate_poll(projection_case):
    c = projection_case(max_sample_gap_ns=100)
    c.feed(1, 0)
    c.feed(2, 5)
    assert c.feed(3, 25).state.stationary is None  # Previous receive age reached 20.
    assert c.feed(4, 30).state.stationary is None
    assert c.feed(5, 35).state.stationary is not None


def test_new_mapping_and_context_always_start_new_windows(projection_case):
    c = projection_case()
    c.feed(1, 0)
    c.feed(2, 5)
    c.projection.set_mapping(replace(c.mapping, revision='sync-2'), now=c.at(5))
    assert c.feed(3, 10).state.stationary is None
    assert c.feed(4, 15).state.stationary is None
    assert c.feed(5, 20).state.stationary is not None
    context = replace(c.context, scene_revision='scene-2')
    assert c.projection.change_context(context, now=c.at(20)).stationary is None
    assert c.feed(6, 25, context=context).state.stationary is None


def test_untrusted_or_missing_controller_cannot_prove_stopped(projection_case):
    c = projection_case()
    for seq, tick in [(1, 0), (2, 5), (3, 10)]:
        assert c.feed(seq, tick, controller=None).state.motion_state is MotionState.UNKNOWN


def test_stationary_boundary_cannot_move_backward_or_into_future(projection_case):
    c = projection_case()
    c.projection.begin_stationary_check(c.at(5), now=c.at(5))
    with pytest.raises(ValueError):
        c.projection.begin_stationary_check(c.at(4), now=c.at(5))
    with pytest.raises(ValueError):
        c.projection.begin_stationary_check(c.at(6), now=c.at(5))
