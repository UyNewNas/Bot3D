"""Function-scoped clocks; no sleep, device connection or global time patching."""
import pytest

from framework.adapters.clocks import ManualMonotonicClock


@pytest.fixture
def manual_clock():
    return ManualMonotonicClock(clock_id='test/protection')


@pytest.fixture
def source_clock():
    return ManualMonotonicClock(clock_id='test/source')


@pytest.fixture
def authority_case():
    """Build the fixed authority fixture when called inside a test body."""
    from importlib import import_module
    from types import SimpleNamespace

    from framework.domain.capabilities import CapabilityInputs, revise_capabilities
    from framework.domain.discovery import BackendIdentity, BackendKind, MotionState
    from framework.domain.time import MonotonicInstant
    from framework.domain.values import DeviceId, RobotId

    def build(*, clock=None, extra_bindings=False):
        try:
            domain = import_module('framework.domain.control')
            application = import_module('framework.application.control_authority')
        except ModuleNotFoundError as exc:
            if exc.name not in {
                'framework.domain.control', 'framework.application.control_authority',
            }:
                raise
            raise AssertionError(f'missing installed control authority API: {exc.name}') from exc

        robot = RobotId('arm-fixture')
        backend = BackendIdentity(
            DeviceId('mock-device-a'), 'mock-backend-a', BackendKind.SIM, 'fixture-epoch-a',
        )
        binding = domain.ControlBinding(robot, backend, False)
        mirror = domain.ControlBinding(RobotId('arm-fixture-mirror'), backend, True)
        other = domain.ControlBinding(
            RobotId('other-fixture'),
            BackendIdentity(
                DeviceId('mock-device-b'), 'mock-backend-b', BackendKind.SIM, 'fixture-epoch-b',
            ),
            False,
        )
        capabilities = revise_capabilities(
            CapabilityInputs(True, True, True, True, True, 'fixture-config-1', 'automatic'),
        )
        evidence = domain.ActivationEvidence(
            binding, capabilities, domain.Readiness.READY, MotionState.STOPPED,
            MonotonicInstant('control-clock', 0), MonotonicInstant('control-clock', 1000),
            True, True, True, True, True, True,
        )
        if clock is None:
            clock = ManualMonotonicClock(clock_id='control-clock')
        bindings = [binding, mirror, other] if extra_bindings else [binding]
        authority = application.ControlAuthority(bindings, clock, max_lease_ns=100)
        for session_id, robot_ids in [('operator-a', [robot]), ('operator-b', [robot]), ('viewer', [])]:
            authority.register_session(domain.SessionAuthorization(session_id, robot_ids))
        return SimpleNamespace(
            domain=domain, application=application, authority=authority, clock=clock,
            binding=binding, mirror=mirror, other=other, evidence=evidence,
        )

    return build
