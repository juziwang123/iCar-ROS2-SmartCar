"""Validation and encoding for the marker detector's JSON topic."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence, Tuple


class MarkerProtocolError(ValueError):
    """A marker detector payload is malformed."""


@dataclass(frozen=True)
class MarkerDetection:
    marker_type: str
    marker_id: str
    polygon: Tuple[Tuple[float, float], ...]


def encode_markers(
    markers: Iterable[MarkerDetection],
    *,
    stamp_sec: int,
    stamp_nanosec: int,
    frame_id: str,
) -> str:
    return json.dumps({
        'stamp': {'sec': int(stamp_sec), 'nanosec': int(stamp_nanosec)},
        'frame_id': str(frame_id),
        'markers': [
            {
                'type': marker.marker_type,
                'id': marker.marker_id,
                'polygon': [[x, y] for x, y in marker.polygon],
            }
            for marker in markers
        ],
    }, ensure_ascii=False, separators=(',', ':'))


def parse_markers(payload: str) -> Tuple[MarkerDetection, ...]:
    return parse_marker_frame(payload)[0]


def parse_marker_frame(payload: str) -> Tuple[Tuple[MarkerDetection, ...], Tuple[int, int]]:
    try:
        value = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise MarkerProtocolError('marker payload must be JSON') from exc
    if not isinstance(value, dict) or not isinstance(value.get('markers'), list):
        raise MarkerProtocolError('marker payload must contain a markers array')
    stamp = value.get('stamp')
    if not isinstance(stamp, dict):
        raise MarkerProtocolError('marker payload must contain a stamp object')
    stamp_sec = _stamp_part(stamp.get('sec'), 'stamp.sec')
    stamp_nanosec = _stamp_part(stamp.get('nanosec'), 'stamp.nanosec')
    if stamp_nanosec >= 1000000000:
        raise MarkerProtocolError('stamp.nanosec must be below 1000000000')
    parsed: List[MarkerDetection] = []
    for index, raw in enumerate(value['markers']):
        if not isinstance(raw, dict):
            raise MarkerProtocolError(f'markers[{index}] must be an object')
        marker_type = _text(raw.get('type'), f'markers[{index}].type')
        marker_id = _text(raw.get('id'), f'markers[{index}].id')
        polygon_value = raw.get('polygon', [])
        if not isinstance(polygon_value, list):
            raise MarkerProtocolError(f'markers[{index}].polygon must be an array')
        polygon = tuple(_point(point, f'markers[{index}].polygon') for point in polygon_value)
        parsed.append(MarkerDetection(marker_type, marker_id, polygon))
    return tuple(parsed), (stamp_sec, stamp_nanosec)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarkerProtocolError(f'{field} must be a non-empty string')
    return value.strip()


def _point(value: Any, field: str) -> Tuple[float, float]:
    if not isinstance(value, Sequence) or len(value) != 2:
        raise MarkerProtocolError(f'{field} entries must be [x, y] pairs')
    try:
        x, y = float(value[0]), float(value[1])
    except (TypeError, ValueError) as exc:
        raise MarkerProtocolError(f'{field} coordinates must be numbers') from exc
    if not math.isfinite(x) or not math.isfinite(y):
        raise MarkerProtocolError(f'{field} coordinates must be finite')
    return x, y


def _stamp_part(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MarkerProtocolError(f'{field} must be a non-negative integer')
    return value
