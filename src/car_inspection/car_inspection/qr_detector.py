"""Publish QR and, when OpenCV-contrib is available, AprilTag detections."""

from __future__ import annotations

from pathlib import Path
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
        # An empty path deliberately keeps the original OpenCV-only QR flow.
        # When a local model is configured, it first finds QR regions and the
        # QRCodeDetector decodes each cropped region.
        self.declare_parameter('qr_yolo_model_path', '')
        self.declare_parameter('qr_yolo_device', 'auto')
        self.declare_parameter('qr_yolo_confidence_threshold', 0.25)
        self.declare_parameter('qr_yolo_iou_threshold', 0.45)
        self.declare_parameter('qr_yolo_image_size', 640)
        self.declare_parameter('qr_yolo_max_detections', 10)
        self.declare_parameter('qr_yolo_labels', ['qrcode', 'qr_code', 'qr'])
        self.declare_parameter('qr_yolo_crop_padding_ratio', 0.10)

        self.cv2 = self._load_cv2()
        self.bridge = self._load_bridge()
        self.qr = self.cv2.QRCodeDetector() if self.cv2 is not None else None
        self.qr_yolo_model = None
        self.qr_yolo_model_file: Optional[Path] = None
        self.qr_yolo_unavailable_reason: Optional[str] = None
        self._load_qr_yolo_model()
        self.marker_publisher = self.create_publisher(
            String, str(self.get_parameter('marker_topic').value), 10
        )
        self.create_subscription(
            Image, str(self.get_parameter('image_topic').value), self._on_image, 10
        )
        if self.cv2 is None or self.bridge is None:
            self.get_logger().error('QR detector requires python3-opencv and cv_bridge')
        if self.qr_yolo_model is not None:
            self.get_logger().info(
                f'QR YOLO cropper started with {self.qr_yolo_model_file}'
            )
        elif str(self.get_parameter('qr_yolo_model_path').value).strip():
            self.get_logger().warn(
                'QR YOLO cropper is unavailable; using full-frame OpenCV QR decoding: '
                f'{self.qr_yolo_unavailable_reason}'
            )

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
        if self.qr_yolo_model is not None:
            return self._detect_qr_with_yolo_crops(frame)
        return self._decode_qr(frame)

    def _decode_qr(
        self, frame: Any, offset_x: int = 0, offset_y: int = 0
    ) -> List[MarkerDetection]:
        """Decode one image and translate crop-relative polygon coordinates."""
        try:
            if hasattr(self.qr, 'detectAndDecodeMulti'):
                result = self.qr.detectAndDecodeMulti(frame)
                if len(result) == 4 and bool(result[0]):
                    decoded, points = result[1], result[2]
                    return [
                        MarkerDetection(
                            'qr', str(marker_id),
                            _offset_polygon(point_set, offset_x, offset_y),
                        )
                        for marker_id, point_set in zip(decoded, points)
                        if isinstance(marker_id, str) and marker_id.strip()
                    ]
            decoded, points, _ = self.qr.detectAndDecode(frame)
            if isinstance(decoded, str) and decoded.strip() and points is not None:
                return [
                    MarkerDetection(
                        'qr', decoded, _offset_polygon(points, offset_x, offset_y)
                    )
                ]
        except Exception as exc:
            self.get_logger().debug(f'QR decoding failed for a frame: {exc}')
        return []

    def _detect_qr_with_yolo_crops(self, frame: Any) -> List[MarkerDetection]:
        """Run the local QR detector, then decode only its padded ROIs."""
        try:
            device = str(self.get_parameter('qr_yolo_device').value).strip().lower()
            kwargs = {
                'verbose': False,
                'conf': float(self.get_parameter('qr_yolo_confidence_threshold').value),
                'iou': float(self.get_parameter('qr_yolo_iou_threshold').value),
                'imgsz': int(self.get_parameter('qr_yolo_image_size').value),
                'max_det': int(self.get_parameter('qr_yolo_max_detections').value),
            }
            if device and device != 'auto':
                kwargs['device'] = device
            result = self.qr_yolo_model.predict(frame, **kwargs)[0]
            names = result.names
            allowed_labels = {
                str(value).strip().lower()
                for value in self.get_parameter('qr_yolo_labels').value
                if str(value).strip()
            }
            detections: List[MarkerDetection] = []
            decoded_ids = set()
            for box in result.boxes:
                class_id = int(box.cls.item())
                label = names[class_id] if isinstance(names, dict) else names[class_id]
                if allowed_labels and str(label).strip().lower() not in allowed_labels:
                    continue
                x_min, y_min, x_max, y_max = (
                    float(value) for value in box.xyxy[0].tolist()
                )
                crop_bounds = _padded_crop_bounds(
                    x_min, y_min, x_max, y_max,
                    frame.shape[1], frame.shape[0],
                    float(self.get_parameter('qr_yolo_crop_padding_ratio').value),
                )
                if crop_bounds is None:
                    continue
                left, top, right, bottom = crop_bounds
                crop = frame[top:bottom, left:right]
                for marker in self._decode_qr(crop, left, top):
                    # Overlapping YOLO boxes should not emit the same QR more
                    # than once for a source image.
                    if marker.marker_id not in decoded_ids:
                        decoded_ids.add(marker.marker_id)
                        detections.append(marker)
            return detections
        except Exception as exc:
            self.get_logger().warn(
                f'QR YOLO inference failed; using full-frame OpenCV decoding: {exc}'
            )
            return self._decode_qr(frame)

    def _load_qr_yolo_model(self) -> None:
        configured_path = str(self.get_parameter('qr_yolo_model_path').value).strip()
        if not configured_path:
            return
        model_file = self._resolve_model_path(configured_path)
        if model_file is None:
            self.qr_yolo_unavailable_reason = f'local model not found: {configured_path}'
            return
        try:
            from ultralytics import YOLO
        except ImportError:
            self.qr_yolo_unavailable_reason = (
                'ultralytics is not installed; install car_vision/requirements-vision.txt'
            )
            return
        try:
            self.qr_yolo_model = YOLO(str(model_file))
            self.qr_yolo_model_file = model_file
        except Exception as exc:
            self.qr_yolo_unavailable_reason = f'could not load {model_file}: {exc}'

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

                share_directory = Path(get_package_share_directory('car_inspection'))
                candidates.extend([
                    share_directory / requested,
                    share_directory / 'models' / requested,
                ])
            except (ImportError, ValueError):
                pass
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        return None

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


def _offset_polygon(points: Any, offset_x: int, offset_y: int) -> Tuple[Tuple[float, float], ...]:
    return tuple(
        (x + float(offset_x), y + float(offset_y))
        for x, y in _polygon(points)
    )


def _padded_crop_bounds(
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    image_width: int,
    image_height: int,
    padding_ratio: float,
) -> Optional[Tuple[int, int, int, int]]:
    """Clamp a padded YOLO box to an image and reject empty regions."""
    if x_max <= x_min or y_max <= y_min:
        return None
    padding = max(0.0, min(1.0, padding_ratio)) * max(x_max - x_min, y_max - y_min)
    left = max(0, int(x_min - padding))
    top = max(0, int(y_min - padding))
    right = min(image_width, int(x_max + padding + 0.999999))
    bottom = min(image_height, int(y_max + padding + 0.999999))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


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
