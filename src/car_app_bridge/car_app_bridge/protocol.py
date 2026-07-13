"""Pure helpers for the newline-delimited JSON APP bridge protocol."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


PROTOCOL_VERSION = 3
VALID_MODES = frozenset({'manual', 'nav', 'vision', 'follow'})
TELEMETRY_CHANNELS = frozenset({
    'status', 'lidar', 'vision', 'navigation', 'pose', 'mission', 'inspection', 'event',
    'control_lease', 'runtime',
})


class ProtocolError(ValueError):
    """An invalid request from an APP client."""


def response(
    ok: bool,
    command: str,
    *,
    request_id: Any = None,
    data: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a stable response envelope shared by every JSON command."""
    payload: Dict[str, Any] = {
        'type': 'response',
        'ok': ok,
        'cmd': command,
    }
    if request_id is not None:
        payload['id'] = request_id
    if data is not None:
        payload['data'] = data
    if error is not None:
        payload['error'] = error
    return payload


def event(channel: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Build an asynchronous telemetry message."""
    return {'type': 'event', 'channel': channel, 'data': data}


def finite_number(value: Any, field: str, *, limit: Optional[float] = None) -> float:
    """Return a finite numeric field and enforce an optional absolute limit."""
    if isinstance(value, bool):
        raise ProtocolError(f'{field} must be a number')
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f'{field} must be a number') from exc
    if not math.isfinite(number):
        raise ProtocolError(f'{field} must be finite')
    if limit is not None and abs(number) > limit:
        raise ProtocolError(f'{field} must be between {-limit} and {limit}')
    return number


def boolean(value: Any, field: str = 'value') -> bool:
    """Accept booleans and the common textual forms, never Python truthiness."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'1', 'true', 'on', 'yes'}:
            return True
        if normalized in {'0', 'false', 'off', 'no'}:
            return False
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    raise ProtocolError(f'{field} must be a boolean')


def string_list(value: Any, field: str) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ProtocolError(f'{field} must be an array of strings')
    return value


def object_value(value: Any, field: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError(f'{field} must be an object')
    return value


def nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(f'{field} must be a non-empty string')
    return value.strip()


def nonnegative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProtocolError(f'{field} must be a non-negative integer')
    return value
