"""Person Detection Node using Ultralytics YOLOv8.

Subscribes to a camera image topic, runs YOLO inference, and publishes
person detection results.  Only the COCO ``person`` class (class 0) is
reported; all other classes are ignored.

Publishes
---------
- ``/vision/person_detected`` (std_msgs/Bool) — whether at least one person
  is visible above the confidence threshold.
- ``/vision/person_detections`` (std_msgs/String) — JSON payload with full
  detection details (bounding boxes, confidence scores, count).
- ``/vision/person_target`` (geometry_msgs/PointStamped) — normalised position
  (-1 … 1) of the closest person (largest bounding-box area) for downstream
  tracking / avoidance nodes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Sequence

import rclpy
from cv_bridge import CvBridge
from geometry_msgs.msg import PointStamped
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, String


class PersonDetector(Node):
    """ROS2 node that detects persons in camera images using YOLO."""

    def __init__(self) -> None:
        super().__init__('person_detector')

        # --- Parameters ---
        self.declare_parameter('image_topic', '/camera/color/image_raw')
        self.declare_parameter('detection_topic', '/vision/person_detections')
        self.declare_parameter('detection_flag_topic', '/vision/person_detected')
        self.declare_parameter('target_topic', '/vision/person_target')
        self.declare_parameter('model_name', 'yolov8n.pt')
        self.declare_parameter('confidence_threshold', 0.5)
        self.declare_parameter('input_width', 640)
        self.declare_parameter('input_height', 640)
        self.declare_parameter('person_class_id', 0)  # COCO dataset

        # --- Dependencies ---
        self._cv2 = self._load_cv2()
        self._bridge = CvBridge()
        self._model = self._load_model()

        # --- Publishers ---
        self._detection_pub = self.create_publisher(
            String,
            str(self.get_parameter('detection_topic').value),
            10,
        )
        self._flag_pub = self.create_publisher(
            Bool,
            str(self.get_parameter('detection_flag_topic').value),
            10,
        )
        self._target_pub = self.create_publisher(
            PointStamped,
            str(self.get_parameter('target_topic').value),
            10,
        )

        # --- Subscriber ---
        self.create_subscription(
            Image,
            str(self.get_parameter('image_topic').value),
            self._on_image,
            10,
        )

        self.get_logger().info(
            f'Person detector started (model={self.get_parameter("model_name").value})'
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_cv2():
        """Lazy-import OpenCV so the node can degrade gracefully."""
        try:
            import cv2
            return cv2
        except ImportError:
            return None

    def _load_model(self):
        """Load the YOLO model via ultralytics (auto-downloaded if needed).

        Returns ``None`` if ultralytics is not installed or the model
        cannot be loaded — the node will publish empty detections in that
        case rather than crash.
        """
        model_name = str(self.get_parameter('model_name').value)

        # Resolve path: explicit > package models/ > ultralytics hub
        model_path = model_name
        if not os.path.isfile(model_path):
            pkg_models = Path(__file__).resolve().parent.parent / 'models'
            candidate = pkg_models / model_name
            if candidate.is_file():
                model_path = str(candidate)
            # otherwise fall through — ultralytics auto-downloads

        try:
            from ultralytics import YOLO
        except ImportError:
            self.get_logger().error(
                'ultralytics package not found. Install: pip install ultralytics'
            )
            return None

        self.get_logger().info(f'Loading YOLO model from {model_path}')
        try:
            return YOLO(model_path)
        except Exception as exc:
            self.get_logger().error(f'Failed to load YOLO model: {exc}')
            return None

    # ------------------------------------------------------------------
    # Callback
    # ------------------------------------------------------------------

    def _on_image(self, msg: Image) -> None:
        if self._model is None:
            self._publish_empty()
            return

        try:
            cv_image = self._bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as exc:
            self.get_logger().error(f'cv_bridge conversion failed: {exc}')
            self._publish_empty()
            return

        height, width = cv_image.shape[:2]

        # --- Inference ---
        results = self._model(
            cv_image,
            imgsz=(
                int(self.get_parameter('input_height').value),
                int(self.get_parameter('input_width').value),
            ),
            verbose=False,
        )[0]

        person_class_id = int(self.get_parameter('person_class_id').value)
        conf_threshold = float(self.get_parameter('confidence_threshold').value)

        persons: list[dict] = []
        person_detected = False

        if results.boxes is not None:
            boxes = results.boxes
            for i in range(len(boxes)):
                cls_id = int(boxes.cls[i].item())
                conf = float(boxes.conf[i].item())

                if cls_id == person_class_id and conf >= conf_threshold:
                    person_detected = True
                    x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                    persons.append({
                        'label': 'person',
                        'confidence': round(conf, 4),
                        'bbox': [int(x1), int(y1), int(x2), int(y2)],
                        'center_x': round((x1 + x2) / 2.0, 2),
                        'center_y': round((y1 + y2) / 2.0, 2),
                        'width': round(x2 - x1, 2),
                        'height': round(y2 - y1, 2),
                    })

        # --- Publish ---
        self._flag_pub.publish(Bool(data=person_detected))

        det_msg = String()
        det_msg.data = json.dumps({
            'detected': person_detected,
            'count': len(persons),
            'persons': persons,
            'image_width': width,
            'image_height': height,
        })
        self._detection_pub.publish(det_msg)

        # Publish target: closest person (largest bounding box)
        if person_detected and persons:
            closest = max(persons, key=lambda p: p['width'] * p['height'])
            target = PointStamped()
            target.header = msg.header
            target.point.x = (closest['center_x'] - width / 2.0) / (width / 2.0)
            target.point.y = (closest['center_y'] - height / 2.0) / (height / 2.0)
            target.point.z = closest['confidence']
            self._target_pub.publish(target)

    def _publish_empty(self) -> None:
        """Publish 'no detection' on all topics when the model is unavailable."""
        self._flag_pub.publish(Bool(data=False))
        self._detection_pub.publish(String(data=json.dumps({
            'detected': False,
            'count': 0,
            'persons': [],
            'image_width': 0,
            'image_height': 0,
        })))


def main(args: Optional[Sequence[str]] = None) -> None:
    rclpy.init(args=args)
    node = PersonDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
