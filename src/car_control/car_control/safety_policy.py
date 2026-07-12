"""Pure safety rules shared by control nodes and unit tests.

This module deliberately has no ROS dependencies so that the safety contract
can be tested on a development machine without a ROS installation.
"""

from __future__ import annotations

from typing import Any


VALID_MODES = frozenset({'manual', 'nav', 'vision', 'follow'})


def normalize_mode(value: Any) -> str:
    """Return a normalized mode string, or an empty string for non-strings."""
    return value.strip().lower() if isinstance(value, str) else ''


def is_supported_mode(value: Any) -> bool:
    """Whether *value* is a mode that the mux knows how to select."""
    return normalize_mode(value) in VALID_MODES


def effective_estop(*, operator_latched: bool, person_active: bool, sensor_fault: bool = False) -> bool:
    """Return whether motion must be stopped immediately.

    Operator emergency-stop is latched by ``SafetyMux`` until a separate,
    explicit false command is received. Person stop is intentionally dynamic:
    it remains active only while the perception node reports a nearby person.
    """
    return bool(operator_latched or person_active or sensor_fault)
