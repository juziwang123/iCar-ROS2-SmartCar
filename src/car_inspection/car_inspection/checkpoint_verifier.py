"""Action server that combines a localization fence with marker proof."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Any, Dict, Optional, Sequence, Tuple

import rclpy
from car_interfaces.action import VerifyCheckpoint
from geometry_msgs.msg import PoseWithCovarianceStamped, Twist
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from rclpy.task import Future
from sensor_msgs.msg import Image
from std_msgs.msg import String

from .checkin_logic import (
    GeofencePolicy,
    MarkerConfirmationTracker,
    MotionSnapshot,
    PoseSnapshot,
    evaluate_geofence,
)
from .evidence_store import EvidenceStore, EvidenceStoreError
from .marker_protocol import MarkerDetection, MarkerProtocolError, parse_marker_frame


class CheckpointVerifier(Node):
    def __init__(self) -> None:
        super().__init__('checkpoint_verifier')
        self._declare_parameters()
        self._callback_group = ReentrantCallbackGroup()
        self._lock = threading.RLock()
        self._pose: Optional[PoseSnapshot] = None
        self._motion: Optional[MotionSnapshot] = None
        self._images = deque(maxlen=int(self.get_parameter('image_cache_size').value))
        self._marker_frames = deque(maxlen=120)
        self._marker_sequence = 0
        self._active = False

        self.cv2 = self._load_cv2()
        self.numpy = self._load_numpy()
        self.bridge = self._load_bridge()
        self.evidence_store = EvidenceStore(str(self.get_parameter('evidence_root').value))

        self.create_subscription(
            PoseWithCovarianceStamped,
            str(self.get_parameter('localization_topic').value),
            self._on_pose,
            10,
            callback_group=self._callback_group,
        )
        self.create_subscription(
            Twist,
            str(self.get_parameter('control_output_topic').value),
            self._on_motion,
            10,
            callback_group=self._callback_group,
        )
        self.create_subscription(
            String,
            str(self.get_parameter('marker_topic').value),
            self._on_markers,
            10,
            callback_group=self._callback_group,
        )
        self.create_subscription(
            Image,
            str(self.get_parameter('image_topic').value),
            self._on_image,
            10,
            callback_group=self._callback_group,
        )
        self.action_server = ActionServer(
            self,
            VerifyCheckpoint,
            str(self.get_parameter('action_name').value),
            execute_callback=self._execute,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
            callback_group=self._callback_group,
        )
        if self.cv2 is None or self.bridge is None:
            self.get_logger().warn(
                'cv_bridge/OpenCV unavailable: visual-marker check-ins will fail safely, geofence check-ins remain available'
            )
        self.get_logger().info('Checkpoint verifier is ready')

    def _declare_parameters(self) -> None:
        self.declare_parameter('action_name', 'verify_checkpoint')
        self.declare_parameter('localization_topic', '/amcl_pose')
        self.declare_parameter('control_output_topic', '/control/cmd_vel')
        self.declare_parameter('marker_topic', '/inspection/marker_detections')
        self.declare_parameter('image_topic', '/camera/color/image_raw')
        self.declare_parameter('evidence_root', '~/.icar/evidence')
        self.declare_parameter('pose_max_age_sec', 1.0)
        self.declare_parameter('motion_max_age_sec', 0.5)
        self.declare_parameter('image_max_age_sec', 1.0)
        self.declare_parameter('image_cache_size', 30)
        self.declare_parameter('still_linear_speed_mps', 0.02)
        self.declare_parameter('still_angular_speed_rps', 0.03)
        self.declare_parameter('poll_period_sec', 0.10)

    # Sensor callbacks ---------------------------------------------------
    def _on_pose(self, msg: PoseWithCovarianceStamped) -> None:
        orientation = msg.pose.pose.orientation
        yaw = math.atan2(
            2.0 * (orientation.w * orientation.z + orientation.x * orientation.y),
            1.0 - 2.0 * (orientation.y * orientation.y + orientation.z * orientation.z),
        )
        snapshot = PoseSnapshot(
            x=float(msg.pose.pose.position.x),
            y=float(msg.pose.pose.position.y),
            yaw=yaw,
            covariance_x=float(msg.pose.covariance[0]),
            covariance_y=float(msg.pose.covariance[7]),
            covariance_yaw=float(msg.pose.covariance[35]),
            received_at=time.monotonic(),
        )
        with self._lock:
            self._pose = snapshot

    def _on_motion(self, msg: Twist) -> None:
        with self._lock:
            self._motion = MotionSnapshot(
                linear_x=float(msg.linear.x),
                angular_z=float(msg.angular.z),
                received_at=time.monotonic(),
            )

    def _on_image(self, msg: Image) -> None:
        if self.bridge is None:
            return
        try:
            image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as exc:
            self.get_logger().debug(f'Could not convert evidence image: {exc}')
            return
        with self._lock:
            self._images.append((
                (int(msg.header.stamp.sec), int(msg.header.stamp.nanosec)),
                time.monotonic(),
                image,
            ))

    def _on_markers(self, msg: String) -> None:
        try:
            markers, stamp = parse_marker_frame(msg.data)
        except MarkerProtocolError as exc:
            self.get_logger().warn(f'Ignoring malformed marker detector payload: {exc}')
            return
        with self._lock:
            self._marker_sequence += 1
            self._marker_frames.append((self._marker_sequence, time.monotonic(), stamp, markers))

    # Action callbacks ---------------------------------------------------
    def _goal_callback(self, goal_request) -> GoalResponse:
        if goal_request.method not in {'geofence', 'visual_marker'}:
            self.get_logger().warn(f'Rejecting unsupported check-in method: {goal_request.method!r}')
            return GoalResponse.REJECT
        if goal_request.timeout_sec <= 0.0 or goal_request.confirmation_frames == 0:
            return GoalResponse.REJECT
        if (
            goal_request.position_tolerance_m <= 0.0
            or goal_request.yaw_tolerance_rad <= 0.0
            or goal_request.max_pose_covariance <= 0.0
            or goal_request.dwell_sec < 0.0
        ):
            return GoalResponse.REJECT
        if goal_request.method == 'visual_marker' and (
            goal_request.marker_type not in {'qr', 'apriltag'}
            or not goal_request.expected_marker_id.strip()
        ):
            return GoalResponse.REJECT
        with self._lock:
            if self._active:
                self.get_logger().warn('Rejecting a concurrent checkpoint verification')
                return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    @staticmethod
    def _cancel_callback(_goal_handle) -> CancelResponse:
        return CancelResponse.ACCEPT

    async def _execute(self, goal_handle) -> VerifyCheckpoint.Result:
        request = goal_handle.request
        with self._lock:
            self._active = True
            marker_sequence = self._marker_sequence
        try:
            return await self._run_checkin(goal_handle, marker_sequence)
        finally:
            with self._lock:
                self._active = False

    async def _run_checkin(self, goal_handle, marker_sequence: int) -> VerifyCheckpoint.Result:
        request = goal_handle.request
        start = time.monotonic()
        deadline = start + float(request.timeout_sec)
        dwell_started_at: Optional[float] = None
        tracker = MarkerConfirmationTracker(
            request.marker_type, request.expected_marker_id, int(request.confirmation_frames)
        )
        self._feedback(goal_handle, 'GEOFENCE', 0.05, 'Waiting for stable localized arrival')

        while True:
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                return self._result(False, 'CANCELLED', '', tracker.count, '', 'Checkpoint verification cancelled')
            now = time.monotonic()
            if now >= deadline:
                goal_handle.abort()
                return self._result(
                    False, 'TIMEOUT', '', tracker.count, '', 'Timed out waiting for checkpoint proof'
                )
            verdict = self._geofence_verdict(request, now)
            if not verdict.passed:
                dwell_started_at = None
                self._feedback(
                    goal_handle,
                    'GEOFENCE',
                    0.10,
                    'Waiting for stable arrival: ' + ','.join(verdict.reasons),
                )
                await self._wait_period()
                continue
            if dwell_started_at is None:
                dwell_started_at = now
                self._feedback(goal_handle, 'DWELL', 0.25, 'Arrival fence reached; confirming dwell')
            if now - dwell_started_at < float(request.dwell_sec):
                await self._wait_period()
                continue
            if request.method == 'geofence':
                goal_handle.succeed()
                return self._result(
                    True,
                    'GEOFENCE_VERIFIED',
                    '',
                    0,
                    '',
                    'Position, orientation, covariance, velocity, and dwell checks passed',
                )

            self._feedback(
                goal_handle,
                'MARKER',
                0.50,
                f'Waiting for {request.marker_type}:{request.expected_marker_id}',
            )
            marker_sequence, frames, dropped_frames = self._marker_frames_since(marker_sequence)
            if dropped_frames:
                # The action did not observe every detector frame.  Reset the
                # counter rather than accepting a non-provable sequence.
                tracker.observe('', '', ('dropped', marker_sequence))
            for frame_sequence, received_at, stamp, markers in frames:
                if now - received_at > float(self.get_parameter('image_max_age_sec').value):
                    tracker.observe('', '', frame_sequence)
                    continue
                marker = next((
                    item for item in markers
                    if item.marker_type == request.marker_type
                    and item.marker_id == request.expected_marker_id
                ), None)
                if marker is None:
                    # A fresh empty or mismatched detector frame breaks
                    # consecutiveness; only sequential proof is accepted.
                    tracker.observe('', '', frame_sequence)
                    continue
                tracker.observe(marker.marker_type, marker.marker_id, frame_sequence)
                self._feedback(
                    goal_handle,
                    'MARKER',
                    min(0.95, 0.50 + 0.45 * tracker.count / tracker.required_frames),
                    f'Marker confirmation {tracker.count}/{tracker.required_frames}',
                )
                if tracker.confirmed:
                    try:
                        evidence_path = self._save_evidence(request, marker, stamp, now)
                    except EvidenceStoreError as exc:
                        goal_handle.abort()
                        return self._result(
                            False, 'EVIDENCE_WRITE_FAILED', marker.marker_id, tracker.count, '', str(exc)
                        )
                    goal_handle.succeed()
                    return self._result(
                        True,
                        'VISUAL_MARKER_VERIFIED',
                        marker.marker_id,
                        tracker.count,
                        evidence_path,
                        'Expected marker was confirmed in consecutive frames',
                    )
            await self._wait_period()

    def _geofence_verdict(self, request, now: float):
        with self._lock:
            pose = self._pose
            motion = self._motion
        return evaluate_geofence(
            GeofencePolicy(
                target_x=float(request.target_x),
                target_y=float(request.target_y),
                target_yaw=float(request.target_yaw),
                position_tolerance_m=float(request.position_tolerance_m),
                yaw_tolerance_rad=float(request.yaw_tolerance_rad),
                max_pose_covariance=float(request.max_pose_covariance),
                max_linear_speed_mps=float(self.get_parameter('still_linear_speed_mps').value),
                max_angular_speed_rps=float(self.get_parameter('still_angular_speed_rps').value),
                pose_max_age_sec=float(self.get_parameter('pose_max_age_sec').value),
                motion_max_age_sec=float(self.get_parameter('motion_max_age_sec').value),
            ),
            pose,
            motion,
            now,
        )

    def _marker_frames_since(self, previous_sequence: int):
        with self._lock:
            sequence = self._marker_sequence
            frames = tuple(frame for frame in self._marker_frames if frame[0] > previous_sequence)
        if not frames:
            return previous_sequence, (), False
        dropped_frames = frames[0][0] > previous_sequence + 1
        return sequence, frames, dropped_frames

    def _save_evidence(
        self,
        request,
        marker: MarkerDetection,
        image_stamp: Tuple[int, int],
        now: float,
    ) -> str:
        if self.cv2 is None or self.numpy is None:
            raise EvidenceStoreError('OpenCV/numpy is unavailable for evidence capture')
        with self._lock:
            matching = next(
                (
                    (received_at, image)
                    for stamp, received_at, image in reversed(self._images)
                    if stamp == image_stamp
                ),
                None,
            )
        if matching is None:
            raise EvidenceStoreError('no camera image matches the marker detector timestamp')
        image_received_at, raw_image = matching
        if now - image_received_at > float(self.get_parameter('image_max_age_sec').value):
            raise EvidenceStoreError('camera image matching the marker is too old for evidence')
        image = raw_image.copy()
        if marker.polygon:
            points = self.numpy.array(marker.polygon, dtype=self.numpy.int32).reshape((-1, 1, 2))
            self.cv2.polylines(image, [points], True, (0, 255, 0), 2)
        encoded, buffer = self.cv2.imencode('.jpg', image)
        if not encoded:
            raise EvidenceStoreError('could not JPEG-encode marker evidence')
        record = self.evidence_store.store_bytes(
            mission_id=request.mission_id,
            checkpoint_id=request.checkpoint_id,
            kind='checkin_marker',
            content=bytes(buffer),
            extension='jpg',
            metadata={
                'method': request.method,
                'marker_type': marker.marker_type,
                'marker_id': marker.marker_id,
                'expected_marker_id': request.expected_marker_id,
                'confirmation_frames': int(request.confirmation_frames),
                'image_stamp': {'sec': image_stamp[0], 'nanosec': image_stamp[1]},
                'polygon': [[x, y] for x, y in marker.polygon],
            },
        )
        return str(record['path'])

    def _feedback(self, goal_handle, stage: str, progress: float, detail: str) -> None:
        feedback = VerifyCheckpoint.Feedback()
        feedback.stage = stage
        feedback.progress = float(progress)
        feedback.detail = detail
        goal_handle.publish_feedback(feedback)

    async def _wait_period(self) -> None:
        future = Future()
        holder: Dict[str, Any] = {}

        def complete() -> None:
            if not future.done():
                future.set_result(True)
            self.destroy_timer(holder['timer'])

        holder['timer'] = self.create_timer(
            float(self.get_parameter('poll_period_sec').value),
            complete,
            callback_group=self._callback_group,
        )
        await future

    @staticmethod
    def _result(
        success: bool,
        outcome: str,
        marker_id: str,
        confirmation_count: int,
        evidence_path: str,
        detail: str,
    ) -> VerifyCheckpoint.Result:
        result = VerifyCheckpoint.Result()
        result.success = success
        result.outcome = outcome
        result.marker_id = marker_id
        result.confirmation_count = confirmation_count
        result.evidence_path = evidence_path
        result.detail = detail
        return result

    @staticmethod
    def _load_cv2() -> Optional[Any]:
        try:
            import cv2
            return cv2
        except ImportError:
            return None

    @staticmethod
    def _load_numpy() -> Optional[Any]:
        try:
            import numpy
            return numpy
        except ImportError:
            return None

    @staticmethod
    def _load_bridge() -> Optional[Any]:
        try:
            from cv_bridge import CvBridge
            return CvBridge()
        except ImportError:
            return None


def main(args: Optional[Sequence[str]] = None) -> None:
    rclpy.init(args=args)
    node = CheckpointVerifier()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
