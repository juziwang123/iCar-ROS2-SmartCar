from pathlib import Path
import sys
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / 'src' / 'car_bringup'
sys.path.insert(0, str(PACKAGE_ROOT))

from car_bringup.cli_core import (
    CliError, build_launch_profile, finite_motion, parse_console_command, validate_mode,
)


class TestBringupCliCore(unittest.TestCase):
    def test_mission_profile_uses_compatible_bringup_arguments(self):
        profile = build_launch_profile(
            'mission', map_file='/maps/lab.yaml', route_file='/routes/night.yaml',
            use_app_bridge=True, use_yolo=True,
        )
        self.assertEqual(profile.arguments['use_navigation'], 'true')
        self.assertEqual(profile.arguments['use_mission'], 'true')
        self.assertEqual(profile.arguments['use_inspection'], 'true')
        self.assertEqual(profile.arguments['mission_require_localization'], 'true')
        self.assertEqual(profile.arguments['mission_route_file'], '/routes/night.yaml')
        self.assertEqual(profile.arguments['use_app_bridge'], 'true')

    def test_route_is_rejected_for_non_mission_profile(self):
        with self.assertRaises(CliError):
            build_launch_profile('navigation', route_file='/routes/night.yaml')

    def test_console_parser_is_a_whitelist_not_a_shell(self):
        self.assertEqual(parse_console_command('start demo_route 2 1'), ('start', ('demo_route', '2', '1')))
        with self.assertRaises(CliError):
            parse_console_command('shell rm -rf /')

    def test_mode_and_motion_are_bounded_before_ros_publish(self):
        self.assertEqual(validate_mode(' NAV '), 'nav')
        self.assertEqual(finite_motion('0.2', 'linear', 0.4), 0.2)
        with self.assertRaises(CliError):
            finite_motion('1.0', 'linear', 0.4)


if __name__ == '__main__':
    unittest.main()
