from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    use_keyboard = LaunchConfiguration('use_keyboard')
    use_lidar_avoidance = LaunchConfiguration('use_lidar_avoidance')
    use_lidar_tracker = LaunchConfiguration('use_lidar_tracker')
    use_mapping = LaunchConfiguration('use_mapping')
    mapping_use_gzclient = LaunchConfiguration('mapping_use_gzclient')
    mapping_use_rviz = LaunchConfiguration('mapping_use_rviz')
    use_navigation = LaunchConfiguration('use_navigation')
    use_patrol = LaunchConfiguration('use_patrol')
    params_file = LaunchConfiguration('params_file')
    lidar_params_file = LaunchConfiguration('lidar_params_file')
    navigation_goal_x = LaunchConfiguration('navigation_goal_x')
    navigation_goal_y = LaunchConfiguration('navigation_goal_y')
    navigation_goal_yaw = LaunchConfiguration('navigation_goal_yaw')
    waypoints_file = LaunchConfiguration('waypoints_file')

    return LaunchDescription([
        DeclareLaunchArgument('use_keyboard', default_value='true'),
        DeclareLaunchArgument('use_lidar_avoidance', default_value='false'),
        DeclareLaunchArgument('use_lidar_tracker', default_value='false'),
        DeclareLaunchArgument('use_mapping', default_value='false'),
        DeclareLaunchArgument('mapping_use_gzclient', default_value='false'),
        DeclareLaunchArgument('mapping_use_rviz', default_value='false'),
        DeclareLaunchArgument('use_navigation', default_value='false'),
        DeclareLaunchArgument('use_patrol', default_value='false'),
        DeclareLaunchArgument('navigation_goal_x', default_value='0.5'),
        DeclareLaunchArgument('navigation_goal_y', default_value='0.0'),
        DeclareLaunchArgument('navigation_goal_yaw', default_value='0.0'),
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
            }.items(),
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
                'use_gzclient': mapping_use_gzclient,
                'use_rviz': mapping_use_rviz,
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
            }.items(),
            condition=IfCondition(use_navigation),
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
            }.items(),
            condition=IfCondition(use_patrol),
        ),
    ])