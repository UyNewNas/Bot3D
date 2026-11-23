"""T29/revision: snapshots track published capability semantics."""
from dataclasses import FrozenInstanceError, replace
from importlib import import_module
from importlib.util import find_spec

import pytest

pytestmark = pytest.mark.t29_revision


def _capabilities():
    module = 'framework.domain.capabilities'
    assert find_spec(module) is not None, f'API unavailable: {module}'
    return import_module(module)


def _inputs(api):
    return api.CapabilityInputs(True, True, True, True, False, 'fixture-config-1', None)


def test_first_snapshot_preserves_unknown_mode_and_is_immutable():
    api = _capabilities()
    inputs = _inputs(api)
    snapshot = api.revise_capabilities(inputs)
    assert snapshot.revision == 1
    assert snapshot.configuration_revision == 'fixture-config-1'
    assert snapshot.mode is None
    assert snapshot.pose_goal.reasons == (api.UnavailableReason.EXECUTION_UNAVAILABLE,)
    with pytest.raises(FrozenInstanceError):
        snapshot.revision = 2
    with pytest.raises(FrozenInstanceError):
        inputs.execution = True


def test_equivalent_reads_keep_revision():
    api = _capabilities()
    inputs = _inputs(api)
    initial = api.revise_capabilities(inputs)
    assert api.revise_capabilities(inputs, initial) == initial
    assert api.revise_capabilities(replace(inputs), initial) == initial


def test_reason_changes_advance_revision_even_when_still_unavailable():
    api = _capabilities()
    inputs = _inputs(api)
    initial = api.revise_capabilities(inputs)
    changed = api.revise_capabilities(replace(inputs, policy=False), initial)
    restored = api.revise_capabilities(inputs, changed)
    assert [snapshot.revision for snapshot in (initial, changed, restored)] == [1, 2, 3]
    assert all(snapshot.pose_goal.available is False for snapshot in (initial, changed, restored))
    assert changed.pose_goal.reasons == (
        api.UnavailableReason.POLICY_UNAVAILABLE, api.UnavailableReason.EXECUTION_UNAVAILABLE,
    )
    assert initial.pose_goal.reasons == restored.pose_goal.reasons == (
        api.UnavailableReason.EXECUTION_UNAVAILABLE,
    )


@pytest.mark.parametrize('field,value', [
    ('configuration_revision', 'fixture-config-2'),
    ('mode', 'fixture-mode'),
])
def test_context_change_advances_revision_with_same_reasons(field, value):
    api = _capabilities()
    inputs = _inputs(api)
    initial = api.revise_capabilities(inputs)
    changed = api.revise_capabilities(replace(inputs, **{field: value}), initial)
    assert changed.revision == 2
    assert changed.pose_goal == initial.pose_goal
    assert getattr(changed, field) == value
    assert api.revise_capabilities(inputs, changed).revision == 3


@pytest.mark.parametrize('field,value,error', [
    ('revision', True, TypeError),
    ('revision', 1.0, TypeError),
    ('revision', 0, ValueError),
    ('revision', -1, ValueError),
    ('configuration_revision', 1, TypeError),
    ('configuration_revision', 'fixture config', ValueError),
    ('mode', 1, TypeError),
    ('mode', 'fixture mode', ValueError),
    ('pose_goal', object(), TypeError),
])
def test_snapshot_validates_all_fields(field, value, error):
    api = _capabilities()
    snapshot = api.revise_capabilities(_inputs(api))
    with pytest.raises(error):
        replace(snapshot, **{field: value})


def test_revision_requires_a_snapshot_as_previous_value():
    api = _capabilities()
    with pytest.raises(TypeError):
        api.revise_capabilities(_inputs(api), object())


def test_snapshot_requires_concrete_pose_goal_value():
    api = _capabilities()

    class ExtendedGoal(api.PoseGoalCapability):
        pass

    with pytest.raises(TypeError):
        api.CapabilitySnapshot(1, 'fixture-config-1', None, ExtendedGoal(()))


def test_revision_rejects_snapshot_subtypes_as_previous_values():
    api = _capabilities()
    inputs = _inputs(api)

    class ExtendedSnapshot(api.CapabilitySnapshot):
        pass

    previous = ExtendedSnapshot(1, 'fixture-config-1', None, api.compose_pose_goal(inputs))
    with pytest.raises(TypeError):
        api.revise_capabilities(inputs, previous)
