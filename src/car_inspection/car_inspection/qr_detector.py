"""Publish QR and, when OpenCV-contrib is available, AprilTag detections."""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

from .marker_protocol import MarkerDetection, encode_markers


class QrDetector(Node):
    def __init__(self) -> None:
        super().__init__('qr_detector')
        self.declare_parameter('image_topic', '/camera/color/image_raw')
        self.declare_parameter('marker_topic', '/inspection/marker_detections')
        self.declare_parameter('detect_qr', True)
        self.declare_parameter('detect_apriltag', True)

        self.cv2 = self._load_cv2()
        self.bridge = self._load_bridge()
        self.qr = self.cv2.QRCodeDetector() if self.cv2 is not None else None
        self.marker_publisher = self.create_publisher(
            String, str(self.get_parameter('marker_topic').value), 10
        )
        self.create_subscription(
            Image, str(self.get_parameter('image_topic').value), self._on_image, 10
        )
        if self.cv2 is None or self.bridge is None:
            self.get_logger().error('QR detector requires python3-opencv and cv_bridge')

    def _on_image(self, msg: Image) -> None:
        if self.cv2 is None or self.bridge is None:
            return
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as exc:
            self.get_logger().warn(f'Could not convert image for marker detection: {exc}')
            return
        markers: List[MarkerDetection] = []
        if bool(self.get_parameter('detect_qr').value):
            markers.extend(self._detect_qr(frame))
        if bool(self.get_parameter('detect_apriltag').value):
            markers.extend(self._detect_apriltag(frame))
        # Publish empty frames too: the verifier uses each detector frame to
        # prove that confirmations were consecutive rather than repeated
        # copies of the last successful detection.
        self.marker_publisher.publish(String(data=encode_markers(
            markers,
            stamp_sec=msg.header.stamp.sec,
            stamp_nanosec=msg.header.stamp.nanosec,
            frame_id=msg.header.frame_id,
        )))

    def _detect_qr(self, frame: Any) -> List[MarkerDetection]:
        if self.qr is None:
            return []
        try:
            if hasattr(self.qr, 'detectAndDecodeMulti'):
                result = self.qr.detectAndDecodeMulti(frame)
                if len(result) == 4 and bool(result[0]):
                    decoded, points = result[1], result[2]
                    return [
                        MarkerDetection('qr', str(marker_id), _polygon(point_set))
                        for marker_id, point_set in zip(decoded, points)
                        if isinstance(marker_id, str) and marker_id.strip()
                    ]
            decoded, points, _ = self.qr.detectAndDecode(frame)
            if isinstance(decoded, str) and decoded.strip() and points is not None:
                return [MarkerDetection('qr', decoded, _polygon(points))]
        except Exception as exc:
            self.get_logger().debug(f'QR decoding failed for a frame: {exc}')
        return []

    def _detect_apriltag(self, frame: Any) -> List[MarkerDetection]:
        aruco = getattr(self.cv2, 'aruco', None) if self.cv2 is not None else None
        dictionary_id = getattr(aruco, 'DICT_APRILTAG_36h11', None) if aruco is not None else None
        if aruco is None or dictionary_id is None:
            return []
        try:
            dictionary_factory = getattr(aruco, 'getPredefinedDictionary', None)
            if dictionary_factory is None:
                dictionary_factory = aruco.Dictionary_get
            dictionary = dictionary_factory(dictionary_id)
            if hasattr(aruco, 'DetectorParameters'):
                parameters = aruco.DetectorParameters()
            else:
                parameters = aruco.DetectorParameters_create()
            if hasattr(aruco, 'ArucoDetector'):
                corners, ids, _ = aruco.ArucoDetector(dictionary, parameters).detectMarkers(frame)
            else:
                corners, ids, _ = aruco.detectMarkers(frame, dictionary, parameters=parameters)
            if ids is None:
                return []
            return [
                MarkerDetection('apriltag', str(int(marker_id)), _polygon(corner))
                for marker_id, corner in zip(ids.flatten(), corners)
            ]
        except Exception as exc:
            self.get_logger().debug(f'AprilTag detection failed for a frame: {exc}')
            return []

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


def _polygon(points: Any) -> Tuple[Tuple[float, float], ...]:
    """Normalize OpenCV's 1x4x2 and 4x2 corner arrays."""
    try:
        flattened = points.reshape((-1, 2))
        return tuple((float(point[0]), float(point[1])) for point in flattened)
    except Exception:
        return ()


def main(args: Optional[Sequence[str]] = None) -> None:
    rclpy.init(args=args)
    node = QrDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
