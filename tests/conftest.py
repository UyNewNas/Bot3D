"""Function-scoped clocks; no sleep, device connection or global time patching."""
import pytest

from framework.adapters.clocks import ManualMonotonicClock


@pytest.fixture
def manual_clock():
    return ManualMonotonicClock(clock_id='test/protection')


@pytest.fixture
def source_clock():
    return ManualMonotonicClock(clock_id='test/source')
