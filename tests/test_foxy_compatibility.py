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
        self.assertIn('PYTHONUNBUFFERED=1 ros2 topic echo', script)
        self.assertIn('--qos-durability "${durability}"', script)
        self.assertIn('check_topic /map "${LOG_DIR}/smoke_mapping.log"', script)
        self.assertIn('check_topic /map "${LOG_DIR}/smoke_navigation.log"', script)
        self.assertIn('check_topic_message /cmd_vel "${LOG_DIR}/smoke_control_lidar.log"', script)
        self.assertIn('SMOKE_MODULES="${SMOKE_MODULES:-all}"', script)
        self.assertIn('SMOKE_SKIP_MODULES="${SMOKE_SKIP_MODULES:-}"', script)
        self.assertIn('HARDWARE_TOPIC_TIMEOUT="${HARDWARE_TOPIC_TIMEOUT:-25}"', script)
        self.assertIn('HARDWARE_START_ATTEMPTS="${HARDWARE_START_ATTEMPTS:-2}"', script)
        self.assertIn('GRAPH_DISCOVERY_SPIN_TIME="${GRAPH_DISCOVERY_SPIN_TIME:-5}"', script)
        self.assertIn('SERVICE_TIMEOUT="${SERVICE_TIMEOUT:-30}"', script)
        self.assertIn('LIFECYCLE_TIMEOUT="${LIFECYCLE_TIMEOUT:-30}"', script)
        self.assertIn('run_module mapping run_mapping_module', script)
        self.assertIn('run_module navigation run_navigation_module', script)
        self.assertIn('prepare_base_stack || return 1', script)
        self.assertIn('prepare_camera || return 1', script)
        self.assertIn('厂家底盘尚未产生完整传感器数据，重启后重试', script)
        self.assertIn('registration is the stable, end-to-end readiness contract', script)

    def test_real_car_keeps_the_odom_transform_enabled(self):
        common = (ROOT / 'scripts/common_real_car.sh').read_text(encoding='utf-8')
        self.assertIn('VENDOR_PUB_ODOM_TF:-true', common)
        self.assertIn('ICAR_VENDOR_LIBRARY_SETUP', common)
        self.assertIn('ICAR_VENDOR_WORKSPACE_SETUP', common)
        self.assertIn('enable_color:=false', common)

    def test_map_saver_lifecycle_manager_starts_after_server_registration(self):
        mapping_launch = (ROOT / 'src/car_navigation/launch/mapping.launch.py').read_text(encoding='utf-8')
        self.assertIn('TimerAction(', mapping_launch)
        self.assertIn('period=1.0', mapping_launch)

    def test_lidar_warning_publishes_a_startup_state_heartbeat(self):
        warning = (ROOT / 'src/car_lidar/car_lidar/warning.py').read_text(encoding='utf-8')
        self.assertIn("self.warning_state = 'unknown'", warning)
        self.assertIn('state_publish_rate_hz', warning)

    def test_vision_launch_uses_the_v4l2_colour_bridge(self):
        bridge = (ROOT / 'src/car_vision/car_vision/camera_bridge.py').read_text(encoding='utf-8')
        setup = (ROOT / 'src/car_vision/setup.py').read_text(encoding='utf-8')
        launch = (ROOT / 'src/car_vision/launch/vision.launch.py').read_text(encoding='utf-8')
        bringup = (ROOT / 'src/car_bringup/launch/bringup.launch.py').read_text(encoding='utf-8')
        script = (ROOT / 'scripts/run_full_system_smoke_test.sh').read_text(encoding='utf-8')
        self.assertIn("self.declare_parameter('video_device', '0')", bridge)
        self.assertIn('self.cv2.VideoCapture(source)', bridge)
        self.assertIn("'MJPG'", bridge)
        self.assertIn("'/camera/color/image_raw'", bridge)
        self.assertIn('camera_bridge = car_vision.camera_bridge:main', setup)
        self.assertIn("DeclareLaunchArgument('use_camera_bridge', default_value='true')", launch)
        self.assertIn("DeclareLaunchArgument('vision_use_camera_bridge', default_value='true')", bringup)
        self.assertIn('START_V4L2_BRIDGE=1 start_vendor_camera', script)


if __name__ == '__main__':
    unittest.main()
