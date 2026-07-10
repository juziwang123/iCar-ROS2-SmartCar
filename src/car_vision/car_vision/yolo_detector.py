"""Local-model YOLO detector that publishes APP-compatible JSON detections."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String


class YoloDetector(Node):
    """Run an Ultralytics YOLO model stored locally on the car.

    The model is never downloaded at runtime.  This avoids an unexpected
    network dependency and makes the model used during a demonstration fully
    deterministic.
    """

    def __init__(self) -> None:
        super().__init__('yolo_detector')
        self.declare_parameter('image_topic', '/camera/color/image_raw')
        self.declare_parameter('detection_topic', '/vision/detections')
        self.declare_parameter('model_path', 'models/model.pt')
        self.declare_parameter('device', 'auto')
        self.declare_parameter('confidence_threshold', 0.45)
        self.declare_parameter('iou_threshold', 0.45)
        self.declare_parameter('image_size', 640)
        self.declare_parameter('max_detections', 100)
        self.declare_parameter('inference_rate_hz', 8.0)

        self.bridge = self._load_bridge()
        self.model = None
        self.model_file: Optional[Path] = None
        self.unavailable_reason: Optional[str] = None
        self.last_inference_time = 0.0
        self._load_model()

        self.publisher = self.create_publisher(
            String, str(self.get_parameter('detection_topic').value), 10
        )
        self.create_subscription(
            Image, str(self.get_parameter('image_topic').value), self._on_image, 10
        )
        if self.model is not None:
            self.get_logger().info(f'YOLO detector started with {self.model_file}')
        else:
            self.get_logger().error(f'YOLO detector is unavailable: {self.unavailable_reason}')

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
            # Passing an existing path is deliberate: Ultralytics only loads it
            # and cannot fall back to downloading a pretrained model by name.
            self.model = YOLO(str(model_file))
            self.model_file = model_file
        except Exception as exc:
            self.unavailable_reason = f'could not load {model_file}: {exc}'
            self.model = None

    @staticmethod
    def _package_root() -> Path:
        # Source tree: <package>/car_vision/yolo_detector.py.  The installed
        # package is resolved separately below through ament when available.
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

    def _on_image(self, msg: Image) -> None:
        if not self._inference_due():
            return
        if self.model is None or self.bridge is None:
            self._publish_detections([], error=self.unavailable_reason or 'cv_bridge is unavailable')
            return
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            detections = self._infer(frame)
        except Exception as exc:
            self.get_logger().error(f'YOLO inference failed: {exc}')
            self._publish_detections([], error='inference failed')
            return
        self._publish_detections(detections, image_width=frame.shape[1], image_height=frame.shape[0])

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
            'conf': float(self.get_parameter('confidence_threshold').value),
            'iou': float(self.get_parameter('iou_threshold').value),
            'imgsz': int(self.get_parameter('image_size').value),
            'max_det': int(self.get_parameter('max_detections').value),
        }
        if device and device != 'auto':
            kwargs['device'] = device
        result = self.model.predict(frame, **kwargs)[0]
        names = result.names
        detections: List[Dict[str, Any]] = []
        for box in result.boxes:
            class_id = int(box.cls.item())
            x_min, y_min, x_max, y_max = (float(value) for value in box.xyxy[0].tolist())
            label = names[class_id] if isinstance(names, dict) else names[class_id]
            detections.append({
                'label': str(label),
                'class_id': class_id,
                'confidence': float(box.conf.item()),
                'x_min': x_min,
                'y_min': y_min,
                'x_max': x_max,
                'y_max': y_max,
                'center_x': (x_min + x_max) / 2.0,
                'center_y': (y_min + y_max) / 2.0,
                'width': x_max - x_min,
                'height': y_max - y_min,
            })
        return detections

    def _publish_detections(
        self,
        detections: List[Dict[str, Any]],
        *,
        image_width: Optional[int] = None,
        image_height: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            'detected': bool(detections),
            'detections': detections,
            'model': self.model_file.name if self.model_file else None,
        }
        if image_width is not None and image_height is not None:
            payload['image'] = {'width': image_width, 'height': image_height}
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


def main(args: Optional[Sequence[str]] = None) -> None:
    rclpy.init(args=args)
    node = YoloDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
