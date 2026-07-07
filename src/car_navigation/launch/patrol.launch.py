from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    waypoints_file = LaunchConfiguration('waypoints_file')
    map_file = LaunchConfiguration('map')
    params_file = LaunchConfiguration('params_file')
    use_rviz = LaunchConfiguration('use_rviz')
    use_sim_time = LaunchConfiguration('use_sim_time')

    return LaunchDescription([
        DeclareLaunchArgument(
            'waypoints_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_navigation'),
                'config',
                'waypoints.yaml',
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
            'params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_navigation'),
                'config',
                'nav2_params.yaml',
            ]),
        ),
        DeclareLaunchArgument('use_rviz', default_value='false'),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('car_navigation'),
                    'launch',
                    'navigation.launch.py',
                ])
            ),
            launch_arguments={
                'map': map_file,
                'params_file': params_file,
                'send_goal': 'false',
                'use_rviz': use_rviz,
                'use_sim_time': use_sim_time,
            }.items(),
        ),
        Node(
            package='car_navigation',
            executable='waypoint_patrol',
            name='waypoint_patrol',
            parameters=[{'waypoints_file': waypoints_file}],
            output='screen',
        ),
    ])
