"""T29/compose: effective pose goals require every declared prerequisite."""
from dataclasses import FrozenInstanceError, replace
from importlib import import_module
from importlib.util import find_spec

import pytest

pytestmark = pytest.mark.t29_compose

PREREQUISITES = [
    ('planning', 'planning_unavailable'),
    ('model', 'model_unavailable'),
    ('frames', 'frames_unavailable'),
    ('policy', 'policy_unavailable'),
    ('execution', 'execution_unavailable'),
]


def _capabilities():
    module = 'framework.domain.capabilities'
    assert find_spec(module) is not None, f'API unavailable: {module}'
    return import_module(module)


def test_all_prerequisites_make_pose_goal_available():
    api = _capabilities()
    inputs = api.CapabilityInputs(True, True, True, True, True, 'fixture-config-1', None)
    result = api.compose_pose_goal(inputs)
    assert result.available is True
    assert result.reasons == ()
    assert result.capability_id == 'manipulation.pose_goal'
    assert result.version == '1.0'


@pytest.mark.parametrize('field,reason', PREREQUISITES)
def test_each_missing_prerequisite_disables_pose_goal(field, reason):
    api = _capabilities()
    inputs = api.CapabilityInputs(True, True, True, True, True, 'fixture-config-1', None)
    result = api.compose_pose_goal(replace(inputs, **{field: False}))
    assert result.available is False
    assert result.reasons == (api.UnavailableReason(reason),)
    assert result.reasons[0].value == reason


def test_all_missing_reasons_are_reported_in_fixed_order():
    api = _capabilities()
    inputs = api.CapabilityInputs(False, False, False, False, False, 'fixture-config-1', None)
    result = api.compose_pose_goal(inputs)
    assert result.available is False
    assert tuple(reason.value for reason in result.reasons) == (
        'planning_unavailable',
        'model_unavailable',
        'frames_unavailable',
        'policy_unavailable',
        'execution_unavailable',
    )


@pytest.mark.parametrize('field', [field for field, _ in PREREQUISITES])
@pytest.mark.parametrize('value', [1, 0.0, 'true'])
def test_prerequisites_reject_boolean_coercion(field, value):
    api = _capabilities()
    inputs = api.CapabilityInputs(True, True, True, True, True, 'fixture-config-1', None)
    with pytest.raises(TypeError):
        replace(inputs, **{field: value})


@pytest.mark.parametrize('field,value,error', [
    ('configuration_revision', None, TypeError),
    ('configuration_revision', '', ValueError),
    ('configuration_revision', 'fixture config', ValueError),
    ('mode', False, TypeError),
    ('mode', '', ValueError),
    ('mode', 'mode\ttwo', ValueError),
])
def test_configuration_and_mode_require_valid_tokens(field, value, error):
    api = _capabilities()
    inputs = api.CapabilityInputs(True, True, True, True, True, 'fixture-config-1', None)
    with pytest.raises(error):
        replace(inputs, **{field: value})


def test_direct_capability_copies_and_normalizes_reasons():
    api = _capabilities()
    execution = api.UnavailableReason.EXECUTION_UNAVAILABLE
    planning = api.UnavailableReason.PLANNING_UNAVAILABLE
    reasons = [execution, planning]
    result = api.PoseGoalCapability(reasons)
    reasons.clear()
    assert result.reasons == (planning, execution)
    assert result.available is False
    with pytest.raises(FrozenInstanceError):
        result.reasons = ()
    with pytest.raises(TypeError):
        api.PoseGoalCapability([], available=False)


def test_reasons_must_be_unique_enum_members_in_a_list_or_tuple():
    api = _capabilities()
    reason = api.UnavailableReason.EXECUTION_UNAVAILABLE
    with pytest.raises(ValueError):
        api.PoseGoalCapability([reason, reason])
    with pytest.raises(TypeError):
        api.PoseGoalCapability([reason.value])
    with pytest.raises(TypeError):
        api.PoseGoalCapability({reason})


def test_composition_requires_capability_inputs():
    api = _capabilities()
    with pytest.raises(TypeError):
        api.compose_pose_goal(object())


def test_composition_rejects_capability_input_subtypes():
    api = _capabilities()

    class ExtendedInputs(api.CapabilityInputs):
        pass

    inputs = ExtendedInputs(True, True, True, True, True, 'fixture-config-1', None)
    with pytest.raises(TypeError):
        api.compose_pose_goal(inputs)


@pytest.mark.parametrize('field,value', [
    ('configuration_revision', 'fixture-config-1'),
    ('mode', 'fixture-mode'),
])
def test_capability_context_rejects_string_subtypes(field, value):
    api = _capabilities()
    inputs = api.CapabilityInputs(True, True, True, True, True, 'fixture-config-1', None)

    class ExtendedText(str):
        pass

    with pytest.raises(TypeError):
        replace(inputs, **{field: ExtendedText(value)})


def test_pose_goal_rejects_reason_container_subtypes():
    api = _capabilities()

    class ExtendedReasons(list):
        pass

    with pytest.raises(TypeError):
        api.PoseGoalCapability(ExtendedReasons())
