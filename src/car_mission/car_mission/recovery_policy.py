"""Pure P5 recovery decisions, shared by ROS callbacks and unit tests."""

from __future__ import annotations

from enum import Enum


class RecoveryDecision(str, Enum):
    WAIT = 'WAIT'
    RETRY = 'RETRY'
    WAIT_OPERATOR = 'WAIT_OPERATOR'


def blocked_recovery(*, blocked_for_sec: float, retry_count: int, timeout_sec: float, max_retries: int) -> RecoveryDecision:
    """Decide a bounded obstacle recovery without permitting arbitrary motion."""
    if blocked_for_sec < max(0.0, timeout_sec):
        return RecoveryDecision.WAIT
    if retry_count < max(0, max_retries):
        return RecoveryDecision.RETRY
    return RecoveryDecision.WAIT_OPERATOR


def person_clear_ready(*, clear_for_sec: float, required_clear_sec: float) -> bool:
    """Require a continuous clear interval before releasing a person safety stop."""
    return clear_for_sec >= max(0.0, required_clear_sec)
