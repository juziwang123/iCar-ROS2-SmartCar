"""ROS-independent checks used by the checkpoint verification action."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class PoseSnapshot:
    x: float
    y: float
    yaw: float
    covariance_x: float
    covariance_y: float
    covariance_yaw: float
    received_at: float


@dataclass(frozen=True)
class MotionSnapshot:
    linear_x: float
    angular_z: float
    received_at: float


@dataclass(frozen=True)
class GeofencePolicy:
    target_x: float
    target_y: float
    target_yaw: float
    position_tolerance_m: float
    yaw_tolerance_rad: float
    max_pose_covariance: float
    max_linear_speed_mps: float
    max_angular_speed_rps: float
    pose_max_age_sec: float
    motion_max_age_sec: float


@dataclass(frozen=True)
class GeofenceVerdict:
    passed: bool
    distance_m: float
    yaw_error_rad: float
    reasons: Tuple[str, ...]


def normalize_angle(angle: float) -> float:
    """Normalize an angle to [-pi, pi]."""
    return math.atan2(math.sin(angle), math.cos(angle))


def evaluate_geofence(
    policy: GeofencePolicy,
    pose: Optional[PoseSnapshot],
    motion: Optional[MotionSnapshot],
    now: float,
) -> GeofenceVerdict:
    """Require a fresh, still, localized robot inside the target fence."""
    reasons = []
    if pose is None:
        return GeofenceVerdict(False, math.inf, math.inf, ('POSE_UNAVAILABLE',))
    distance = math.hypot(pose.x - policy.target_x, pose.y - policy.target_y)
    yaw_error = abs(normalize_angle(pose.yaw - policy.target_yaw))
    if now - pose.received_at > policy.pose_max_age_sec:
        reasons.append('POSE_STALE')
    if distance > policy.position_tolerance_m:
        reasons.append('POSITION_OUTSIDE_FENCE')
    if yaw_error > policy.yaw_tolerance_rad:
        reasons.append('YAW_OUTSIDE_FENCE')
    if max(pose.covariance_x, pose.covariance_y, pose.covariance_yaw) > policy.max_pose_covariance:
        reasons.append('POSE_COVARIANCE_HIGH')
    if motion is None or now - motion.received_at > policy.motion_max_age_sec:
        reasons.append('MOTION_STALE')
    elif (
        abs(motion.linear_x) > policy.max_linear_speed_mps
        or abs(motion.angular_z) > policy.max_angular_speed_rps
    ):
        reasons.append('ROBOT_NOT_STILL')
    return GeofenceVerdict(not reasons, distance, yaw_error, tuple(reasons))


class MarkerConfirmationTracker:
    """Counts unique consecutive detector frames for one expected marker."""

    def __init__(self, expected_type: str, expected_id: str, required_frames: int) -> None:
        if required_frames <= 0:
            raise ValueError('required_frames must be positive')
        self.expected_type = expected_type
        self.expected_id = expected_id
        self.required_frames = required_frames
        self.count = 0
        self._last_frame_key = None

    @property
    def confirmed(self) -> bool:
        return self.count >= self.required_frames

    def observe(self, marker_type: str, marker_id: str, frame_key: object) -> bool:
        if frame_key == self._last_frame_key:
            return self.confirmed
        self._last_frame_key = frame_key
        if marker_type == self.expected_type and marker_id == self.expected_id:
            self.count += 1
        else:
            self.count = 0
        return self.confirmed
