"""Publish the Astra UVC colour stream as a standard ROS image topic."""

from __future__ import annotations

import time
from typing import Optional, Sequence, Union

import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


class CameraBridge(Node):
    """Bridge the camera's V4L2 colour device to ``/camera/color/image_raw``."""

    def __init__(self) -> None:
        super().__init__('camera_bridge')
        self.declare_parameter('video_device', '/dev/video0')
        self.declare_parameter('image_topic', '/camera/color/image_raw')
        self.declare_parameter('frame_id', 'camera_color_frame')
        self.declare_parameter('width', 640)
        self.declare_parameter('height', 480)
        self.declare_parameter('fps', 30.0)
        self.declare_parameter('pixel_format', 'MJPG')
        self.declare_parameter('reopen_interval_sec', 2.0)

        self.cv2 = self._load_cv2()
        self.bridge = CvBridge()
        self.capture = None
        self.last_open_attempt = 0.0
        self.publisher = self.create_publisher(
            Image,
            str(self.get_parameter('image_topic').value),
            qos_profile_sensor_data,
        )
        fps = max(1.0, float(self.get_parameter('fps').value))
        self.create_timer(1.0 / fps, self._publish_frame)
        self._open_capture()

    @staticmethod
    def _load_cv2():
        try:
            import cv2
            return cv2
        except ImportError:
            return None

    def _open_capture(self) -> bool:
        self.last_open_attempt = time.monotonic()
        if self.cv2 is None:
            self.get_logger().error('OpenCV is unavailable; V4L2 camera bridge cannot start')
            return False

        self._release_capture()
        device = str(self.get_parameter('video_device').value)
        source: Union[int, str] = int(device) if device.isdigit() else device
        capture = self.cv2.VideoCapture(source, self.cv2.CAP_V4L2)
        if not capture.isOpened():
            capture.release()
            self.get_logger().warn(f'Cannot open V4L2 colour device {device}; will retry')
            return False

        pixel_format = str(self.get_parameter('pixel_format').value).upper()
        if len(pixel_format) == 4:
            capture.set(
                self.cv2.CAP_PROP_FOURCC,
                self.cv2.VideoWriter_fourcc(*pixel_format),
            )
        capture.set(self.cv2.CAP_PROP_FRAME_WIDTH, int(self.get_parameter('width').value))
        capture.set(self.cv2.CAP_PROP_FRAME_HEIGHT, int(self.get_parameter('height').value))
        capture.set(self.cv2.CAP_PROP_FPS, float(self.get_parameter('fps').value))
        self.capture = capture
        self.get_logger().info(f'Publishing V4L2 colour stream from {device}')
        return True

    def _publish_frame(self) -> None:
        if self.capture is None:
            retry_after = float(self.get_parameter('reopen_interval_sec').value)
            if time.monotonic() - self.last_open_attempt >= max(0.1, retry_after):
                self._open_capture()
            return

        success, frame = self.capture.read()
        if not success or frame is None:
            self.get_logger().warn('V4L2 colour frame read failed; reopening device')
            self._release_capture()
            return

        message = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = str(self.get_parameter('frame_id').value)
        self.publisher.publish(message)

    def _release_capture(self) -> None:
        if self.capture is not None:
            self.capture.release()
            self.capture = None

    def destroy_node(self) -> bool:
        self._release_capture()
        return super().destroy_node()


def main(args: Optional[Sequence[str]] = None) -> None:
    rclpy.init(args=args)
    node = CameraBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

