"""Single-owner in-memory discovery of read-only robot bindings."""
from __future__ import annotations

from dataclasses import dataclass, replace

from framework.domain.capabilities import CapabilitySnapshot, revise_capabilities
from framework.domain.discovery import (
    BackendDescription, BackendIdentity, BackendState, ReadOnlyBinding, RobotDescription, RobotState,
    _validate_robot_id,
)
from framework.domain.values import RobotId

from .ports import ReadOnlyBackend

__all__ = ['DuplicateRobot', 'BindingMismatch', 'UnknownRobot', 'RobotRegistry']


class DuplicateRobot(ValueError):
    """A logical robot ID is already registered."""


class BindingMismatch(ValueError):
    """A backend read returned a different identity than the registered binding."""


class UnknownRobot(KeyError):
    """No binding exists for the logical robot ID."""


@dataclass(slots=True)
class _Entry:
    backend: ReadOnlyBackend
    binding: ReadOnlyBinding
    capabilities: CapabilitySnapshot


def _read_description(backend: ReadOnlyBackend) -> BackendDescription:
    description = backend.describe()
    if type(description) is not BackendDescription:
        raise TypeError('backend describe() must return a BackendDescription')
    return description


def _check_identity(binding: ReadOnlyBinding, identity: BackendIdentity) -> None:
    if identity != binding.backend:
        raise BindingMismatch(f'backend identity changed for {binding.robot_id.value!r}')


def _effective_description(
    binding: ReadOnlyBinding,
    description: BackendDescription,
    previous: CapabilitySnapshot | None = None,
) -> RobotDescription:
    inputs = replace(description.capability_inputs, execution=False)
    return RobotDescription(binding, description.name, revise_capabilities(inputs, previous))


class RobotRegistry:
    """Synchronously read and track the published revision of each logical binding."""

    def __init__(self) -> None:
        self._entries: dict[RobotId, _Entry] = {}

    def register(self, robot_id: RobotId, backend: ReadOnlyBackend) -> RobotDescription:
        _validate_robot_id(robot_id)
        if robot_id in self._entries:
            raise DuplicateRobot(f'robot {robot_id.value!r} is already registered')
        if not callable(getattr(backend, 'describe', None)) or not callable(getattr(backend, 'read_state', None)):
            raise TypeError('backend must provide callable describe() and read_state() methods')
        description = _read_description(backend)
        binding = ReadOnlyBinding(robot_id, description.identity)
        published = _effective_description(binding, description)
        self._entries[robot_id] = _Entry(backend, binding, published.capabilities)
        return published

    def describe(self, robot_id: RobotId) -> RobotDescription:
        entry = self._lookup(robot_id)
        description = self._current_description(entry)
        entry.capabilities = description.capabilities
        return description

    def discover(self) -> tuple[RobotDescription, ...]:
        """Publish the sorted descriptions after every binding has been read successfully."""
        entries = sorted(self._entries.values(), key=lambda entry: entry.binding.robot_id.value)
        descriptions = tuple(self._current_description(entry) for entry in entries)
        for entry, description in zip(entries, descriptions, strict=True):
            entry.capabilities = description.capabilities
        return descriptions

    def read_state(self, robot_id: RobotId) -> RobotState:
        entry = self._lookup(robot_id)
        description = self._current_description(entry)
        state = entry.backend.read_state()
        if type(state) is not BackendState:
            raise TypeError('backend read_state() must return a BackendState')
        _check_identity(entry.binding, state.identity)
        published = RobotState(entry.binding, state.observation, description.capabilities.revision)
        entry.capabilities = description.capabilities
        return published

    def _lookup(self, robot_id: RobotId) -> _Entry:
        _validate_robot_id(robot_id)
        entry = self._entries.get(robot_id)
        if entry is None:
            raise UnknownRobot(robot_id.value)
        return entry

    def _current_description(self, entry: _Entry) -> RobotDescription:
        description = _read_description(entry.backend)
        _check_identity(entry.binding, description.identity)
        return _effective_description(entry.binding, description, entry.capabilities)
