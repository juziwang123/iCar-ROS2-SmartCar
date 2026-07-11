from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def _launch_boolean(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    raise RuntimeError(f'Launch argument {name} must be a boolean, got {value!r}')


def _validate_operation_mode(context, *args, **kwargs):
    """Reject combinations that start incompatible map/navigation systems."""
    modes = {
        'mapping': _launch_boolean(LaunchConfiguration('use_mapping').perform(context), 'use_mapping'),
        'navigation': _launch_boolean(
            LaunchConfiguration('use_navigation').perform(context), 'use_navigation'
        ),
        # Patrol includes navigation.launch.py itself, therefore it is a
        # separate top-level mode instead of an add-on to use_navigation.
        'patrol': _launch_boolean(LaunchConfiguration('use_patrol').perform(context), 'use_patrol'),
        # Mission manager needs Nav2 but must not run alongside the legacy
        # waypoint patrol, which would submit a second route independently.
        'mission': _launch_boolean(LaunchConfiguration('use_mission').perform(context), 'use_mission'),
    }
    if modes['mapping'] and any(modes[name] for name in ('navigation', 'patrol', 'mission')):
        raise RuntimeError(
            'use_mapping cannot be combined with use_navigation, use_patrol, or use_mission'
        )
    if modes['patrol'] and (modes['navigation'] or modes['mission']):
        raise RuntimeError('use_patrol cannot be combined with use_navigation or use_mission')
    if modes['mission'] and not modes['navigation']:
        raise RuntimeError('use_mission:=true requires use_navigation:=true')
    return []


def generate_launch_description() -> LaunchDescription:
    use_keyboard = LaunchConfiguration('use_keyboard')
    use_lidar_avoidance = LaunchConfiguration('use_lidar_avoidance')
    use_lidar_tracker = LaunchConfiguration('use_lidar_tracker')
    use_lidar_warning = LaunchConfiguration('use_lidar_warning')
    use_vision = LaunchConfiguration('use_vision')
    use_color_detector = LaunchConfiguration('use_color_detector')
    use_color_tracker = LaunchConfiguration('use_color_tracker')
    use_yolo = LaunchConfiguration('use_yolo')
    vision_yolo_model_path = LaunchConfiguration('vision_yolo_model_path')
    vision_yolo_device = LaunchConfiguration('vision_yolo_device')
    use_app_bridge = LaunchConfiguration('use_app_bridge')
    app_bridge_host = LaunchConfiguration('app_bridge_host')
    app_bridge_port = LaunchConfiguration('app_bridge_port')
    use_mapping = LaunchConfiguration('use_mapping')
    mapping_use_rviz = LaunchConfiguration('mapping_use_rviz')
    mapping_scan_topic = LaunchConfiguration('mapping_scan_topic')
    mapping_use_scan_filter = LaunchConfiguration('mapping_use_scan_filter')
    mapping_scan_filter_multiple = LaunchConfiguration('mapping_scan_filter_multiple')
    mapping_publish_laser_tf = LaunchConfiguration('mapping_publish_laser_tf')
    mapping_publish_base_link_tf = LaunchConfiguration('mapping_publish_base_link_tf')
    mapping_use_map_saver = LaunchConfiguration('mapping_use_map_saver')
    mapping_map_save_timeout_sec = LaunchConfiguration('mapping_map_save_timeout_sec')
    use_navigation = LaunchConfiguration('use_navigation')
    navigation_use_rviz = LaunchConfiguration('navigation_use_rviz')
    use_patrol = LaunchConfiguration('use_patrol')
    use_mission = LaunchConfiguration('use_mission')
    params_file = LaunchConfiguration('params_file')
    lidar_params_file = LaunchConfiguration('lidar_params_file')
    vision_params_file = LaunchConfiguration('vision_params_file')
    app_bridge_params_file = LaunchConfiguration('app_bridge_params_file')
    map_file = LaunchConfiguration('map')
    nav_params_file = LaunchConfiguration('nav_params_file')
    use_sim_time = LaunchConfiguration('use_sim_time')
    navigation_goal_x = LaunchConfiguration('navigation_goal_x')
    navigation_goal_y = LaunchConfiguration('navigation_goal_y')
    navigation_goal_yaw = LaunchConfiguration('navigation_goal_yaw')
    navigation_send_goal = LaunchConfiguration('navigation_send_goal')
    waypoints_file = LaunchConfiguration('waypoints_file')
    mission_route_file = LaunchConfiguration('mission_route_file')
    mission_database_path = LaunchConfiguration('mission_database_path')
    mission_require_localization = LaunchConfiguration('mission_require_localization')

    return LaunchDescription([
        DeclareLaunchArgument('use_keyboard', default_value='true'),
        DeclareLaunchArgument('use_lidar_avoidance', default_value='false'),
        DeclareLaunchArgument('use_lidar_tracker', default_value='false'),
        DeclareLaunchArgument('use_lidar_warning', default_value='false'),
        DeclareLaunchArgument('use_vision', default_value='false'),
        DeclareLaunchArgument('use_color_detector', default_value='true'),
        DeclareLaunchArgument('use_color_tracker', default_value='false'),
        DeclareLaunchArgument('use_yolo', default_value='false'),
        DeclareLaunchArgument('vision_yolo_model_path', default_value='models/model.pt'),
        DeclareLaunchArgument('vision_yolo_device', default_value='auto'),
        DeclareLaunchArgument('use_app_bridge', default_value='false'),
        DeclareLaunchArgument('app_bridge_host', default_value='0.0.0.0'),
        DeclareLaunchArgument('app_bridge_port', default_value='8765'),
        DeclareLaunchArgument('use_mapping', default_value='false'),
        DeclareLaunchArgument('mapping_use_rviz', default_value='false'),
        DeclareLaunchArgument('mapping_scan_topic', default_value='/scan'),
        DeclareLaunchArgument('mapping_use_scan_filter', default_value='false'),
        DeclareLaunchArgument('mapping_scan_filter_multiple', default_value='2'),
        DeclareLaunchArgument('mapping_publish_laser_tf', default_value='false'),
        DeclareLaunchArgument('mapping_publish_base_link_tf', default_value='false'),
        DeclareLaunchArgument('mapping_use_map_saver', default_value='true'),
        DeclareLaunchArgument('mapping_map_save_timeout_sec', default_value='10.0'),
        DeclareLaunchArgument('use_navigation', default_value='false'),
        DeclareLaunchArgument('navigation_use_rviz', default_value='false'),
        DeclareLaunchArgument('use_patrol', default_value='false'),
        DeclareLaunchArgument('use_mission', default_value='false'),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('navigation_goal_x', default_value='0.5'),
        DeclareLaunchArgument('navigation_goal_y', default_value='0.0'),
        DeclareLaunchArgument('navigation_goal_yaw', default_value='0.0'),
        DeclareLaunchArgument('navigation_send_goal', default_value='false'),
        DeclareLaunchArgument(
            'mission_route_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_mission'), 'config', 'demo_route.yaml',
            ]),
        ),
        DeclareLaunchArgument('mission_database_path', default_value='~/.icar/icar.db'),
        DeclareLaunchArgument('mission_require_localization', default_value='false'),
        OpaqueFunction(function=_validate_operation_mode),
        DeclareLaunchArgument(
            'waypoints_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_navigation'),
                'config',
                'waypoints.yaml',
            ]),
        ),
        DeclareLaunchArgument(
            'params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_bringup'),
                'config',
                'params.yaml',
            ]),
        ),
        DeclareLaunchArgument(
            'lidar_params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_bringup'),
                'config',
                'lidar.yaml',
            ]),
        ),
        DeclareLaunchArgument(
            'vision_params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_vision'),
                'config',
                'vision.yaml',
            ]),
        ),
        DeclareLaunchArgument(
            'app_bridge_params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_app_bridge'),
                'config',
                'app_bridge.yaml',
            ]),
        ),
        DeclareLaunchArgument(
            'map',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_navigation'),
                'maps',
                'lab_map.yaml',
            ]),
        ),
        DeclareLaunchArgument(
            'nav_params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_navigation'),
                'config',
                'nav2_params.yaml',
            ]),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('car_control'),
                    'launch',
                    'control.launch.py',
                ])
            ),
            launch_arguments={
                'use_keyboard': use_keyboard,
                'params_file': params_file,
            }.items(),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('car_lidar'),
                    'launch',
                    'lidar.launch.py',
                ])
            ),
            launch_arguments={
                'params_file': lidar_params_file,
                'use_avoidance': use_lidar_avoidance,
                'use_tracker': use_lidar_tracker,
                'use_warning': use_lidar_warning,
            }.items(),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('car_vision'),
                    'launch',
                    'vision.launch.py',
                ])
            ),
            launch_arguments={
                'params_file': vision_params_file,
                'use_color_detector': use_color_detector,
                'use_color_tracker': use_color_tracker,
                'use_yolo': use_yolo,
                'yolo_model_path': vision_yolo_model_path,
                'yolo_device': vision_yolo_device,
            }.items(),
            condition=IfCondition(use_vision),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('car_app_bridge'),
                    'launch',
                    'app_bridge.launch.py',
                ])
            ),
            launch_arguments={
                'params_file': app_bridge_params_file,
                'host': app_bridge_host,
                'port': app_bridge_port,
            }.items(),
            condition=IfCondition(use_app_bridge),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('car_navigation'),
                    'launch',
                    'mapping.launch.py',
                ])
            ),
            launch_arguments={
                'use_rviz': mapping_use_rviz,
                'use_sim_time': use_sim_time,
                'scan_topic': mapping_scan_topic,
                'use_scan_filter': mapping_use_scan_filter,
                'scan_filter_multiple': mapping_scan_filter_multiple,
                'publish_laser_tf': mapping_publish_laser_tf,
                'publish_base_link_tf': mapping_publish_base_link_tf,
                'use_map_saver': mapping_use_map_saver,
                'map_save_timeout_sec': mapping_map_save_timeout_sec,
            }.items(),
            condition=IfCondition(use_mapping),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('car_navigation'),
                    'launch',
                    'navigation.launch.py',
                ])
            ),
            launch_arguments={
                'x': navigation_goal_x,
                'y': navigation_goal_y,
                'yaw': navigation_goal_yaw,
                'send_goal': navigation_send_goal,
                'map': map_file,
                'params_file': nav_params_file,
                'use_rviz': navigation_use_rviz,
                'use_sim_time': use_sim_time,
            }.items(),
            condition=IfCondition(use_navigation),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('car_mission'),
                    'launch',
                    'mission.launch.py',
                ])
            ),
            launch_arguments={
                'route_file': mission_route_file,
                'database_path': mission_database_path,
                'require_localization': mission_require_localization,
            }.items(),
            condition=IfCondition(use_mission),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('car_navigation'),
                    'launch',
                    'patrol.launch.py',
                ])
            ),
            launch_arguments={
                'waypoints_file': waypoints_file,
                'map': map_file,
                'params_file': nav_params_file,
                'use_rviz': navigation_use_rviz,
                'use_sim_time': use_sim_time,
            }.items(),
            condition=IfCondition(use_patrol),
        ),
    ])
