"""T42: source timing never borrows freshness from transport activity."""
from dataclasses import replace

import pytest

from framework.domain.time import MonotonicInstant

pytestmark = pytest.mark.t42_feedback_clock


def test_delayed_source_has_independent_age_despite_fresh_receipt(projection_case):
    c = projection_case()
    state = c.feed(1, 0, received=40, now=45).state
    assert state.source_age_ns == 45 and state.receive_age_ns == 5
    assert state.joints.quality is c.domain.DataQuality.STALE
    assert state.joints.reason == 'SOURCE_STALE'
    assert state.joints.valid_until is None


@pytest.mark.parametrize('kind,limit', [('source', 30), ('receive', 20), ('mapping', 15)])
def test_freshness_has_half_open_exact_boundaries(kind, limit, projection_case):
    c = projection_case(max_receive_age_ns=100 if kind == 'source' else 20)
    if kind == 'mapping':
        c.projection.set_mapping(replace(c.mapping, valid_until=c.at(limit)), now=c.at(0))
    state = c.feed().state
    assert state.joints.valid_until == c.at(limit)
    assert c.projection.snapshot(now=c.at(limit - 1)).joints.quality is c.domain.DataQuality.FRESH
    at_limit = c.projection.snapshot(now=c.at(limit))
    expected = c.domain.DataQuality.UNSYNCED if kind == 'mapping' else c.domain.DataQuality.STALE
    assert at_limit.joints.quality is expected
    assert c.projection.snapshot(now=c.at(limit + 1)).joints.quality is expected


def test_uncertainty_uses_oldest_source_bound_and_earliest_expiry(projection_case):
    c = projection_case(max_receive_age_ns=100)
    mapping = replace(c.mapping, offset_ns=10, uncertainty_ns=2)
    c.projection.set_mapping(mapping, now=c.at(0))
    state = c.feed(1, 10, received=22, now=30).state
    assert state.source_time_bounds.earliest == c.at(18)
    assert state.source_time_bounds.latest == c.at(22)
    assert state.source_age_ns == 12 and state.receive_age_ns == 8
    assert state.joints.valid_until == c.at(48)
    assert c.projection.snapshot(now=c.at(47)).joints.quality is c.domain.DataQuality.FRESH
    assert c.projection.snapshot(now=c.at(48)).joints.quality is c.domain.DataQuality.STALE


@pytest.mark.parametrize('condition,quality,reason', [
    ('missing-map', 'UNSYNCED', 'MAPPING_MISSING'),
    ('uncertain', 'UNSYNCED', 'MAPPING_UNCERTAIN'),
    ('not-yet-valid', 'UNSYNCED', 'MAPPING_EXPIRED'),
    ('missing-source', 'UNSYNCED', 'SOURCE_TIME_MISSING'),
    ('future', 'INVALID', 'SOURCE_IN_FUTURE'),
    ('future-overlap', 'UNSYNCED', 'SOURCE_TIME_UNCERTAIN'),
    ('negative-map', 'INVALID', 'SOURCE_BEFORE_CLOCK'),
])
def test_untrustworthy_source_time_is_explicit(condition, quality, reason, projection_case):
    c = projection_case(mapped=False)
    mapping = c.mapping
    if condition == 'uncertain':
        mapping = replace(mapping, uncertainty_ns=3)
    if condition == 'not-yet-valid':
        mapping = replace(mapping, valid_from=c.at(11))
    if condition == 'future-overlap':
        mapping = replace(mapping, uncertainty_ns=1)
    if condition == 'negative-map':
        mapping = replace(mapping, offset_ns=-20)
    if condition != 'missing-map':
        c.projection.set_mapping(mapping, now=c.at(0))
    state = c.feed(1, 11 if condition == 'future' else 10, received=10,
                   **({'source_time': None} if condition == 'missing-source' else {})).state
    assert state.joints.quality.name == quality and state.joints.reason == reason
    assert state.stationary is None and state.joints.valid_until is None


def test_mapping_update_does_not_reinterpret_or_refresh_an_old_sample(projection_case):
    c = projection_case()
    old = c.feed(1, 0).state
    changed = c.projection.set_mapping(replace(c.mapping, revision='sync-2', offset_ns=10), now=c.at(10))
    assert changed.joints.quality is c.domain.DataQuality.UNSYNCED
    assert changed.source_age_ns == 10 and changed.mapping_revision == 'sync-1'
    duplicate = c.feed(1, 0, received=10).state
    assert duplicate.joints.quality is c.domain.DataQuality.UNSYNCED
    assert duplicate.received_at == old.received_at
    fresh = c.feed(2, 10, received=20).state
    assert fresh.source_age_ns == 0 and fresh.mapping_revision == 'sync-2'
    assert fresh.joints.quality is c.domain.DataQuality.FRESH


def test_mapping_cannot_recover_delayed_future_data_by_waiting(projection_case):
    c = projection_case()
    c.feed(1, 15, received=10)
    later = c.projection.snapshot(now=c.at(20))
    assert later.joints.quality is c.domain.DataQuality.INVALID
    assert later.joints.reason == 'SOURCE_IN_FUTURE'


def test_same_clock_needs_no_map_and_rejects_remapping(projection_case):
    c = projection_case(source_clock_id='control-clock', mapped=False)
    state = c.feed(1, 5).state
    assert state.source_age_ns == state.receive_age_ns == 0
    assert state.joints.quality is c.domain.DataQuality.FRESH
    with pytest.raises(ValueError):
        c.projection.set_mapping(replace(c.mapping, source_clock_id='control-clock'), now=c.at(5))


@pytest.mark.parametrize('kind', ['regression', 'domain'])
def test_protection_clock_failure_latches_even_if_old_clock_returns(kind, projection_case):
    c = projection_case()
    c.feed(1, 10)
    bad_now = c.at(9) if kind == 'regression' else MonotonicInstant('other-clock', 11)
    fault = c.projection.snapshot(now=bad_now)
    assert fault.joints.quality is c.domain.DataQuality.INVALID
    assert fault.clock_fault and fault.stationary is None
    assert c.projection.snapshot(now=c.at(12)).joints.quality is c.domain.DataQuality.INVALID


@pytest.mark.parametrize('kind', ['future', 'clock', 'regression'])
def test_invalid_receive_timestamp_never_overwrites_valid_actual(kind, projection_case):
    c = projection_case()
    c.feed(1, 10)
    received = {'future': c.at(12), 'clock': MonotonicInstant('other', 11), 'regression': c.at(9)}[kind]
    result = c.projection.ingest(replace(c.sample(2, 11), received_at=received), now=c.at(11))
    assert result.disposition is c.domain.ProjectionDisposition.INVALID_RECEIVE_TIME
    assert result.state.source_seq == 1
    assert result.state.joints.quality is c.domain.DataQuality.INVALID


def test_clock_mapping_scope_and_integer_boundaries_are_checked(projection_case):
    c = projection_case()
    with pytest.raises(ValueError):
        c.projection.set_mapping(replace(c.mapping, source_clock_id='other'), now=c.at(0))
    with pytest.raises(ValueError):
        c.projection.set_mapping(replace(c.mapping, valid_from=MonotonicInstant('other', 0),
                                        valid_until=MonotonicInstant('other', 100)), now=c.at(0))
    with pytest.raises(TypeError):
        replace(c.mapping, offset_ns=True)
