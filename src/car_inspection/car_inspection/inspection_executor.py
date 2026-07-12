"""Capture inspection evidence and produce conservative structured results."""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional, Sequence, Tuple

import rclpy
from car_interfaces.action import RunInspection
from car_interfaces.msg import InspectionResult
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from rclpy.task import Future
from sensor_msgs.msg import Image
from std_msgs.msg import String

from .evidence_store import EvidenceStore, EvidenceStoreError
from .image_capture import BufferedImage, ImageBuffer, encode_jpeg
from .inspection_schema import (
    InspectionDecision,
    LocalObservation,
    decision_to_mapping,
    fuse_observations,
    local_observation_from_payload,
)
from .vlm_client import VlmAttempt, VlmClient


class InspectionExecutor(Node):
    """One-at-a-time visual inspection action server.

    Model deployment is intentionally external: this component consumes the
    stamped output of ``car_vision/yolo_detector`` and optionally a configured
    HTTP VLM.  Missing, stale, or invalid model outputs degrade to UNKNOWN.
    """

    def __init__(self) -> None:
        super().__init__('inspection_executor')
        self._declare_parameters()
        self._callback_group = ReentrantCallbackGroup()
        self._lock = threading.RLock()
        self._images = ImageBuffer(int(self.get_parameter('inspection_image_cache_size').value))
        self._detections = deque(maxlen=int(self.get_parameter('inspection_detection_cache_size').value))
        self._active = False
        self.cv2 = self._load_cv2()
        self.bridge = self._load_bridge()
        self.evidence_store = EvidenceStore(str(self.get_parameter('evidence_root').value))
        self.vlm_client = VlmClient(
            str(self.get_parameter('inspection_vlm_endpoint').value),
            float(self.get_parameter('inspection_vlm_timeout_sec').value),
        )

        self.create_subscription(
            Image,
            str(self.get_parameter('image_topic').value),
            self._on_image,
            10,
            callback_group=self._callback_group,
        )
        self.create_subscription(
            String,
            str(self.get_parameter('inspection_detection_topic').value),
            self._on_detection,
            10,
            callback_group=self._callback_group,
        )
        self.result_publisher = self.create_publisher(
            InspectionResult, str(self.get_parameter('inspection_result_topic').value), 10
        )
        self.action_server = ActionServer(
            self,
            RunInspection,
            str(self.get_parameter('inspection_action_name').value),
            execute_callback=self._execute,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
            callback_group=self._callback_group,
        )
        if self.cv2 is None or self.bridge is None:
            self.get_logger().warn('cv_bridge/OpenCV unavailable: inspections will return UNKNOWN safely')
        self.get_logger().info('Inspection executor is ready')

    def _declare_parameters(self) -> None:
        self.declare_parameter('inspection_action_name', 'run_inspection')
        self.declare_parameter('image_topic', '/camera/color/image_raw')
        self.declare_parameter('inspection_detection_topic', '/vision/detections')
        self.declare_parameter('inspection_result_topic', '/inspection/result')
        self.declare_parameter('evidence_root', '~/.icar/evidence')
        self.declare_parameter('inspection_image_cache_size', 30)
        self.declare_parameter('inspection_detection_cache_size', 60)
        self.declare_parameter('inspection_capture_settle_sec', 0.5)
        self.declare_parameter('inspection_capture_timeout_sec', 5.0)
        self.declare_parameter('inspection_detection_wait_sec', 0.8)
        self.declare_parameter('inspection_detection_max_age_sec', 1.5)
        self.declare_parameter('inspection_allow_local_absent', False)
        self.declare_parameter('inspection_vlm_endpoint', '')
        self.declare_parameter('inspection_vlm_timeout_sec', 15.0)
        self.declare_parameter('inspection_poll_period_sec', 0.05)

    # Inputs -------------------------------------------------------------
    def _on_image(self, msg: Image) -> None:
        if self.bridge is None:
            return
        try:
            image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as exc:
            self.get_logger().debug(f'Could not convert inspection image: {exc}')
            return
        with self._lock:
            self._images.append(
                (int(msg.header.stamp.sec), int(msg.header.stamp.nanosec)),
                time.monotonic(),
                image,
            )

    def _on_detection(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warn('Ignoring malformed /vision/detections JSON')
            return
        stamp = _payload_stamp(payload)
        if stamp is None:
            # Unstamped detections cannot be bound to captured evidence and
            # must never be used to make an absence/presence decision.
            return
        with self._lock:
            self._detections.append((stamp, time.monotonic(), payload))

    # Action -------------------------------------------------------------
    def _goal_callback(self, goal_request) -> GoalResponse:
        if goal_request.task_type != 'visual_presence':
            return GoalResponse.REJECT
        if not goal_request.mission_id.strip() or not goal_request.checkpoint_id.strip():
            return GoalResponse.REJECT
        if not goal_request.task_id.strip() or not goal_request.target.strip():
            return GoalResponse.REJECT
        if goal_request.capture_count == 0 or goal_request.capture_count > 5:
            return GoalResponse.REJECT
        if goal_request.confidence_threshold < 0.0 or goal_request.confidence_threshold > 1.0:
            return GoalResponse.REJECT
        with self._lock:
            if self._active:
                return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    @staticmethod
    def _cancel_callback(_goal_handle) -> CancelResponse:
        return CancelResponse.ACCEPT

    async def _execute(self, goal_handle) -> RunInspection.Result:
        with self._lock:
            self._active = True
            start_sequence = self._images.sequence
        try:
            return await self._run(goal_handle, start_sequence)
        finally:
            with self._lock:
                self._active = False

    async def _run(self, goal_handle, start_sequence: int) -> RunInspection.Result:
        request = goal_handle.request
        if self.cv2 is None or self.bridge is None:
            return self._complete(
                goal_handle,
                success=False,
                decision=InspectionDecision(
                    'UNKNOWN', 0.0, True, 'none', 'camera conversion dependencies are unavailable'
                ),
                evidence_paths=[],
                detail={'error': 'CAMERA_DEPENDENCY_UNAVAILABLE'},
            )

        self._feedback(goal_handle, 'CAPTURING', 0.05, 'Waiting for post-arrival camera frames')
        settle_until = time.monotonic() + float(
            self.get_parameter('inspection_capture_settle_sec').value
        )
        while time.monotonic() < settle_until:
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                return self._result(False, 'UNKNOWN', 0.0, True, [], {'error': 'CANCELLED'})
            await self._wait_period()

        captures = await self._capture_frames(goal_handle, start_sequence)
        if captures is None:
            goal_handle.canceled()
            return self._result(False, 'UNKNOWN', 0.0, True, [], {'error': 'CANCELLED'})
        if not captures:
            return self._complete(
                goal_handle,
                success=False,
                decision=InspectionDecision('UNKNOWN', 0.0, True, 'none', 'no fresh camera image was captured'),
                evidence_paths=[],
                detail={'error': 'CAPTURE_TIMEOUT'},
            )

        self._feedback(goal_handle, 'INSPECTING', 0.55, 'Matching local detections to captured images')
        await self._wait_for_detection_window(goal_handle)
        if goal_handle.is_cancel_requested:
            goal_handle.canceled()
            return self._result(False, 'UNKNOWN', 0.0, True, [], {'error': 'CANCELLED'})
        detection_payloads = self._capture_detection_payloads(captures)
        local = self._local_observation(
            captures,
            request.target,
            float(request.confidence_threshold),
            request.local_model,
            detection_payloads,
        )
        vlm_attempt = VlmAttempt(None, '', '')
        if bool(request.use_vlm_fallback) and local.status != 'PRESENT':
            self._feedback(goal_handle, 'INSPECTING', 0.75, 'Requesting optional VLM review')
            vlm_attempt = self.vlm_client.review(
                task=request.task_type,
                target=request.target,
                image_bytes=captures[-1]['jpeg'],
            )
        decision = fuse_observations(local, vlm_attempt.review)
        evidence_paths = [capture['path'] for capture in captures]
        detail = {
            'task_type': request.task_type,
            'target': request.target,
            'local': {
                'status': local.status,
                'confidence': local.confidence,
                'model': local.model,
                'detail': local.detail,
            },
            'local_detector_payloads': detection_payloads,
            'decision': decision_to_mapping(decision),
            'vlm_error': vlm_attempt.error,
        }
        try:
            detector_record = self.evidence_store.store_bytes(
                mission_id=request.mission_id,
                checkpoint_id=request.checkpoint_id,
                kind='local_detection',
                content=json.dumps(detection_payloads, ensure_ascii=False, sort_keys=True).encode('utf-8'),
                extension='json',
                metadata={'task_id': request.task_id, 'expected_model': request.local_model},
            )
            evidence_paths.append(str(detector_record['path']))
        except EvidenceStoreError as exc:
            detail['local_detection_evidence_error'] = str(exc)
        if vlm_attempt.raw_response:
            try:
                vlm_record = self.evidence_store.store_bytes(
                    mission_id=request.mission_id,
                    checkpoint_id=request.checkpoint_id,
                    kind='vlm_response',
                    content=vlm_attempt.raw_response.encode('utf-8'),
                    extension='json',
                    metadata={'task_id': request.task_id, 'task_type': request.task_type},
                )
                evidence_paths.append(str(vlm_record['path']))
            except EvidenceStoreError as exc:
                detail['vlm_evidence_error'] = str(exc)
        try:
            result_record = self.evidence_store.store_bytes(
                mission_id=request.mission_id,
                checkpoint_id=request.checkpoint_id,
                kind='inspection_result',
                content=json.dumps(detail, ensure_ascii=False, sort_keys=True).encode('utf-8'),
                extension='json',
                metadata={'task_id': request.task_id, 'conclusion': decision.conclusion},
            )
            evidence_paths.append(str(result_record['path']))
        except EvidenceStoreError as exc:
            detail['result_evidence_error'] = str(exc)
            decision = InspectionDecision(
                'UNKNOWN', 0.0, True, 'none', 'inspection result could not be persisted'
            )

        return self._complete(
            goal_handle,
            success=True,
            decision=decision,
            evidence_paths=evidence_paths,
            detail=detail,
        )

    async def _capture_frames(self, goal_handle, start_sequence: int) -> Optional[List[Dict[str, Any]]]:
        request = goal_handle.request
        deadline = time.monotonic() + float(
            self.get_parameter('inspection_capture_timeout_sec').value
        )
        sequence = start_sequence
        captured: List[Dict[str, Any]] = []
        while len(captured) < int(request.capture_count) and time.monotonic() < deadline:
            if goal_handle.is_cancel_requested:
                return None
            with self._lock:
                frames = self._images.after(sequence)
            for frame in frames:
                sequence = max(sequence, frame.sequence)
                try:
                    jpeg = encode_jpeg(self.cv2, frame.image)
                    record = self.evidence_store.store_bytes(
                        mission_id=request.mission_id,
                        checkpoint_id=request.checkpoint_id,
                        kind='capture',
                        content=jpeg,
                        extension='jpg',
                        metadata={
                            'task_id': request.task_id,
                            'task_type': request.task_type,
                            'target': request.target,
                            'capture_index': len(captured) + 1,
                            'stamp': {'sec': frame.stamp[0], 'nanosec': frame.stamp[1]},
                        },
                    )
                except (ValueError, EvidenceStoreError) as exc:
                    self.get_logger().warn(f'Could not persist inspection capture: {exc}')
                    continue
                captured.append({'frame': frame, 'jpeg': jpeg, 'path': str(record['path'])})
                self._feedback(
                    goal_handle,
                    'CAPTURING',
                    0.05 + 0.45 * len(captured) / int(request.capture_count),
                    f'Captured {len(captured)}/{int(request.capture_count)} image(s)',
                )
                if len(captured) >= int(request.capture_count):
                    break
            if len(captured) < int(request.capture_count):
                await self._wait_period()
        return captured

    async def _wait_for_detection_window(self, goal_handle) -> None:
        deadline = time.monotonic() + float(
            self.get_parameter('inspection_detection_wait_sec').value
        )
        while time.monotonic() < deadline and not goal_handle.is_cancel_requested:
            await self._wait_period()

    def _capture_detection_payloads(self, captures) -> List[Dict[str, Any]]:
        return [
            {
                'stamp': {
                    'sec': capture['frame'].stamp[0],
                    'nanosec': capture['frame'].stamp[1],
                },
                'payload': self._detection_for_stamp(capture['frame'].stamp),
            }
            for capture in captures
        ]

    def _local_observation(
        self,
        captures,
        target: str,
        confidence_threshold: float,
        expected_model: str,
        detection_payloads: List[Dict[str, Any]],
    ) -> LocalObservation:
        observations: List[LocalObservation] = []
        allow_absent = bool(self.get_parameter('inspection_allow_local_absent').value)
        for item in detection_payloads:
            observations.append(local_observation_from_payload(
                item.get('payload'),
                target=target,
                confidence_threshold=confidence_threshold,
                allow_absent=allow_absent,
                expected_model=expected_model,
            ))
        present = [item for item in observations if item.status == 'PRESENT']
        if present:
            return max(present, key=lambda item: item.confidence)
        absent = [item for item in observations if item.status == 'ABSENT']
        if absent:
            return max(absent, key=lambda item: item.confidence)
        unavailable = [item for item in observations if item.status == 'UNAVAILABLE']
        if unavailable:
            return unavailable[-1]
        return observations[-1] if observations else LocalObservation(
            'UNAVAILABLE', 0.0, '', 'no captured frame has a matching detector result'
        )

    def _detection_for_stamp(self, stamp: Tuple[int, int]) -> Optional[Dict[str, Any]]:
        now = time.monotonic()
        with self._lock:
            matches = [
                payload for detected_stamp, received_at, payload in self._detections
                if detected_stamp == stamp
                and now - received_at <= float(
                    self.get_parameter('inspection_detection_max_age_sec').value
                )
            ]
        return matches[-1] if matches else None

    def _complete(
        self,
        goal_handle,
        *,
        success: bool,
        decision: InspectionDecision,
        evidence_paths: List[str],
        detail: Dict[str, Any],
    ) -> RunInspection.Result:
        result = self._result(
            success,
            decision.conclusion,
            decision.confidence,
            decision.needs_human_review,
            evidence_paths,
            detail,
        )
        self._publish_result(goal_handle.request, result)
        goal_handle.succeed()
        return result

    def _publish_result(self, request, result: RunInspection.Result) -> None:
        message = InspectionResult()
        message.header.stamp = self.get_clock().now().to_msg()
        message.mission_id = request.mission_id
        message.checkpoint_id = request.checkpoint_id
        message.task_id = request.task_id
        message.task_type = request.task_type
        message.target = request.target
        message.conclusion = result.conclusion
        message.confidence = result.confidence
        message.needs_human_review = result.needs_human_review
        message.evidence_paths = list(result.evidence_paths)
        message.detail_json = result.detail_json
        self.result_publisher.publish(message)

    def _feedback(self, goal_handle, stage: str, progress: float, detail: str) -> None:
        feedback = RunInspection.Feedback()
        feedback.stage = stage
        feedback.progress = progress
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
            float(self.get_parameter('inspection_poll_period_sec').value),
            complete,
            callback_group=self._callback_group,
        )
        await future

    @staticmethod
    def _result(
        success: bool,
        conclusion: str,
        confidence: float,
        needs_human_review: bool,
        evidence_paths: List[str],
        detail: Dict[str, Any],
    ) -> RunInspection.Result:
        result = RunInspection.Result()
        result.success = success
        result.conclusion = conclusion
        result.confidence = confidence
        result.needs_human_review = needs_human_review
        result.evidence_paths = evidence_paths
        result.detail_json = json.dumps(detail, ensure_ascii=False, sort_keys=True)
        return result

    @staticmethod
    def _load_cv2() -> Optional[Any]:
        try:
            import cv2
            return cv2
        except ImportError:
            return None

    @staticmethod
    def _load_bridge() -> Optional[Any]:
        try:
            from cv_bridge import CvBridge
            return CvBridge()
        except ImportError:
            return None


def _payload_stamp(payload: Any) -> Optional[Tuple[int, int]]:
    if not isinstance(payload, dict):
        return None
    stamp = payload.get('stamp')
    if not isinstance(stamp, dict):
        return None
    sec = stamp.get('sec')
    nanosec = stamp.get('nanosec')
    if (
        isinstance(sec, bool) or isinstance(nanosec, bool)
        or not isinstance(sec, int) or not isinstance(nanosec, int)
        or sec < 0 or nanosec < 0 or nanosec >= 1000000000
    ):
        return None
    return sec, nanosec


def main(args: Optional[Sequence[str]] = None) -> None:
    rclpy.init(args=args)
    node = InspectionExecutor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
