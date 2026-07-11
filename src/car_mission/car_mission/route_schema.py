"""Route schema parsing and validation with no ROS runtime dependency."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple


NAVIGATION_FAILURE_POLICIES = frozenset({
    'retry_then_continue',
    'retry_then_skip',
    'retry_then_wait_operator',
    'abort_mission',
})


class RouteValidationError(ValueError):
    """Raised when a route definition is unsafe or structurally invalid."""


@dataclass(frozen=True)
class Pose2D:
    frame_id: str
    x: float
    y: float
    yaw: float


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    sequence: int
    name: str
    checkpoint_type: str
    pose: Pose2D
    position_tolerance_m: float
    yaw_tolerance_rad: float
    dwell_sec: float
    navigation_failure_policy: str
    tasks: Tuple[Dict[str, Any], ...]


@dataclass(frozen=True)
class RouteDefinition:
    schema_version: int
    route_id: str
    map_id: str
    name: str
    version: int
    loop: bool
    checkpoints: Tuple[Checkpoint, ...]


def parse_route(value: Mapping[str, Any]) -> RouteDefinition:
    """Validate a route mapping and return its normalized immutable form."""
    if not isinstance(value, Mapping):
        raise RouteValidationError('route must be an object')

    schema_version = _integer(value.get('schema_version', 1), 'schema_version', minimum=1)
    if schema_version != 1:
        raise RouteValidationError(f'unsupported schema_version: {schema_version}')

    route_id = _identifier(value.get('route_id'), 'route_id')
    map_id = _identifier(value.get('map_id'), 'map_id')
    name = _nonempty_string(value.get('name', route_id), 'name')
    version = _integer(value.get('version', 1), 'version', minimum=1)
    loop = _boolean(value.get('loop', False), 'loop')

    raw_checkpoints = value.get('checkpoints')
    if not isinstance(raw_checkpoints, list) or not raw_checkpoints:
        raise RouteValidationError('checkpoints must be a non-empty array')

    checkpoints: List[Checkpoint] = []
    known_ids = set()
    for index, raw_checkpoint in enumerate(raw_checkpoints, start=1):
        checkpoint = _parse_checkpoint(raw_checkpoint, index)
        if checkpoint.checkpoint_id in known_ids:
            raise RouteValidationError(f'duplicate checkpoint_id: {checkpoint.checkpoint_id}')
        known_ids.add(checkpoint.checkpoint_id)
        checkpoints.append(checkpoint)

    return RouteDefinition(
        schema_version=schema_version,
        route_id=route_id,
        map_id=map_id,
        name=name,
        version=version,
        loop=loop,
        checkpoints=tuple(checkpoints),
    )


def route_to_mapping(route: RouteDefinition) -> Dict[str, Any]:
    """Convert a validated route back to a deterministic JSON/YAML mapping."""
    return {
        'schema_version': route.schema_version,
        'route_id': route.route_id,
        'map_id': route.map_id,
        'name': route.name,
        'version': route.version,
        'loop': route.loop,
        'checkpoints': [
            {
                'checkpoint_id': checkpoint.checkpoint_id,
                'sequence': checkpoint.sequence,
                'name': checkpoint.name,
                'type': checkpoint.checkpoint_type,
                'pose': {
                    'frame_id': checkpoint.pose.frame_id,
                    'x': checkpoint.pose.x,
                    'y': checkpoint.pose.y,
                    'yaw': checkpoint.pose.yaw,
                },
                'arrival': {
                    'position_tolerance_m': checkpoint.position_tolerance_m,
                    'yaw_tolerance_rad': checkpoint.yaw_tolerance_rad,
                    'dwell_sec': checkpoint.dwell_sec,
                },
                'tasks': list(checkpoint.tasks),
                'failure_policy': {'navigation': checkpoint.navigation_failure_policy},
            }
            for checkpoint in route.checkpoints
        ],
    }


def _parse_checkpoint(value: Any, expected_sequence: int) -> Checkpoint:
    if not isinstance(value, Mapping):
        raise RouteValidationError(f'checkpoints[{expected_sequence - 1}] must be an object')

    checkpoint_id = _identifier(value.get('checkpoint_id'), f'checkpoints[{expected_sequence - 1}].checkpoint_id')
    sequence = _integer(value.get('sequence', expected_sequence), f'{checkpoint_id}.sequence', minimum=1)
    if sequence != expected_sequence:
        raise RouteValidationError(
            f'{checkpoint_id}.sequence must be {expected_sequence}; checkpoints must be ordered continuously'
        )
    name = _nonempty_string(value.get('name', checkpoint_id), f'{checkpoint_id}.name')
    checkpoint_type = _nonempty_string(value.get('type', 'transit'), f'{checkpoint_id}.type')

    raw_pose = value.get('pose')
    if not isinstance(raw_pose, Mapping):
        raise RouteValidationError(f'{checkpoint_id}.pose must be an object')
    pose = Pose2D(
        frame_id=_nonempty_string(raw_pose.get('frame_id', 'map'), f'{checkpoint_id}.pose.frame_id'),
        x=_finite_number(raw_pose.get('x'), f'{checkpoint_id}.pose.x'),
        y=_finite_number(raw_pose.get('y'), f'{checkpoint_id}.pose.y'),
        yaw=_finite_number(raw_pose.get('yaw', 0.0), f'{checkpoint_id}.pose.yaw'),
    )
    if pose.frame_id != 'map':
        raise RouteValidationError(f'{checkpoint_id}.pose.frame_id must be map')

    arrival = value.get('arrival', {})
    if not isinstance(arrival, Mapping):
        raise RouteValidationError(f'{checkpoint_id}.arrival must be an object')
    position_tolerance = _finite_number(
        arrival.get('position_tolerance_m', 0.30), f'{checkpoint_id}.arrival.position_tolerance_m'
    )
    yaw_tolerance = _finite_number(
        arrival.get('yaw_tolerance_rad', 0.35), f'{checkpoint_id}.arrival.yaw_tolerance_rad'
    )
    dwell_sec = _finite_number(arrival.get('dwell_sec', 0.0), f'{checkpoint_id}.arrival.dwell_sec')
    if position_tolerance <= 0.0 or yaw_tolerance <= 0.0 or dwell_sec < 0.0:
        raise RouteValidationError(f'{checkpoint_id}.arrival contains an invalid tolerance or dwell time')

    failure_policy = value.get('failure_policy', {})
    if not isinstance(failure_policy, Mapping):
        raise RouteValidationError(f'{checkpoint_id}.failure_policy must be an object')
    navigation_policy = _nonempty_string(
        failure_policy.get('navigation', 'retry_then_wait_operator'),
        f'{checkpoint_id}.failure_policy.navigation',
    )
    if navigation_policy not in NAVIGATION_FAILURE_POLICIES:
        allowed = ', '.join(sorted(NAVIGATION_FAILURE_POLICIES))
        raise RouteValidationError(f'{checkpoint_id}.failure_policy.navigation must be one of: {allowed}')

    raw_tasks = value.get('tasks', [])
    if not isinstance(raw_tasks, list) or not all(isinstance(task, Mapping) for task in raw_tasks):
        raise RouteValidationError(f'{checkpoint_id}.tasks must be an array of objects')

    return Checkpoint(
        checkpoint_id=checkpoint_id,
        sequence=sequence,
        name=name,
        checkpoint_type=checkpoint_type,
        pose=pose,
        position_tolerance_m=position_tolerance,
        yaw_tolerance_rad=yaw_tolerance,
        dwell_sec=dwell_sec,
        navigation_failure_policy=navigation_policy,
        tasks=tuple(dict(task) for task in raw_tasks),
    )


def _identifier(value: Any, field: str) -> str:
    result = _nonempty_string(value, field)
    if any(character.isspace() for character in result):
        raise RouteValidationError(f'{field} must not contain whitespace')
    return result


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RouteValidationError(f'{field} must be a non-empty string')
    return value.strip()


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise RouteValidationError(f'{field} must be a boolean')
    return value


def _integer(value: Any, field: str, *, minimum: Optional[int] = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RouteValidationError(f'{field} must be an integer')
    if minimum is not None and value < minimum:
        raise RouteValidationError(f'{field} must be at least {minimum}')
    return value


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise RouteValidationError(f'{field} must be a finite number')
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise RouteValidationError(f'{field} must be a finite number') from exc
    if not math.isfinite(result):
        raise RouteValidationError(f'{field} must be a finite number')
    return result
