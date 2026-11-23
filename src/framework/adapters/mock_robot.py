"""A static, read-only simulation fixture."""
from __future__ import annotations

from dataclasses import dataclass, replace

from framework.domain.discovery import BackendDescription, BackendKind, BackendState

__all__ = ['ReadOnlyMockBackend']


@dataclass(frozen=True, slots=True)
class ReadOnlyMockBackend:
    description: BackendDescription
    state: BackendState

    def __post_init__(self) -> None:
        if type(self.description) is not BackendDescription:
            raise TypeError('description must be a BackendDescription')
        if type(self.state) is not BackendState:
            raise TypeError('state must be a BackendState')
        if self.description.identity != self.state.identity:
            raise ValueError('mock description and state must have the same backend identity')
        if self.description.identity.backend_kind is not BackendKind.SIM:
            raise ValueError('mock backend kind must be SIM')
        inputs = replace(self.description.capability_inputs, execution=False)
        description = replace(self.description, capability_inputs=inputs)
        object.__setattr__(self, 'description', description)

    def describe(self) -> BackendDescription:
        return self.description

    def read_state(self) -> BackendState:
        return self.state
