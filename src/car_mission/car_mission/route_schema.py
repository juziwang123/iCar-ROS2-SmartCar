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

CHECKIN_FAILURE_POLICIES = frozenset({
    'retry_then_continue',
    'retry_then_wait_operator',
    'alert_and_continue',
    'abort_mission',
})

CHECKIN_METHODS = frozenset({'none', 'geofence', 'visual_marker'})
MARKER_TYPES = frozenset({'qr', 'apriltag'})
INSPECTION_TASK_TYPES = frozenset({'visual_presence'})
REQUIRED_TASK_FAILURE_POLICIES = frozenset({'continue', 'wait_operator', 'abort_mission'})


class RouteValidationError(ValueError):
    """Raised when a route definition is unsafe or structurally invalid."""


@dataclass(frozen=True)
class Pose2D:
    frame_id: str
    x: float
    y: float
    yaw: float


@dataclass(frozen=True)
class CheckinDefinition:
    """The explicit P3 proof required after Nav2 reports arrival."""

    method: str
    marker_type: str
    expected_marker_id: str
    timeout_sec: float
    retries: int
    confirmation_frames: int


@dataclass(frozen=True)
class InspectionTask:
    """A model-agnostic visual task executed after a successful check-in."""

    task_id: str
    task_type: str
    target: str
    required: bool
    capture_count: int
    local_model: str
    use_vlm_fallback: bool
    confidence_threshold: float


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
    max_pose_covariance: float
    checkin: CheckinDefinition
    navigation_failure_policy: str
    checkin_failure_policy: str
    required_task_failure_policy: str
    tasks: Tuple[InspectionTask, ...]


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
                    'max_pose_covariance': checkpoint.max_pose_covariance,
                },
                'checkin': {
                    'method': checkpoint.checkin.method,
                    'marker_type': checkpoint.checkin.marker_type,
                    'expected_marker_id': checkpoint.checkin.expected_marker_id,
                    'timeout_sec': checkpoint.checkin.timeout_sec,
                    'retries': checkpoint.checkin.retries,
                    'confirmation_frames': checkpoint.checkin.confirmation_frames,
                },
                'tasks': [
                    {
                        'task_id': task.task_id,
                        'type': task.task_type,
                        'target': task.target,
                        'required': task.required,
                        'capture_count': task.capture_count,
                        'local_model': task.local_model,
                        'use_vlm_fallback': task.use_vlm_fallback,
                        'confidence_threshold': task.confidence_threshold,
                    }
                    for task in checkpoint.tasks
                ],
                'failure_policy': {
                    'navigation': checkpoint.navigation_failure_policy,
                    'checkin': checkpoint.checkin_failure_policy,
                    'required_task': checkpoint.required_task_failure_policy,
                },
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
    max_pose_covariance = _finite_number(
        arrival.get('max_pose_covariance', 0.25), f'{checkpoint_id}.arrival.max_pose_covariance'
    )
    if (
        position_tolerance <= 0.0 or yaw_tolerance <= 0.0 or dwell_sec < 0.0
        or max_pose_covariance <= 0.0
    ):
        raise RouteValidationError(f'{checkpoint_id}.arrival contains an invalid tolerance or dwell time')

    checkin = _parse_checkin(value.get('checkin'), checkpoint_id)

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
    checkin_policy = _nonempty_string(
        failure_policy.get('checkin', 'alert_and_continue'),
        f'{checkpoint_id}.failure_policy.checkin',
    )
    if checkin_policy not in CHECKIN_FAILURE_POLICIES:
        allowed = ', '.join(sorted(CHECKIN_FAILURE_POLICIES))
        raise RouteValidationError(f'{checkpoint_id}.failure_policy.checkin must be one of: {allowed}')
    required_task_policy = _nonempty_string(
        failure_policy.get('required_task', 'wait_operator'),
        f'{checkpoint_id}.failure_policy.required_task',
    )
    if required_task_policy not in REQUIRED_TASK_FAILURE_POLICIES:
        allowed = ', '.join(sorted(REQUIRED_TASK_FAILURE_POLICIES))
        raise RouteValidationError(
            f'{checkpoint_id}.failure_policy.required_task must be one of: {allowed}'
        )

    raw_tasks = value.get('tasks', [])
    if not isinstance(raw_tasks, list):
        raise RouteValidationError(f'{checkpoint_id}.tasks must be an array of objects')
    tasks = _parse_tasks(raw_tasks, checkpoint_id)

    return Checkpoint(
        checkpoint_id=checkpoint_id,
        sequence=sequence,
        name=name,
        checkpoint_type=checkpoint_type,
        pose=pose,
        position_tolerance_m=position_tolerance,
        yaw_tolerance_rad=yaw_tolerance,
        dwell_sec=dwell_sec,
        max_pose_covariance=max_pose_covariance,
        checkin=checkin,
        navigation_failure_policy=navigation_policy,
        checkin_failure_policy=checkin_policy,
        required_task_failure_policy=required_task_policy,
        tasks=tasks,
    )


def _parse_checkin(value: Any, checkpoint_id: str) -> CheckinDefinition:
    # Routes created before P3 remain executable, but they explicitly receive
    # no physical check-in proof until a checkin configuration is added.
    if value is None:
        return CheckinDefinition('none', '', '', 0.0, 0, 0)
    if not isinstance(value, Mapping):
        raise RouteValidationError(f'{checkpoint_id}.checkin must be an object')
    method = _nonempty_string(value.get('method', 'none'), f'{checkpoint_id}.checkin.method')
    if method not in CHECKIN_METHODS:
        allowed = ', '.join(sorted(CHECKIN_METHODS))
        raise RouteValidationError(f'{checkpoint_id}.checkin.method must be one of: {allowed}')
    if method == 'none':
        return CheckinDefinition('none', '', '', 0.0, 0, 0)

    timeout_sec = _finite_number(
        value.get('timeout_sec', 8.0), f'{checkpoint_id}.checkin.timeout_sec'
    )
    retries = _integer(value.get('retries', 0), f'{checkpoint_id}.checkin.retries', minimum=0)
    confirmation_frames = _integer(
        value.get('confirmation_frames', 2),
        f'{checkpoint_id}.checkin.confirmation_frames',
        minimum=1,
    )
    if timeout_sec <= 0.0:
        raise RouteValidationError(f'{checkpoint_id}.checkin.timeout_sec must be greater than zero')
    if confirmation_frames > 10:
        raise RouteValidationError(f'{checkpoint_id}.checkin.confirmation_frames must be at most 10')
    if method == 'geofence':
        return CheckinDefinition('geofence', '', '', timeout_sec, retries, confirmation_frames)

    marker_type = _nonempty_string(
        value.get('marker_type'), f'{checkpoint_id}.checkin.marker_type'
    ).lower()
    if marker_type not in MARKER_TYPES:
        allowed = ', '.join(sorted(MARKER_TYPES))
        raise RouteValidationError(f'{checkpoint_id}.checkin.marker_type must be one of: {allowed}')
    expected_marker_id = _nonempty_string(
        value.get('expected_marker_id'), f'{checkpoint_id}.checkin.expected_marker_id'
    )
    return CheckinDefinition(
        'visual_marker', marker_type, expected_marker_id, timeout_sec, retries, confirmation_frames
    )


def _parse_tasks(value: List[Any], checkpoint_id: str) -> Tuple[InspectionTask, ...]:
    tasks: List[InspectionTask] = []
    seen_ids = set()
    for index, raw_task in enumerate(value):
        if not isinstance(raw_task, Mapping):
            raise RouteValidationError(f'{checkpoint_id}.tasks[{index}] must be an object')
        task_id = _identifier(raw_task.get('task_id'), f'{checkpoint_id}.tasks[{index}].task_id')
        if task_id in seen_ids:
            raise RouteValidationError(f'{checkpoint_id}.tasks contains duplicate task_id: {task_id}')
        seen_ids.add(task_id)
        task_type = _nonempty_string(
            raw_task.get('type'), f'{checkpoint_id}.{task_id}.type'
        )
        if task_type not in INSPECTION_TASK_TYPES:
            allowed = ', '.join(sorted(INSPECTION_TASK_TYPES))
            raise RouteValidationError(f'{checkpoint_id}.{task_id}.type must be one of: {allowed}')
        target = _nonempty_string(raw_task.get('target'), f'{checkpoint_id}.{task_id}.target')
        required = _boolean(raw_task.get('required', True), f'{checkpoint_id}.{task_id}.required')
        capture_count = _integer(
            raw_task.get('capture_count', 1), f'{checkpoint_id}.{task_id}.capture_count', minimum=1
        )
        if capture_count > 5:
            raise RouteValidationError(f'{checkpoint_id}.{task_id}.capture_count must be at most 5')
        local_model = raw_task.get('local_model', '')
        if not isinstance(local_model, str):
            raise RouteValidationError(f'{checkpoint_id}.{task_id}.local_model must be a string')
        use_vlm_fallback = _boolean(
            raw_task.get('use_vlm_fallback', False),
            f'{checkpoint_id}.{task_id}.use_vlm_fallback',
        )
        confidence_threshold = _finite_number(
            raw_task.get('confidence_threshold', 0.70),
            f'{checkpoint_id}.{task_id}.confidence_threshold',
        )
        if confidence_threshold < 0.0 or confidence_threshold > 1.0:
            raise RouteValidationError(
                f'{checkpoint_id}.{task_id}.confidence_threshold must be between zero and one'
            )
        tasks.append(InspectionTask(
            task_id=task_id,
            task_type=task_type,
            target=target,
            required=required,
            capture_count=capture_count,
            local_model=local_model.strip(),
            use_vlm_fallback=use_vlm_fallback,
            confidence_threshold=confidence_threshold,
        ))
    return tuple(tasks)


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
