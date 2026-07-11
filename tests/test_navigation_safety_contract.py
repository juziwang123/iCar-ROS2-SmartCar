from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestNavigationSafetyContract(unittest.TestCase):
    def test_nav2_is_remapped_to_the_mux_input(self):
        launch_file = REPO_ROOT / 'src' / 'car_navigation' / 'launch' / 'navigation.launch.py'
        source = launch_file.read_text(encoding='utf-8')
        self.assertIn("SetRemap(src='/cmd_vel', dst='/cmd_vel_nav')", source)
        self.assertIn('GroupAction(', source)

    def test_only_motion_controller_targets_the_final_cmd_vel_topic(self):
        control_root = REPO_ROOT / 'src' / 'car_control' / 'car_control'
        final_publishers = []
        for source_file in control_root.glob('*.py'):
            source = source_file.read_text(encoding='utf-8')
            if "output_topic', '/cmd_vel'" in source:
                final_publishers.append(source_file.name)
        self.assertEqual(final_publishers, ['motion_controller.py'])

    def test_keyboard_teleop_rejects_the_final_cmd_vel_topic(self):
        keyboard_file = REPO_ROOT / 'src' / 'car_control' / 'car_control' / 'keyboard_teleop.py'
        source = keyboard_file.read_text(encoding='utf-8')
        self.assertIn("if publish_topic == '/cmd_vel':", source)
        self.assertIn("publish_topic = '/cmd_vel_manual'", source)


if __name__ == '__main__':
    unittest.main()
