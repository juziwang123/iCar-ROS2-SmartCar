"""ROS-independent validation for the iCar operator CLI."""

from __future__ import annotations

import shlex
import math
from dataclasses import dataclass
from typing import Dict, Tuple


class CliError(ValueError):
    """Raised for invalid local CLI input before any ROS command is sent."""


@dataclass(frozen=True)
class LaunchProfile:
    name: str
    arguments: Dict[str, str]


VALID_MODES = frozenset({'manual', 'nav', 'vision', 'follow'})


def build_launch_profile(
    name: str, *, map_file: str = '', route_file: str = '', use_app_bridge: bool = False,
    use_yolo: bool = False, use_rviz: bool = False,
) -> LaunchProfile:
    """Build only whitelisted launch arguments; never construct a shell string."""
    normalized = name.strip().lower()
    profiles = {
        'mapping': {'use_mapping': 'true'},
        'navigation': {'use_navigation': 'true'},
        'mission': {
            'use_navigation': 'true', 'use_mission': 'true', 'use_inspection': 'true',
            'mission_require_localization': 'true',
        },
    }
    if normalized not in profiles:
        raise CliError('profile must be mapping, navigation, or mission')
    arguments = dict(profiles[normalized])
    if map_file:
        arguments['map'] = map_file
    if route_file:
        if normalized != 'mission':
            raise CliError('--route is only valid for the mission profile')
        arguments['mission_route_file'] = route_file
    arguments['use_app_bridge'] = 'true' if use_app_bridge else 'false'
    arguments['use_yolo'] = 'true' if use_yolo else 'false'
    arguments['navigation_use_rviz'] = 'true' if use_rviz else 'false'
    return LaunchProfile(normalized, arguments)


def parse_console_command(line: str) -> Tuple[str, Tuple[str, ...]]:
    """Parse a console line without allowing it to become a shell command."""
    try:
        tokens = tuple(shlex.split(line))
    except ValueError as exc:
        raise CliError(f'cannot parse command: {exc}') from exc
    if not tokens:
        return '', ()
    command = tokens[0].lower()
    allowed = {
        'help', 'status', 'start', 'pause', 'resume', 'cancel', 'estop', 'report',
        'recoveries', 'mode', 'move', 'stop', 'nav', 'nav_cancel', 'quit', 'exit',
    }
    if command not in allowed:
        raise CliError(f'unknown command: {command}')
    return command, tokens[1:]


def validate_mode(value: str) -> str:
    mode = value.strip().lower()
    if mode not in VALID_MODES:
        raise CliError('mode must be manual, nav, vision, or follow')
    return mode


def finite_motion(value: str, field: str, limit: float) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise CliError(f'{field} must be a number') from exc
    if not math.isfinite(number) or abs(number) > limit:
        raise CliError(f'{field} must be finite and within ±{limit}')
    return number
