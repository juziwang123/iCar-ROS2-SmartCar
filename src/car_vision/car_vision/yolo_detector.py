from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String


class YoloDetector(Node):
    def __init__(self) -> None:
        super().__init__('yolo_detector')
        self.declare_parameter('image_topic', '/camera/color/image_raw')
        self.declare_parameter('detection_topic', '/vision/detections')
        self.declare_parameter('model_path', '')
        self.declare_parameter('class_names_path', '')
        self.declare_parameter('confidence_threshold', 0.45)

        self.bridge = self._load_bridge()
        self.cv2 = self._load_cv2()
        self.net = None
        self.classes = []
        self._load_model()
        self.publisher = self.create_publisher(String, str(self.get_parameter('detection_topic').value), 10)
        self.create_subscription(Image, str(self.get_parameter('image_topic').value), self._on_image, 10)
        self.get_logger().info('YOLO detector started')

    def _load_model(self) -> None:
        model_path = str(self.get_parameter('model_path').value)
        names_path = str(self.get_parameter('class_names_path').value)
        if not model_path:
            self.get_logger().warn('No model_path configured; yolo_detector will publish empty detections')
            return
        if self.cv2 is None:
            self.get_logger().error('cv2 is unavailable')
            return
        try:
            self.net = self.cv2.dnn.readNet(model_path)
            if names_path and Path(names_path).exists():
                self.classes = Path(names_path).read_text(encoding='utf-8').splitlines()
        except Exception as exc:
            self.get_logger().error(f'Failed to load model: {exc}')
            self.net = None

    def _on_image(self, msg: Image) -> None:
        if self.net is None or self.bridge is None or self.cv2 is None:
            self.publisher.publish(String(data=json.dumps({'detections': []})))
            return

        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        height, width = frame.shape[:2]
        blob = self.cv2.dnn.blobFromImage(frame, 1 / 255.0, (640, 640), swapRB=True, crop=False)
        self.net.setInput(blob)
        outputs = self.net.forward(self.net.getUnconnectedOutLayersNames())
        detections = self._parse_outputs(outputs, width, height)
        self.publisher.publish(String(data=json.dumps({'detections': detections})))

    def _parse_outputs(self, outputs, width: int, height: int):
        threshold = float(self.get_parameter('confidence_threshold').value)
        detections = []
        for output in outputs:
            for row in output:
                scores = row[5:]
                if len(scores) == 0:
                    continue
                class_id = int(scores.argmax())
                confidence = float(scores[class_id])
                if confidence < threshold:
                    continue
                cx, cy, box_w, box_h = row[:4]
                label = self.classes[class_id] if class_id < len(self.classes) else str(class_id)
                detections.append({
                    'label': label,
                    'confidence': confidence,
                    'center_x': float(cx) * width,
                    'center_y': float(cy) * height,
                    'width': float(box_w) * width,
                    'height': float(box_h) * height,
                })
        return detections

    @staticmethod
    def _load_bridge():
        try:
            from cv_bridge import CvBridge
            return CvBridge()
        except ImportError:
            return None

    @staticmethod
    def _load_cv2():
        try:
            import cv2
            return cv2
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
