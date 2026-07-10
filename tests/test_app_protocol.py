from pathlib import Path
import sys
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / 'src' / 'car_app_bridge'
sys.path.insert(0, str(PACKAGE_ROOT))

from car_app_bridge.protocol import ProtocolError, boolean, finite_number, response, string_list


class TestAppProtocol(unittest.TestCase):
    def test_response_has_a_stable_envelope(self):
        self.assertEqual(response(True, 'move', request_id='42', data={'linear': 0.2}), {
            'type': 'response',
            'ok': True,
            'cmd': 'move',
            'id': '42',
            'data': {'linear': 0.2},
        })

    def test_boolean_does_not_treat_false_string_as_truthy(self):
        self.assertTrue(boolean('true'))
        self.assertFalse(boolean('off'))
        self.assertTrue(boolean(1))
        self.assertFalse(boolean(0))

    def test_boolean_rejects_ambiguous_values(self):
        for value in ('false-ish', 2, None):
            with self.assertRaises(ProtocolError):
                boolean(value)

    def test_finite_number_enforces_speed_limits(self):
        self.assertEqual(finite_number('0.4', 'linear', limit=0.4), 0.4)
        with self.assertRaises(ProtocolError):
            finite_number(float('nan'), 'linear', limit=0.4)
        with self.assertRaises(ProtocolError):
            finite_number(0.41, 'linear', limit=0.4)

    def test_string_list_requires_string_items(self):
        self.assertEqual(string_list(['status', 'lidar'], 'channels'), ['status', 'lidar'])
        with self.assertRaises(ProtocolError):
            string_list('status', 'channels')
        with self.assertRaises(ProtocolError):
            string_list(['status', 1], 'channels')


if __name__ == '__main__':
    unittest.main()
