from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TestFoxyCompatibility(unittest.TestCase):
    def test_map_saver_timeout_is_passed_as_an_integer(self):
        mapping_launch = (ROOT / 'src/car_navigation/launch/mapping.launch.py').read_text(encoding='utf-8')
        bringup_launch = (ROOT / 'src/car_bringup/launch/bringup.launch.py').read_text(encoding='utf-8')
        self.assertIn("DeclareLaunchArgument('map_save_timeout_sec', default_value='10')", mapping_launch)
        self.assertIn("ParameterValue(map_save_timeout_sec, value_type=int)", mapping_launch)
        self.assertIn("DeclareLaunchArgument('mapping_map_save_timeout_sec', default_value='10')", bringup_launch)

    def test_bt_plugin_list_excludes_missing_change_goal_library(self):
        params = (ROOT / 'src/car_navigation/config/nav2_params.yaml').read_text(encoding='utf-8')
        self.assertIn('plugin_lib_names:', params)
        self.assertIn('nav2_compute_path_to_pose_action_bt_node', params)
        self.assertNotIn('      - nav2_change_goal_node_bt_node', params)

    def test_smoke_test_uses_foxy_compatible_topic_capture(self):
        script = (ROOT / 'scripts/run_full_system_smoke_test.sh').read_text(encoding='utf-8')
        self.assertIn('capture_topic_message()', script)
        self.assertNotIn('topic echo --once', script)


if __name__ == '__main__':
    unittest.main()
