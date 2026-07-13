"""ROS-independent runtime-profile validation and launch argument building."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict


RUNTIME_PROFILES = frozenset({'idle', 'mapping', 'navigation', 'mission'})
ACTIVE_PROFILES = frozenset({'mapping', 'navigation', 'mission'})
TRANSITION_STATES = frozenset({'IDLE', 'STARTING', 'READY', 'STOPPING', 'FAILED'})


class RuntimeProfileError(ValueError):
    """Raised before a runtime request can start any process."""


@dataclass(frozen=True)
class RuntimeProfileRequest:
    profile: str
    map_path: str = ''
    route_file: str = ''
    use_yolo: bool = False

    def normalized(self) -> 'RuntimeProfileRequest':
        profile = self.profile.strip().lower()
        if profile not in RUNTIME_PROFILES:
            raise RuntimeProfileError(
                'profile must be one of: idle, mapping, navigation, mission'
            )
        if not isinstance(self.use_yolo, bool):
            raise RuntimeProfileError('use_yolo must be a boolean')
        map_path = _absolute_path(self.map_path, 'map_path') if self.map_path else ''
        route_file = _absolute_path(self.route_file, 'route_file') if self.route_file else ''
        if profile in {'navigation', 'mission'} and not map_path:
            raise RuntimeProfileError(f'{profile} requires an absolute map_path')
        if profile not in {'navigation', 'mission'} and map_path:
            raise RuntimeProfileError('map_path is only valid for navigation or mission')
        if profile == 'mission' and not route_file:
            raise RuntimeProfileError('mission requires an absolute route_file')
        if profile != 'mission' and route_file:
            raise RuntimeProfileError('route_file is only valid for the mission profile')
        if profile != 'mission' and self.use_yolo:
            raise RuntimeProfileError('use_yolo is only valid for the mission profile')
        return RuntimeProfileRequest(profile, map_path, route_file, self.use_yolo)


def profile_launch_arguments(request: RuntimeProfileRequest) -> Dict[str, str]:
    """Return only whitelisted ``ros2 launch`` arguments for a profile."""
    request = request.normalized()
    if request.profile == 'idle':
        return {}
    arguments = {
        'profile': request.profile,
        'use_yolo': 'true' if request.use_yolo else 'false',
    }
    if request.map_path:
        arguments['map'] = request.map_path
    if request.route_file:
        arguments['mission_route_file'] = request.route_file
    return arguments


def validate_runtime_files(request: RuntimeProfileRequest) -> RuntimeProfileRequest:
    """Ensure files exist after normalization and before any child is started."""
    request = request.normalized()
    for value, field in ((request.map_path, 'map_path'), (request.route_file, 'route_file')):
        if value and not Path(value).is_file():
            raise RuntimeProfileError(f'{field} does not exist or is not a file: {value}')
    return request


def _absolute_path(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeProfileError(f'{field} must be a non-empty absolute path')
    if '\x00' in value:
        raise RuntimeProfileError(f'{field} must not contain NUL')
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise RuntimeProfileError(f'{field} must be an absolute path')
    return str(path.resolve())
