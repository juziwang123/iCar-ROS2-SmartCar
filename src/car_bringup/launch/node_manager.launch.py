"""One-command real-car startup with a persistent node manager and APP bridge."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def _include(package: str, launch_file: str, arguments, condition=None):
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare(package), 'launch', launch_file])
        ),
        launch_arguments=arguments.items(),
        condition=condition,
    )


def generate_launch_description() -> LaunchDescription:
    use_vendor_base = LaunchConfiguration('use_vendor_base')
    use_control = LaunchConfiguration('use_control')
    use_camera = LaunchConfiguration('use_camera')
    use_app_bridge = LaunchConfiguration('use_app_bridge')
    return LaunchDescription([
        DeclareLaunchArgument('use_vendor_base', default_value='true'),
        DeclareLaunchArgument('rplidar_type', default_value='a1'),
        # The factory EKF is started by vendor_x3_base_no_joy.launch.py and
        # owns odom -> base_footprint.  Publishing the same transform from
        # base_node_X3 creates two TF authorities and makes scan transforms
        # intermittent, so preserve the factory launch default.
        DeclareLaunchArgument('pub_odom_tf', default_value='false'),
        DeclareLaunchArgument('use_robot_description', default_value='true'),
        DeclareLaunchArgument('use_control', default_value='true'),
        DeclareLaunchArgument('use_keyboard', default_value='false'),
        DeclareLaunchArgument('use_camera', default_value='true'),
        DeclareLaunchArgument('use_lidar_avoidance', default_value='true'),
        # The vendor's proven lidar following algorithm is safe to keep
        # running: it only reaches the base when safety_mux is explicitly in
        # ``follow`` mode.  Starting it here lets the APP enable native
        # following instantly, without requiring YOLO detections first.
        DeclareLaunchArgument('use_lidar_tracker', default_value='true'),
        DeclareLaunchArgument('use_lidar_warning', default_value='false'),
        DeclareLaunchArgument('use_app_bridge', default_value='true'),
        DeclareLaunchArgument('app_bridge_host', default_value='0.0.0.0'),
        DeclareLaunchArgument('app_bridge_port', default_value='8765'),
        DeclareLaunchArgument('initial_profile', default_value='idle'),
        DeclareLaunchArgument('map', default_value=''),
        DeclareLaunchArgument(
            'mission_route_file', default_value=PathJoinSubstitution([
                FindPackageShare('car_mission'), 'config', 'demo_route.yaml',
            ]),
        ),
        DeclareLaunchArgument('initial_use_yolo', default_value='false'),
        DeclareLaunchArgument('initial_yolo_active_model', default_value='person'),
        DeclareLaunchArgument(
            'control_params_file', default_value=PathJoinSubstitution([
                FindPackageShare('car_control'), 'config', 'control.yaml',
            ]),
        ),
        DeclareLaunchArgument(
            'lidar_params_file', default_value=PathJoinSubstitution([
                FindPackageShare('car_bringup'), 'config', 'lidar.yaml',
            ]),
        ),
        DeclareLaunchArgument(
            'vision_params_file', default_value=PathJoinSubstitution([
                FindPackageShare('car_vision'), 'config', 'vision.yaml',
            ]),
        ),
        DeclareLaunchArgument(
            'app_bridge_params_file', default_value=PathJoinSubstitution([
                FindPackageShare('car_app_bridge'), 'config', 'app_bridge.yaml',
            ]),
        ),
        DeclareLaunchArgument(
            'manager_params_file', default_value=PathJoinSubstitution([
                FindPackageShare('car_runtime_manager'), 'config', 'node_manager.yaml',
            ]),
        ),
        _include('car_bringup', 'vendor_x3_base_no_joy.launch.py', {
            'rplidar_type': LaunchConfiguration('rplidar_type'),
            'pub_odom_tf': LaunchConfiguration('pub_odom_tf'),
            'use_robot_description': LaunchConfiguration('use_robot_description'),
        }, IfCondition(use_vendor_base)),
        # The factory EKF can be quiet while the vehicle is stationary.  Keep
        # its latest pose available as dynamic TF so a newly started Nav2
        # costmap can always initialise its odom -> base_footprint buffer.
        Node(
            package='car_bringup', executable='odom_tf_keepalive',
            name='odom_tf_keepalive', output='screen',
        ),
        _include('car_control', 'control.launch.py', {
            'use_keyboard': LaunchConfiguration('use_keyboard'),
            'params_file': LaunchConfiguration('control_params_file'),
        }, IfCondition(use_control)),
        _include('car_lidar', 'lidar.launch.py', {
            'params_file': LaunchConfiguration('lidar_params_file'),
            'use_avoidance': LaunchConfiguration('use_lidar_avoidance'),
            'use_tracker': LaunchConfiguration('use_lidar_tracker'),
            'use_warning': LaunchConfiguration('use_lidar_warning'),
        }),
        Node(
            package='car_vision', executable='camera_bridge', name='camera_bridge',
            parameters=[LaunchConfiguration('vision_params_file')],
            condition=IfCondition(use_camera), output='screen',
        ),
        _include('car_app_bridge', 'app_bridge.launch.py', {
            'params_file': LaunchConfiguration('app_bridge_params_file'),
            'host': LaunchConfiguration('app_bridge_host'),
            'port': LaunchConfiguration('app_bridge_port'),
        }, IfCondition(use_app_bridge)),
        Node(
            package='car_runtime_manager', executable='node_manager', name='node_manager',
            parameters=[LaunchConfiguration('manager_params_file'), {
                'initial_profile': LaunchConfiguration('initial_profile'),
                'initial_map_path': LaunchConfiguration('map'),
                'initial_route_file': LaunchConfiguration('mission_route_file'),
                'initial_use_yolo': ParameterValue(
                    LaunchConfiguration('initial_use_yolo'), value_type=bool,
                ),
                'initial_yolo_active_model': LaunchConfiguration('initial_yolo_active_model'),
            }],
            output='screen',
        ),
    ])
