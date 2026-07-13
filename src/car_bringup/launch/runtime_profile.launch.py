"""Launch only one mutually-exclusive mapping, navigation or mission profile."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def _boolean(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    raise RuntimeError(f'Launch argument {name} must be a boolean, got {value!r}')


def _include(package: str, launch_file: str, arguments):
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare(package), 'launch', launch_file])
        ),
        launch_arguments=arguments.items(),
    )


def _profile_actions(context, *args, **kwargs):
    profile = LaunchConfiguration('profile').perform(context).strip().lower()
    if profile not in {'mapping', 'navigation', 'mission'}:
        raise RuntimeError('profile must be mapping, navigation, or mission')

    mapping_arguments = {
        'use_rviz': LaunchConfiguration('mapping_use_rviz'),
        'use_sim_time': LaunchConfiguration('use_sim_time'),
        'scan_topic': LaunchConfiguration('mapping_scan_topic'),
        'use_scan_filter': LaunchConfiguration('mapping_use_scan_filter'),
        'scan_filter_multiple': LaunchConfiguration('mapping_scan_filter_multiple'),
        'publish_laser_tf': LaunchConfiguration('mapping_publish_laser_tf'),
        'publish_base_link_tf': LaunchConfiguration('mapping_publish_base_link_tf'),
        'use_map_saver': LaunchConfiguration('mapping_use_map_saver'),
        'map_save_timeout_sec': LaunchConfiguration('mapping_map_save_timeout_sec'),
        'max_laser_range': LaunchConfiguration('mapping_max_laser_range'),
    }
    navigation_arguments = {
        'map': LaunchConfiguration('map'),
        'params_file': LaunchConfiguration('nav_params_file'),
        'use_rviz': LaunchConfiguration('navigation_use_rviz'),
        'use_sim_time': LaunchConfiguration('use_sim_time'),
        'send_goal': 'false',
    }
    if profile == 'mapping':
        return [_include('car_navigation', 'mapping.launch.py', mapping_arguments)]

    actions = [_include('car_navigation', 'navigation.launch.py', navigation_arguments)]
    if profile != 'mission':
        return actions

    actions.extend([
        _include('car_mission', 'mission.launch.py', {
            'route_file': LaunchConfiguration('mission_route_file'),
            'database_path': LaunchConfiguration('mission_database_path'),
            'require_localization': LaunchConfiguration('mission_require_localization'),
        }),
        _include('car_inspection', 'inspection.launch.py', {
            'params_file': LaunchConfiguration('inspection_params_file'),
            'use_marker_detector': LaunchConfiguration('inspection_use_marker_detector'),
        }),
    ])
    if _boolean(LaunchConfiguration('use_vision').perform(context), 'use_vision'):
        # camera_bridge belongs to the persistent foundation.  Task-specific
        # detectors are started here so a mapping/navigation profile never
        # owns a duplicate camera process.
        actions.append(_include('car_vision', 'vision.launch.py', {
            'params_file': LaunchConfiguration('vision_params_file'),
            'use_camera_bridge': 'false',
            'use_color_detector': 'true',
            'use_color_tracker': 'false',
            'use_yolo': LaunchConfiguration('use_yolo'),
            'yolo_model_path': LaunchConfiguration('vision_yolo_model_path'),
            'yolo_device': LaunchConfiguration('vision_yolo_device'),
            'yolo_active_model': LaunchConfiguration('vision_yolo_active_model'),
            'yolo_active_models': LaunchConfiguration('vision_yolo_active_models'),
        }))
    return actions


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        DeclareLaunchArgument('profile'),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('use_yolo', default_value='false'),
        DeclareLaunchArgument('use_vision', default_value='true'),
        DeclareLaunchArgument('mapping_use_rviz', default_value='false'),
        DeclareLaunchArgument('mapping_scan_topic', default_value='/scan'),
        DeclareLaunchArgument('mapping_use_scan_filter', default_value='false'),
        DeclareLaunchArgument('mapping_scan_filter_multiple', default_value='2'),
        DeclareLaunchArgument('mapping_publish_laser_tf', default_value='false'),
        DeclareLaunchArgument('mapping_publish_base_link_tf', default_value='false'),
        DeclareLaunchArgument('mapping_use_map_saver', default_value='true'),
        DeclareLaunchArgument('mapping_map_save_timeout_sec', default_value='10'),
        DeclareLaunchArgument('mapping_max_laser_range', default_value='12.0'),
        DeclareLaunchArgument('navigation_use_rviz', default_value='false'),
        DeclareLaunchArgument(
            'map', default_value=PathJoinSubstitution([
                FindPackageShare('car_navigation'), 'maps', 'lab_map.yaml',
            ]),
        ),
        DeclareLaunchArgument(
            'nav_params_file', default_value=PathJoinSubstitution([
                FindPackageShare('car_navigation'), 'config', 'nav2_params.yaml',
            ]),
        ),
        DeclareLaunchArgument(
            'mission_route_file', default_value=PathJoinSubstitution([
                FindPackageShare('car_mission'), 'config', 'demo_route.yaml',
            ]),
        ),
        DeclareLaunchArgument('mission_database_path', default_value='~/.icar/icar.db'),
        DeclareLaunchArgument('mission_require_localization', default_value='true'),
        DeclareLaunchArgument('inspection_use_marker_detector', default_value='true'),
        DeclareLaunchArgument(
            'inspection_params_file', default_value=PathJoinSubstitution([
                FindPackageShare('car_inspection'), 'config', 'inspection.yaml',
            ]),
        ),
        DeclareLaunchArgument(
            'vision_params_file', default_value=PathJoinSubstitution([
                FindPackageShare('car_vision'), 'config', 'vision.yaml',
            ]),
        ),
        DeclareLaunchArgument('vision_yolo_model_path', default_value='models/model.pt'),
        DeclareLaunchArgument('vision_yolo_device', default_value='auto'),
        DeclareLaunchArgument('vision_yolo_active_model', default_value='person'),
        DeclareLaunchArgument('vision_yolo_active_models', default_value=''),
        OpaqueFunction(function=_profile_actions),
    ])
