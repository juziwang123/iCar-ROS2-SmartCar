from pathlib import Path
import sys
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / 'src' / 'car_control'
sys.path.insert(0, str(PACKAGE_ROOT))

from car_control.safety_policy import effective_estop, is_supported_mode, normalize_mode


class TestSafetyPolicy(unittest.TestCase):
    def test_mode_normalization_is_case_and_whitespace_insensitive(self):
        self.assertEqual(normalize_mode(' Nav '), 'nav')
        self.assertTrue(is_supported_mode('VISION'))

    def test_unsupported_mode_is_rejected(self):
        for value in ('', 'patrol', 'mapping', None):
            self.assertFalse(is_supported_mode(value))

    def test_operator_estop_stays_effective_until_explicitly_cleared(self):
        self.assertTrue(effective_estop(operator_latched=True, person_active=False))
        self.assertFalse(effective_estop(operator_latched=False, person_active=False))

    def test_person_estop_stops_even_when_operator_estop_is_clear(self):
        self.assertTrue(effective_estop(operator_latched=False, person_active=True))


if __name__ == '__main__':
    unittest.main()
