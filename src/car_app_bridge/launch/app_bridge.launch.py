from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    params_file = LaunchConfiguration('params_file')
    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_app_bridge'),
                'config',
                'app_bridge.yaml',
            ]),
        ),
        Node(
            package='car_app_bridge',
            executable='app_server',
            name='app_server',
            parameters=[params_file],
            output='screen',
        ),
    ])
