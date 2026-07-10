from __future__ import annotations

import json
from typing import Optional, Sequence

import rclpy
from geometry_msgs.msg import PointStamped
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String


class ColorDetector(Node):
    def __init__(self) -> None:
        super().__init__('color_detector')
        self.declare_parameter('image_topic', '/camera/color/image_raw')
        self.declare_parameter('target_topic', '/vision/color_target')
        self.declare_parameter('detection_topic', '/vision/detections')
        self.declare_parameter('h_min', 0)
        self.declare_parameter('s_min', 85)
        self.declare_parameter('v_min', 80)
        self.declare_parameter('h_max', 12)
        self.declare_parameter('s_max', 255)
        self.declare_parameter('v_max', 255)
        self.declare_parameter('min_area', 500.0)

        self.bridge = self._load_bridge()
        self.cv2 = self._load_cv2()
        self.np = self._load_numpy()
        self.target_pub = self.create_publisher(PointStamped, str(self.get_parameter('target_topic').value), 10)
        self.detection_pub = self.create_publisher(String, str(self.get_parameter('detection_topic').value), 10)
        self.create_subscription(Image, str(self.get_parameter('image_topic').value), self._on_image, 10)
        self.get_logger().info('Color detector started')

    def _on_image(self, msg: Image) -> None:
        if self.bridge is None or self.cv2 is None or self.np is None:
            self.get_logger().error('cv_bridge, cv2, or numpy is unavailable')
            return

        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        hsv = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2HSV)
        lower = self.np.array([
            int(self.get_parameter('h_min').value),
            int(self.get_parameter('s_min').value),
            int(self.get_parameter('v_min').value),
        ])
        upper = self.np.array([
            int(self.get_parameter('h_max').value),
            int(self.get_parameter('s_max').value),
            int(self.get_parameter('v_max').value),
        ])
        mask = self.cv2.inRange(hsv, lower, upper)
        mask = self.cv2.morphologyEx(mask, self.cv2.MORPH_OPEN, self.np.ones((5, 5), self.np.uint8))
        contours, _ = self.cv2.findContours(mask, self.cv2.RETR_EXTERNAL, self.cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            self.detection_pub.publish(String(data=json.dumps({'detected': False})))
            return

        contour = max(contours, key=self.cv2.contourArea)
        area = float(self.cv2.contourArea(contour))
        if area < float(self.get_parameter('min_area').value):
            self.detection_pub.publish(String(data=json.dumps({'detected': False, 'area': area})))
            return

        moments = self.cv2.moments(contour)
        if moments['m00'] == 0:
            return
        height, width = frame.shape[:2]
        cx = moments['m10'] / moments['m00']
        cy = moments['m01'] / moments['m00']
        area_ratio = area / float(width * height)

        target = PointStamped()
        target.header = msg.header
        target.point.x = (cx - width / 2.0) / (width / 2.0)
        target.point.y = (cy - height / 2.0) / (height / 2.0)
        target.point.z = area_ratio
        self.target_pub.publish(target)
        self.detection_pub.publish(String(data=json.dumps({
            'detected': True,
            'center_x': cx,
            'center_y': cy,
            'area': area,
            'area_ratio': area_ratio,
        })))

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

    @staticmethod
    def _load_numpy():
        try:
            import numpy
            return numpy
        except ImportError:
            return None


def main(args: Optional[Sequence[str]] = None) -> None:
    rclpy.init(args=args)
    node = ColorDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
