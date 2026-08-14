"""WatchTask state machine tests (§14)."""
from __future__ import annotations

import pytest

from universal_agent.core.contracts import WatchState
from universal_agent.core.state_machine import (
    TransitionError,
    can_transition,
    is_terminal,
    transition,
)


class TestStateMachine:
    def test_main_line_transitions(self):
        assert can_transition(WatchState.DRAFT, WatchState.ACTIVE)
        assert can_transition(WatchState.ACTIVE, WatchState.WATCHING)
        assert can_transition(WatchState.WATCHING, WatchState.MATCH_FOUND)
        assert can_transition(WatchState.MATCH_FOUND, WatchState.NOTIFIED)
        assert can_transition(WatchState.NOTIFIED, WatchState.ACTION_PENDING)
        assert can_transition(WatchState.ACTION_PENDING, WatchState.FULFILLED)

    def test_transition_returns_target(self):
        assert transition(WatchState.DRAFT, WatchState.ACTIVE) == WatchState.ACTIVE

    def test_illegal_transition_raises(self):
        with pytest.raises(TransitionError):
            transition(WatchState.DRAFT, WatchState.FULFILLED)

    def test_terminal_states(self):
        assert is_terminal(WatchState.FULFILLED)
        assert is_terminal(WatchState.CANCELLED)
        assert is_terminal(WatchState.EXPIRED)
        assert not is_terminal(WatchState.WATCHING)

    def test_paused_resume_path(self):
        assert can_transition(WatchState.PAUSED, WatchState.WATCHING)
        assert can_transition(WatchState.PAUSED, WatchState.ACTIVE)

    def test_failed_retry_allowed(self):
        assert can_transition(WatchState.FAILED, WatchState.ACTIVE)
        assert can_transition(WatchState.FAILED, WatchState.WATCHING)

    def test_no_self_loop_on_terminal(self):
        assert not can_transition(WatchState.CANCELLED, WatchState.ACTIVE)

    def test_full_cycle(self):
        state = WatchState.DRAFT
        for target in (WatchState.ACTIVE, WatchState.WATCHING, WatchState.MATCH_FOUND,
                       WatchState.NOTIFIED, WatchState.ACTION_PENDING, WatchState.FULFILLED):
            state = transition(state, target)
        assert state == WatchState.FULFILLED
        assert is_terminal(state)
