"""Unit tests for the optional YOLO-to-OpenCV QR crop path."""

from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT / 'car_inspection'))


def _install_ros_stubs() -> None:
    """Make the detector's image-independent helpers testable without ROS."""
    rclpy = types.ModuleType('rclpy')
    rclpy.init = lambda *args, **kwargs: None
    rclpy.spin = lambda *args, **kwargs: None
    node = types.ModuleType('rclpy.node')
    node.Node = object
    sensor_msgs = types.ModuleType('sensor_msgs')
    sensor_msgs_msg = types.ModuleType('sensor_msgs.msg')
    sensor_msgs_msg.Image = object
    std_msgs = types.ModuleType('std_msgs')
    std_msgs_msg = types.ModuleType('std_msgs.msg')
    std_msgs_msg.String = object
    sys.modules.update({
        'rclpy': rclpy,
        'rclpy.node': node,
        'sensor_msgs': sensor_msgs,
        'sensor_msgs.msg': sensor_msgs_msg,
        'std_msgs': std_msgs,
        'std_msgs.msg': std_msgs_msg,
    })


_install_ros_stubs()
from car_inspection.marker_protocol import MarkerDetection
from car_inspection.qr_detector import QrDetector, _padded_crop_bounds


class _Parameter:
    def __init__(self, value):
        self.value = value


class _Box:
    def __init__(self, class_id, bounds):
        self.cls = type('Value', (), {'item': lambda self: class_id})()
        self.xyxy = [type('Coordinates', (), {'tolist': lambda self: bounds})()]


class _Frame:
    shape = (80, 100, 3)

    def __getitem__(self, key):
        y_slice, x_slice = key[:2]
        return type('Crop', (), {
            'shape': (
                y_slice.stop - y_slice.start,
                x_slice.stop - x_slice.start,
                3,
            ),
        })()


class TestQrYoloCrop(unittest.TestCase):
    def test_crop_bounds_are_padded_and_clamped_to_image(self):
        self.assertEqual(
            _padded_crop_bounds(-5.0, 10.0, 30.0, 40.0, 100, 80, 0.1),
            (0, 6, 34, 44),
        )
        self.assertIsNone(_padded_crop_bounds(10, 10, 10, 20, 100, 80, 0.1))

    def test_yolo_regions_are_cropped_then_decoded_with_image_offsets(self):
        detector = object.__new__(QrDetector)
        parameters = {
            'qr_yolo_device': 'auto',
            'qr_yolo_confidence_threshold': 0.25,
            'qr_yolo_iou_threshold': 0.45,
            'qr_yolo_image_size': 640,
            'qr_yolo_max_detections': 10,
            'qr_yolo_labels': ['qrcode'],
            'qr_yolo_crop_padding_ratio': 0.0,
        }
        detector.get_parameter = lambda name: _Parameter(parameters[name])
        detector.get_logger = lambda: type('Logger', (), {'warn': lambda *args: None})()
        detector.qr_yolo_model = type('Model', (), {
            'predict': lambda self, frame, **kwargs: [type('Result', (), {
                'names': {0: 'qrcode'},
                'boxes': [_Box(0, [10.0, 20.0, 30.0, 50.0])],
            })()],
        })()
        calls = []

        def decode(crop, offset_x, offset_y):
            calls.append((crop.shape, offset_x, offset_y))
            return [MarkerDetection('qr', 'CP-01', ((11.0, 21.0),))]

        detector._decode_qr = decode
        markers = detector._detect_qr_with_yolo_crops(_Frame())

        self.assertEqual(calls, [((30, 20, 3), 10, 20)])
        self.assertEqual([marker.marker_id for marker in markers], ['CP-01'])


if __name__ == '__main__':
    unittest.main()
