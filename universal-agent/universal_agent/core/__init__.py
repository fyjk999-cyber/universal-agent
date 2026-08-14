"""Universal Agent Core — deterministic, host-agnostic logic core.

Core never imports hosts/, never imports Harness. It only depends on
contracts, events, and its own coordination modules.
"""
from __future__ import annotations

from .contracts import *  # noqa: F401,F403
from .state_machine import TransitionError, can_transition, transition  # noqa: F401
