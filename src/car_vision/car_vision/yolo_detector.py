"""Local YOLO person detection, depth safety, and APP-selected person following."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, String


class YoloDetector(Node):
    """Detect and track people with a local model; never download a model at runtime."""

    def __init__(self) -> None:
        super().__init__('yolo_detector')
        self._declare_parameters()
        self.bridge = self._load_bridge()
        self.np = self._load_numpy()
        self.model = None
        self.model_file: Optional[Path] = None
        self.unavailable_reason: Optional[str] = None
        self.last_inference_time = 0.0
        self.last_depth_time = 0.0
        self.latest_depth = None
        self.latest_depth_encoding = ''
        self.selected_track_id: Optional[int] = None
        self.estop_confirmations = 0
        self._load_model()

        self.publisher = self.create_publisher(
            String, str(self.get_parameter('detection_topic').value), 10
        )
        self.follow_publisher = self.create_publisher(
            Twist, str(self.get_parameter('follow_output_topic').value), 10
        )
        self.person_slow_publisher = self.create_publisher(
            Bool, str(self.get_parameter('person_slow_topic').value), 10
        )
        self.person_estop_publisher = self.create_publisher(
            Bool, str(self.get_parameter('person_estop_topic').value), 10
        )
        self.create_subscription(
            Image, str(self.get_parameter('image_topic').value), self._on_image, 10
        )
        self.create_subscription(
            Image, str(self.get_parameter('depth_topic').value), self._on_depth, 10
        )
        self.create_subscription(
            String, str(self.get_parameter('follow_target_topic').value), self._on_follow_target, 10
        )
        if self.model is not None:
            self.get_logger().info(f'YOLO detector started with {self.model_file}')
        else:
            self.get_logger().error(f'YOLO detector is unavailable: {self.unavailable_reason}')

    def _declare_parameters(self) -> None:
        self.declare_parameter('image_topic', '/camera/color/image_raw')
        self.declare_parameter('depth_topic', '/camera/depth/image_raw')
        self.declare_parameter('detection_topic', '/vision/detections')
        self.declare_parameter('follow_target_topic', '/vision/follow_target')
        self.declare_parameter('follow_output_topic', '/cmd_vel_follow')
        self.declare_parameter('person_slow_topic', '/vision/person_slow')
        self.declare_parameter('person_estop_topic', '/vision/person_estop')
        self.declare_parameter('model_path', 'models/model.pt')
        self.declare_parameter('device', 'auto')
        self.declare_parameter('confidence_threshold', 0.45)
        self.declare_parameter('iou_threshold', 0.45)
        self.declare_parameter('image_size', 640)
        self.declare_parameter('max_detections', 100)
        self.declare_parameter('inference_rate_hz', 8.0)
        self.declare_parameter('person_labels', ['person'])
        self.declare_parameter('depth_timeout_sec', 0.5)
        self.declare_parameter('depth_unit_scale', 0.001)
        self.declare_parameter('depth_roi_ratio', 0.5)
        self.declare_parameter('depth_min_m', 0.15)
        self.declare_parameter('depth_max_m', 8.0)
        self.declare_parameter('person_slow_distance_m', 1.2)
        self.declare_parameter('person_estop_distance_m', 0.55)
        self.declare_parameter('person_estop_confirm_frames', 2)
        self.declare_parameter('follow_desired_distance_m', 1.0)
        self.declare_parameter('follow_distance_tolerance_m', 0.15)
        self.declare_parameter('follow_linear_gain', 0.45)
        self.declare_parameter('follow_angular_gain', 0.8)
        self.declare_parameter('follow_max_linear_speed', 0.18)
        self.declare_parameter('follow_max_angular_speed', 0.7)

    def _load_model(self) -> None:
        configured_path = str(self.get_parameter('model_path').value).strip()
        if not configured_path:
            self.unavailable_reason = 'model_path is empty'
            return
        model_file = self._resolve_model_path(configured_path)
        if model_file is None:
            self.unavailable_reason = f'local model not found: {configured_path}'
            return
        try:
            from ultralytics import YOLO
        except ImportError:
            self.unavailable_reason = 'ultralytics is not installed; install requirements-vision.txt'
            return
        try:
            self.model = YOLO(str(model_file))
            self.model_file = model_file
        except Exception as exc:
            self.unavailable_reason = f'could not load {model_file}: {exc}'
            self.model = None

    @staticmethod
    def _package_root() -> Path:
        return Path(__file__).resolve().parents[1]

    def _resolve_model_path(self, configured_path: str) -> Optional[Path]:
        requested = Path(configured_path).expanduser()
        candidates = [requested]
        if not requested.is_absolute():
            package_root = self._package_root()
            candidates.extend([package_root / requested, package_root / 'models' / requested])
            try:
                from ament_index_python.packages import get_package_share_directory

                share_directory = Path(get_package_share_directory('car_vision'))
                candidates.extend([share_directory / requested, share_directory / 'models' / requested])
            except (ImportError, ValueError):
                pass
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        return None

    def _on_depth(self, msg: Image) -> None:
        if self.bridge is None:
            return
        try:
            self.latest_depth = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
            self.latest_depth_encoding = msg.encoding.lower()
            self.last_depth_time = time.monotonic()
        except Exception as exc:
            self.get_logger().warn(f'Could not decode depth image: {exc}')

    def _on_follow_target(self, msg: String) -> None:
        value = msg.data.strip()
        if not value:
            self.selected_track_id = None
            self.follow_publisher.publish(Twist())
            return
        try:
            track_id = int(value)
        except ValueError:
            self.get_logger().warn(f'Ignoring invalid follow target: {value!r}')
            return
        if track_id < 0:
            self.get_logger().warn(f'Ignoring negative follow target: {track_id}')
            return
        self.selected_track_id = track_id
        self.get_logger().info(f'APP selected YOLO track {track_id} for following')

    def _on_image(self, msg: Image) -> None:
        if not self._inference_due():
            return
        if self.model is None or self.bridge is None:
            self._clear_safety_and_follow()
            self._publish_detections(
                [],
                error=self.unavailable_reason or 'cv_bridge is unavailable',
                stamp=msg.header.stamp,
                frame_id=msg.header.frame_id,
            )
            return
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            detections = self._infer(frame)
            self._attach_depth_distances(detections, frame.shape[1], frame.shape[0])
        except Exception as exc:
            self.get_logger().error(f'YOLO inference failed: {exc}')
            self._clear_safety_and_follow()
            self._publish_detections(
                [], error='inference failed', stamp=msg.header.stamp, frame_id=msg.header.frame_id
            )
            return
        self._publish_person_safety(detections)
        self._publish_follow_command(detections, frame.shape[1])
        self._publish_detections(
            detections,
            image_width=frame.shape[1],
            image_height=frame.shape[0],
            stamp=msg.header.stamp,
            frame_id=msg.header.frame_id,
        )

    def _inference_due(self) -> bool:
        rate_hz = float(self.get_parameter('inference_rate_hz').value)
        now = time.monotonic()
        if rate_hz > 0.0 and now - self.last_inference_time < 1.0 / rate_hz:
            return False
        self.last_inference_time = now
        return True

    def _infer(self, frame: Any) -> List[Dict[str, Any]]:
        device = str(self.get_parameter('device').value).strip().lower()
        kwargs: Dict[str, Any] = {
            'verbose': False,
            'persist': True,
            'conf': float(self.get_parameter('confidence_threshold').value),
            'iou': float(self.get_parameter('iou_threshold').value),
            'imgsz': int(self.get_parameter('image_size').value),
            'max_det': int(self.get_parameter('max_detections').value),
        }
        if device and device != 'auto':
            kwargs['device'] = device
        result = self.model.track(frame, **kwargs)[0]
        names = result.names
        detections: List[Dict[str, Any]] = []
        for box in result.boxes:
            class_id = int(box.cls.item())
            x_min, y_min, x_max, y_max = (float(value) for value in box.xyxy[0].tolist())
            label = names[class_id] if isinstance(names, dict) else names[class_id]
            track_id = int(box.id.item()) if box.id is not None else None
            detections.append({
                'label': str(label),
                'class_id': class_id,
                'track_id': track_id,
                'confidence': float(box.conf.item()),
                'x_min': x_min,
                'y_min': y_min,
                'x_max': x_max,
                'y_max': y_max,
                'center_x': (x_min + x_max) / 2.0,
                'center_y': (y_min + y_max) / 2.0,
                'width': x_max - x_min,
                'height': y_max - y_min,
                'distance_m': None,
            })
        return detections

    def _attach_depth_distances(self, detections: List[Dict[str, Any]], width: int, height: int) -> None:
        if not self._has_fresh_aligned_depth(width, height):
            return
        for detection in detections:
            if self._is_person(detection):
                detection['distance_m'] = self._depth_in_box(detection)

    def _has_fresh_aligned_depth(self, width: int, height: int) -> bool:
        if self.latest_depth is None or self.np is None:
            return False
        if time.monotonic() - self.last_depth_time > float(self.get_parameter('depth_timeout_sec').value):
            return False
        return self.latest_depth.shape[0] == height and self.latest_depth.shape[1] == width

    def _depth_in_box(self, detection: Dict[str, Any]) -> Optional[float]:
        roi_ratio = max(0.1, min(1.0, float(self.get_parameter('depth_roi_ratio').value)))
        center_x = detection['center_x']
        center_y = detection['center_y']
        half_width = detection['width'] * roi_ratio / 2.0
        half_height = detection['height'] * roi_ratio / 2.0
        height, width = self.latest_depth.shape[:2]
        x_min = max(0, int(center_x - half_width))
        x_max = min(width, int(center_x + half_width))
        y_min = max(0, int(center_y - half_height))
        y_max = min(height, int(center_y + half_height))
        if x_max <= x_min or y_max <= y_min:
            return None
        depth_values = self.latest_depth[y_min:y_max, x_min:x_max].reshape(-1)
        scale = 1.0 if self.latest_depth_encoding.startswith('32f') else float(
            self.get_parameter('depth_unit_scale').value
        )
        depth_values = depth_values.astype(float) * scale
        minimum = float(self.get_parameter('depth_min_m').value)
        maximum = float(self.get_parameter('depth_max_m').value)
        valid = depth_values[self.np.isfinite(depth_values)]
        valid = valid[(valid >= minimum) & (valid <= maximum)]
        if valid.size == 0:
            return None
        return float(self.np.median(valid))

    def _publish_person_safety(self, detections: List[Dict[str, Any]]) -> None:
        distances = [item['distance_m'] for item in detections if self._is_person(item) and item['distance_m'] is not None]
        nearest = min(distances) if distances else None
        slow_active = nearest is not None and nearest <= float(self.get_parameter('person_slow_distance_m').value)
        estop_candidate = nearest is not None and nearest <= float(self.get_parameter('person_estop_distance_m').value)
        self.estop_confirmations = self.estop_confirmations + 1 if estop_candidate else 0
        estop_active = self.estop_confirmations >= int(self.get_parameter('person_estop_confirm_frames').value)
        self.person_slow_publisher.publish(Bool(data=slow_active))
        self.person_estop_publisher.publish(Bool(data=estop_active))

    def _publish_follow_command(self, detections: List[Dict[str, Any]], image_width: int) -> None:
        command = Twist()
        target = next(
            (item for item in detections if item['track_id'] == self.selected_track_id and self._is_person(item)),
            None,
        )
        if target is None or target['distance_m'] is None:
            self.follow_publisher.publish(command)
            return
        desired = float(self.get_parameter('follow_desired_distance_m').value)
        tolerance = float(self.get_parameter('follow_distance_tolerance_m').value)
        distance_error = target['distance_m'] - desired
        if abs(distance_error) > tolerance:
            command.linear.x = self._clamp(
                distance_error * float(self.get_parameter('follow_linear_gain').value),
                float(self.get_parameter('follow_max_linear_speed').value),
            )
        horizontal_error = (target['center_x'] - image_width / 2.0) / (image_width / 2.0)
        command.angular.z = self._clamp(
            -horizontal_error * float(self.get_parameter('follow_angular_gain').value),
            float(self.get_parameter('follow_max_angular_speed').value),
        )
        self.follow_publisher.publish(command)

    def _clear_safety_and_follow(self) -> None:
        self.estop_confirmations = 0
        self.person_slow_publisher.publish(Bool(data=False))
        self.person_estop_publisher.publish(Bool(data=False))
        self.follow_publisher.publish(Twist())

    def _is_person(self, detection: Dict[str, Any]) -> bool:
        return detection['label'].strip().lower() in {
            str(label).strip().lower() for label in self.get_parameter('person_labels').value
        }

    @staticmethod
    def _clamp(value: float, limit: float) -> float:
        return max(-limit, min(limit, value))

    def _publish_detections(
        self,
        detections: List[Dict[str, Any]],
        *,
        image_width: Optional[int] = None,
        image_height: Optional[int] = None,
        error: Optional[str] = None,
        stamp: Optional[Any] = None,
        frame_id: str = '',
    ) -> None:
        payload: Dict[str, Any] = {
            'detected': bool(detections),
            'detections': detections,
            'model': self.model_file.name if self.model_file else None,
            'selected_track_id': self.selected_track_id,
        }
        if image_width is not None and image_height is not None:
            payload['image'] = {'width': image_width, 'height': image_height}
        if stamp is not None:
            payload['stamp'] = {
                'sec': int(stamp.sec),
                'nanosec': int(stamp.nanosec),
                'frame_id': frame_id,
            }
        if error:
            payload['error'] = error
        self.publisher.publish(String(data=json.dumps(payload, ensure_ascii=False)))

    @staticmethod
    def _load_bridge():
        try:
            from cv_bridge import CvBridge

            return CvBridge()
        except ImportError:
            return None

    @staticmethod
    def _load_numpy():
        try:
            import numpy

            return numpy
        except ImportError:
            return None


def main(args: Optional[Sequence[str]] = None) -> None:
    rclpy.init(args=args)
    node = YoloDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node._clear_safety_and_follow()
        node.destroy_node()
        rclpy.shutdown()
