from pathlib import Path
import sys
import tempfile
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / 'src' / 'car_runtime_manager'
sys.path.insert(0, str(PACKAGE_ROOT))

from car_runtime_manager.runtime_core import (
    RuntimeProfileError,
    RuntimeProfileRequest,
    profile_launch_arguments,
    validate_runtime_files,
)


class TestRuntimeProfileCore(unittest.TestCase):
    def test_navigation_is_whitelisted_and_requires_an_absolute_map(self):
        with tempfile.TemporaryDirectory() as directory:
            map_path = Path(directory) / 'map.yaml'
            map_path.write_text('image: map.pgm\n', encoding='utf-8')
            request = validate_runtime_files(RuntimeProfileRequest(' Navigation ', str(map_path)))
            self.assertEqual(request.profile, 'navigation')
            self.assertEqual(profile_launch_arguments(request), {
                'profile': 'navigation',
                'map': str(map_path.resolve()),
                'use_yolo': 'false',
            })
        with self.assertRaises(RuntimeProfileError):
            RuntimeProfileRequest('navigation', 'maps/lab.yaml').normalized()

    def test_mission_requires_map_and_route_files_before_launching(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            map_path = root / 'map.yaml'
            route_path = root / 'route.yaml'
            map_path.write_text('image: map.pgm\n', encoding='utf-8')
            route_path.write_text('routes: []\n', encoding='utf-8')
            request = validate_runtime_files(
                RuntimeProfileRequest('mission', str(map_path), str(route_path), True)
            )
            arguments = profile_launch_arguments(request)
            self.assertEqual(arguments['profile'], 'mission')
            self.assertEqual(arguments['mission_route_file'], str(route_path.resolve()))
            self.assertEqual(arguments['use_yolo'], 'true')
            self.assertEqual(arguments['vision_yolo_active_model'], 'person')
        with self.assertRaises(RuntimeProfileError):
            RuntimeProfileRequest('mission', '/tmp/map.yaml').normalized()

    def test_idle_rejects_stale_profile_arguments(self):
        with self.assertRaises(RuntimeProfileError):
            RuntimeProfileRequest('idle', '/tmp/map.yaml').normalized()
        with self.assertRaises(RuntimeProfileError):
            RuntimeProfileRequest('mapping', use_yolo=True).normalized()
        self.assertEqual(profile_launch_arguments(RuntimeProfileRequest('idle')), {})

    def test_missing_files_are_rejected_before_starting_ros_launch(self):
        with self.assertRaises(RuntimeProfileError):
            validate_runtime_files(RuntimeProfileRequest('navigation', '/tmp/missing-map.yaml'))

    def test_mission_accepts_only_safe_registered_yolo_model_names(self):
        map_path = str((Path.cwd() / 'map.yaml').resolve())
        route_path = str((Path.cwd() / 'route.yaml').resolve())
        request = RuntimeProfileRequest(
            'mission', map_path, route_path, True, 'inspection'
        ).normalized()
        self.assertEqual(request.yolo_active_model, 'inspection')
        with self.assertRaises(RuntimeProfileError):
            RuntimeProfileRequest(
                'mission', map_path, route_path, True, 'inspection;bad'
            ).normalized()

    def test_mission_passes_multiple_registered_models_as_a_launch_argument(self):
        request = RuntimeProfileRequest(
            'mission',
            str((Path.cwd() / 'map.yaml').resolve()),
            str((Path.cwd() / 'route.yaml').resolve()),
            True,
            'person',
            ('person', 'inspection'),
        )
        arguments = profile_launch_arguments(request)
        self.assertEqual(arguments['vision_yolo_active_models'], 'person,inspection')


if __name__ == '__main__':
    unittest.main()
