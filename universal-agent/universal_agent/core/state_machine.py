"""WatchTask explicit state machine (§14).

Main line:
  DRAFT → ACTIVE → WATCHING → MATCH_FOUND → NOTIFIED → ACTION_PENDING → FULFILLED
Auxiliary: PAUSED / CANCELLED / EXPIRED / FAILED

All transitions are enforced; unknown transitions raise TransitionError.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Set

from .contracts import ALIVE_STATES, WatchState

# Allowed transitions per state.
_TRANSITIONS: Dict[WatchState, Set[WatchState]] = {
    WatchState.DRAFT: {WatchState.ACTIVE, WatchState.CANCELLED, WatchState.EXPIRED},
    WatchState.ACTIVE: {WatchState.WATCHING, WatchState.PAUSED, WatchState.CANCELLED, WatchState.FAILED},
    WatchState.WATCHING: {
        WatchState.MATCH_FOUND,
        WatchState.PAUSED,
        WatchState.CANCELLED,
        WatchState.EXPIRED,
        WatchState.FAILED,
    },
    WatchState.MATCH_FOUND: {
        WatchState.NOTIFIED,
        WatchState.WATCHING,  # material change re-arms watch
        WatchState.PAUSED,
        WatchState.CANCELLED,
    },
    WatchState.NOTIFIED: {
        WatchState.ACTION_PENDING,
        WatchState.WATCHING,
        WatchState.PAUSED,
        WatchState.CANCELLED,
        WatchState.FULFILLED,
    },
    WatchState.ACTION_PENDING: {
        WatchState.FULFILLED,
        WatchState.CANCELLED,
        WatchState.WATCHING,
        WatchState.FAILED,
    },
    WatchState.FULFILLED: set(),  # terminal
    WatchState.PAUSED: {
        WatchState.ACTIVE,
        WatchState.WATCHING,
        WatchState.CANCELLED,
        WatchState.EXPIRED,
    },
    WatchState.CANCELLED: set(),  # terminal
    WatchState.EXPIRED: set(),  # terminal
    WatchState.FAILED: {WatchState.ACTIVE, WatchState.WATCHING},  # retry allowed
}

_TERMINAL: FrozenSet[WatchState] = frozenset(
    {WatchState.FULFILLED, WatchState.CANCELLED, WatchState.EXPIRED}
)


class TransitionError(ValueError):
    def __init__(self, current: WatchState, target: WatchState) -> None:
        super().__init__(f"Illegal transition {current.value} -> {target.value}")
        self.current = current
        self.target = target


def can_transition(current: WatchState, target: WatchState) -> bool:
    return target in _TRANSITIONS.get(current, set())


def transition(current: WatchState, target: WatchState) -> WatchState:
    """Return the target state if legal, else raise TransitionError."""
    if not can_transition(current, target):
        raise TransitionError(current, target)
    return target


def is_terminal(state: WatchState) -> bool:
    return state in _TERMINAL


def alive_states() -> FrozenSet[WatchState]:
    return ALIVE_STATES
