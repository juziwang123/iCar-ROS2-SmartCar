from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    params_file = LaunchConfiguration('params_file')
    use_marker_detector = LaunchConfiguration('use_marker_detector')
    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_inspection'), 'config', 'inspection.yaml',
            ]),
        ),
        DeclareLaunchArgument('use_marker_detector', default_value='true'),
        Node(
            package='car_inspection',
            executable='qr_detector',
            name='qr_detector',
            parameters=[params_file],
            condition=IfCondition(use_marker_detector),
            output='screen',
        ),
        Node(
            package='car_inspection',
            executable='checkpoint_verifier',
            name='checkpoint_verifier',
            parameters=[params_file],
            output='screen',
        ),
    ])
