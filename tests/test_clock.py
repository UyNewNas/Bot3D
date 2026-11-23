"""T26/ports-clock only, not lease/deadline/SIM-pause product acceptance."""
from dataclasses import FrozenInstanceError
from typing import get_type_hints

import pytest

from framework.adapters.clocks import ManualMonotonicClock, SystemMonotonicClock
from framework.application.ports import MonotonicClock
from framework.domain.time import ClockDomainMismatch, MonotonicInstant

pytestmark = pytest.mark.t26_ports_clock


@pytest.mark.parametrize('value', [None, 1, True, b'clock'])
def test_clock_id_requires_string(value):
    with pytest.raises(TypeError):
        MonotonicInstant(value, 0)


@pytest.mark.parametrize('value', ['', ' ', '\t'])
def test_clock_id_must_not_be_blank(value):
    with pytest.raises(ValueError):
        MonotonicInstant(value, 0)


@pytest.mark.parametrize('value', [True, False, 0.0, float('nan'), float('inf'), None, '0'])
def test_ticks_require_exact_integers(value):
    with pytest.raises(TypeError):
        MonotonicInstant('clock', value)


def test_negative_ticks_rejected():
    with pytest.raises(ValueError):
        MonotonicInstant('clock', -1)


def test_snapshot_is_frozen_and_intervals_are_exact():
    reading = MonotonicInstant('clock', 2 ** 70)
    with pytest.raises(FrozenInstanceError):
        reading.tick_ns = 0
    assert reading.elapsed_ns_since(MonotonicInstant('clock', 2 ** 70 - 1)) == 1
    assert reading.elapsed_ns_since(reading) == 0


def test_other_clock_domains_cannot_be_subtracted():
    with pytest.raises(ClockDomainMismatch):
        MonotonicInstant('a', 100).elapsed_ns_since(MonotonicInstant('b', 100))


def test_future_reading_and_untyped_subtraction_rejected():
    now = MonotonicInstant('clock', 5)
    with pytest.raises(ValueError):
        now.elapsed_ns_since(MonotonicInstant('clock', 6))
    with pytest.raises(TypeError):
        now.elapsed_ns_since(0)
    with pytest.raises(TypeError):
        _ = now < MonotonicInstant('other', 7)


def test_manual_clock_is_explicit_and_preserves_old_snapshot(manual_clock):
    before = manual_clock.now()
    assert manual_clock.now() is before
    after = manual_clock.advance_ns(10)
    assert before.tick_ns == 0
    assert after.tick_ns == 10
    assert manual_clock.now() == after
    assert after.elapsed_ns_since(before) == 10
    assert manual_clock.advance_ns(0) == after


def test_manual_clock_rejects_rollback_without_mutation(manual_clock):
    manual_clock.advance_ns(5)
    with pytest.raises(ValueError):
        manual_clock.advance_ns(-1)
    assert manual_clock.now().tick_ns == 5


@pytest.mark.parametrize('value', [True, 1.0, float('nan'), float('inf'), None, '10'])
def test_invalid_clock_advances_do_not_mutate(manual_clock, value):
    before = manual_clock.now()
    with pytest.raises(TypeError):
        manual_clock.advance_ns(value)
    assert manual_clock.now() is before


def test_manual_constructor_uses_the_same_value_validation():
    with pytest.raises(ValueError):
        ManualMonotonicClock(clock_id='clock', start_ns=-1)


def test_source_and_protection_clock_are_independent(manual_clock, source_clock):
    source_clock.advance_ns(1_000_000)
    assert manual_clock.now().tick_ns == 0
    manual_clock.advance_ns(5_000)
    assert source_clock.now().tick_ns == 1_000_000
    with pytest.raises(ClockDomainMismatch):
        manual_clock.now().elapsed_ns_since(source_clock.now())


def test_port_exposes_only_an_ordinary_domain_snapshot(manual_clock):
    def sample(clock: MonotonicClock) -> MonotonicInstant:
        return clock.now()

    assert get_type_hints(MonotonicClock.now) == {'return': MonotonicInstant}
    assert type(sample(manual_clock)) is MonotonicInstant


def test_system_clock_has_a_stable_identity_and_non_decreasing_readings():
    clock = SystemMonotonicClock()
    first, second, third = clock.now(), clock.now(), clock.now()
    assert first.clock_id == second.clock_id == third.clock_id
    assert first.tick_ns <= second.tick_ns <= third.tick_ns
    assert third.elapsed_ns_since(first) >= 0
    assert SystemMonotonicClock().now().clock_id != first.clock_id
