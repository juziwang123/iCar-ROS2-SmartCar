"""Pure, persisted-state-friendly patrol mission state machine."""

from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet


class MissionState(str, Enum):
    IDLE = 'IDLE'
    PREPARING = 'PREPARING'
    LOCALIZING = 'LOCALIZING'
    NAVIGATING = 'NAVIGATING'
    ARRIVAL_CONFIRMING = 'ARRIVAL_CONFIRMING'
    CHECKING_IN = 'CHECKING_IN'
    RECORDING = 'RECORDING'
    RECOVERING = 'RECOVERING'
    PAUSING = 'PAUSING'
    PAUSED = 'PAUSED'
    WAITING_OPERATOR = 'WAITING_OPERATOR'
    ESTOPPED = 'ESTOPPED'
    COMPLETED = 'COMPLETED'
    CANCELLED = 'CANCELLED'
    FAILED = 'FAILED'


TERMINAL_STATES = frozenset({
    MissionState.COMPLETED,
    MissionState.CANCELLED,
    MissionState.FAILED,
})


_ACTIVE_STATES = frozenset({
    MissionState.PREPARING,
    MissionState.LOCALIZING,
    MissionState.NAVIGATING,
    MissionState.ARRIVAL_CONFIRMING,
    MissionState.CHECKING_IN,
    MissionState.RECORDING,
    MissionState.RECOVERING,
    MissionState.PAUSING,
    MissionState.PAUSED,
    MissionState.WAITING_OPERATOR,
    MissionState.ESTOPPED,
})


def _with_terminal(*states: MissionState) -> FrozenSet[MissionState]:
    return frozenset(states) | frozenset({MissionState.CANCELLED, MissionState.FAILED})


ALLOWED_TRANSITIONS: Dict[MissionState, FrozenSet[MissionState]] = {
    MissionState.IDLE: frozenset({MissionState.PREPARING}),
    MissionState.PREPARING: _with_terminal(
        MissionState.LOCALIZING, MissionState.PAUSING, MissionState.ESTOPPED,
    ),
    MissionState.LOCALIZING: _with_terminal(
        MissionState.NAVIGATING, MissionState.WAITING_OPERATOR, MissionState.PAUSING,
        MissionState.ESTOPPED,
    ),
    MissionState.NAVIGATING: _with_terminal(
        MissionState.ARRIVAL_CONFIRMING, MissionState.RECOVERING, MissionState.PAUSING,
        MissionState.ESTOPPED, MissionState.WAITING_OPERATOR, MissionState.COMPLETED,
    ),
    MissionState.ARRIVAL_CONFIRMING: _with_terminal(
        MissionState.CHECKING_IN, MissionState.RECORDING, MissionState.PAUSING,
        MissionState.ESTOPPED, MissionState.WAITING_OPERATOR,
    ),
    MissionState.CHECKING_IN: _with_terminal(
        MissionState.RECORDING, MissionState.PAUSING, MissionState.ESTOPPED,
        MissionState.WAITING_OPERATOR,
    ),
    MissionState.RECORDING: _with_terminal(
        MissionState.NAVIGATING, MissionState.COMPLETED, MissionState.PAUSING,
        MissionState.ESTOPPED,
    ),
    MissionState.RECOVERING: _with_terminal(
        MissionState.NAVIGATING, MissionState.WAITING_OPERATOR, MissionState.PAUSING,
        MissionState.ESTOPPED,
    ),
    MissionState.PAUSING: _with_terminal(MissionState.PAUSED, MissionState.ESTOPPED),
    MissionState.PAUSED: _with_terminal(
        MissionState.NAVIGATING, MissionState.LOCALIZING, MissionState.WAITING_OPERATOR,
        MissionState.ESTOPPED,
    ),
    MissionState.WAITING_OPERATOR: _with_terminal(
        MissionState.NAVIGATING, MissionState.LOCALIZING, MissionState.PAUSING,
        MissionState.ESTOPPED,
    ),
    MissionState.ESTOPPED: _with_terminal(
        MissionState.WAITING_OPERATOR, MissionState.NAVIGATING, MissionState.LOCALIZING,
    ),
    MissionState.COMPLETED: frozenset(),
    MissionState.CANCELLED: frozenset(),
    MissionState.FAILED: frozenset(),
}


class InvalidTransition(ValueError):
    """Raised when a mission attempts an unsafe or inconsistent transition."""


class MissionStateMachine:
    """Validate the state transitions performed by the ROS mission node."""

    def __init__(self, initial_state: MissionState = MissionState.IDLE) -> None:
        self._state = initial_state

    @property
    def state(self) -> MissionState:
        return self._state

    @property
    def terminal(self) -> bool:
        return self._state in TERMINAL_STATES

    def can_transition(self, target: MissionState) -> bool:
        return target in ALLOWED_TRANSITIONS[self._state]

    def transition(self, target: MissionState) -> MissionState:
        if not isinstance(target, MissionState):
            target = MissionState(target)
        if not self.can_transition(target):
            raise InvalidTransition(f'{self._state.value} -> {target.value} is not allowed')
        previous = self._state
        self._state = target
        return previous
