"""Unit tests for selecting and executing registered YOLO model profiles."""

from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT / 'car_vision'))


def _install_ros_stubs() -> None:
    rclpy = types.ModuleType('rclpy')
    rclpy.init = lambda *args, **kwargs: None
    rclpy.spin = lambda *args, **kwargs: None
    node = types.ModuleType('rclpy.node')
    node.Node = object
    qos = types.ModuleType('rclpy.qos')
    qos.DurabilityPolicy = type('DurabilityPolicy', (), {'TRANSIENT_LOCAL': object()})
    qos.ReliabilityPolicy = type('ReliabilityPolicy', (), {'RELIABLE': object()})
    qos.QoSProfile = type('QoSProfile', (), {'__init__': lambda self, **kwargs: None})
    qos.qos_profile_sensor_data = object()
    geometry_msgs = types.ModuleType('geometry_msgs')
    geometry_msgs_msg = types.ModuleType('geometry_msgs.msg')
    geometry_msgs_msg.Twist = object
    sensor_msgs = types.ModuleType('sensor_msgs')
    sensor_msgs_msg = types.ModuleType('sensor_msgs.msg')
    sensor_msgs_msg.Image = object
    std_msgs = types.ModuleType('std_msgs')
    std_msgs_msg = types.ModuleType('std_msgs.msg')
    std_msgs_msg.Bool = object
    std_msgs_msg.String = object
    sys.modules.update({
        'rclpy': rclpy,
        'rclpy.node': node,
        'rclpy.qos': qos,
        'geometry_msgs': geometry_msgs,
        'geometry_msgs.msg': geometry_msgs_msg,
        'sensor_msgs': sensor_msgs,
        'sensor_msgs.msg': sensor_msgs_msg,
        'std_msgs': std_msgs,
        'std_msgs.msg': std_msgs_msg,
    })


_install_ros_stubs()
from car_vision.yolo_detector import LoadedYoloModel, YoloDetector


class _Parameter:
    def __init__(self, value):
        self.value = value


class _Value:
    def __init__(self, value):
        self.value = value

    def item(self):
        return self.value


class _Box:
    def __init__(self, track_id=None):
        self.cls = _Value(0)
        self.xyxy = [type('Coordinates', (), {'tolist': lambda self: [1, 2, 11, 22]})()]
        self.conf = _Value(0.9)
        self.id = _Value(track_id) if track_id is not None else None


class _Model:
    def __init__(self, box):
        self.box = box
        self.calls = []

    def track(self, frame, **kwargs):
        self.calls.append(('track', kwargs))
        return [type('Result', (), {'names': {0: 'person'}, 'boxes': [self.box]})()]

    def predict(self, frame, **kwargs):
        self.calls.append(('predict', kwargs))
        return [type('Result', (), {'names': {0: 'fire_extinguisher'}, 'boxes': [self.box]})()]


class TestYoloModelRegistry(unittest.TestCase):
    def test_active_models_take_precedence_and_are_deduplicated(self):
        detector = object.__new__(YoloDetector)
        detector.get_parameter = lambda name: _Parameter({
            'active_models_csv': '',
            'active_models': ['person', 'inspection', 'person'],
            'active_model': 'legacy',
        }[name])
        self.assertEqual(detector._active_model_names(), ['person', 'inspection'])

    def test_launch_csv_models_take_precedence_over_parameter_file_list(self):
        detector = object.__new__(YoloDetector)
        detector.get_parameter = lambda name: _Parameter({
            'active_models_csv': 'inspection, person,inspection',
            'active_models': ['person'],
            'active_model': 'legacy',
        }[name])
        self.assertEqual(detector._active_model_names(), ['inspection', 'person'])

    def test_registered_models_use_their_respective_inference_modes(self):
        detector = object.__new__(YoloDetector)
        person = _Model(_Box(track_id=7))
        inspection = _Model(_Box())
        detector.models = {
            'person': LoadedYoloModel(
                'person', person, Path('person.pt'), 'track', 'auto', 0.4, 0.5, 640, 10
            ),
            'inspection': LoadedYoloModel(
                'inspection', inspection, Path('inspection.pt'), 'predict', 'cpu', 0.6, 0.4, 512, 5
            ),
        }

        detections = detector._infer(object())

        self.assertEqual([item['model'] for item in detections], ['person', 'inspection'])
        self.assertEqual(detections[0]['track_id'], 7)
        self.assertIsNone(detections[1]['track_id'])
        self.assertEqual(person.calls[0][0], 'track')
        self.assertTrue(person.calls[0][1]['persist'])
        self.assertEqual(inspection.calls[0][0], 'predict')
        self.assertNotIn('persist', inspection.calls[0][1])
        self.assertEqual(inspection.calls[0][1]['device'], 'cpu')

    def test_following_uses_the_first_tracking_model_to_avoid_id_collisions(self):
        detector = object.__new__(YoloDetector)
        detector.models = {
            'person': LoadedYoloModel(
                'person', object(), Path('person.pt'), 'track', 'auto', 0.4, 0.5, 640, 10
            ),
            'secondary': LoadedYoloModel(
                'secondary', object(), Path('secondary.pt'), 'track', 'auto', 0.4, 0.5, 640, 10
            ),
        }
        self.assertTrue(detector._tracking_model_accepts('person'))
        self.assertFalse(detector._tracking_model_accepts('secondary'))

    def test_follow_reacquire_overlap_metric(self):
        self.assertAlmostEqual(
            YoloDetector._box_iou(
                {'x_min': 0, 'y_min': 0, 'x_max': 10, 'y_max': 10},
                {'x_min': 5, 'y_min': 0, 'x_max': 15, 'y_max': 10},
            ),
            1.0 / 3.0,
        )
        self.assertEqual(
            YoloDetector._box_iou(
                {'x_min': 0, 'y_min': 0, 'x_max': 1, 'y_max': 1},
                {'x_min': 2, 'y_min': 2, 'x_max': 3, 'y_max': 3},
            ),
            0.0,
        )

    def test_capabilities_include_labels_from_each_loaded_model(self):
        detector = object.__new__(YoloDetector)
        detector.models = {
            'person': LoadedYoloModel(
                'person', type('Model', (), {'names': {0: 'person', 1: 'bottle'}})(),
                Path('person.pt'), 'track', 'auto', 0.4, 0.5, 640, 10,
            ),
        }
        detector.unavailable_reason = None
        self.assertEqual(detector._capabilities_payload(), {
            'models': [{
                'name': 'person', 'file': 'person.pt', 'loaded': True, 'active': True,
                'inference_mode': 'track', 'labels': ['person', 'bottle'],
            }],
            'active_models': ['person'],
        })


if __name__ == '__main__':
    unittest.main()
