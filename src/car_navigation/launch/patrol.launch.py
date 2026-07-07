from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    waypoints_file = LaunchConfiguration('waypoints_file')

    return LaunchDescription([
        DeclareLaunchArgument(
            'waypoints_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_navigation'),
                'config',
                'waypoints.yaml',
            ]),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('wpr_simulation2'),
                    'launch',
                    'navigation.launch.py',
                ])
            )
        ),
        Node(
            package='car_navigation',
            executable='waypoint_patrol',
            name='waypoint_patrol',
            parameters=[{'waypoints_file': waypoints_file}],
            output='screen',
        ),
    ])