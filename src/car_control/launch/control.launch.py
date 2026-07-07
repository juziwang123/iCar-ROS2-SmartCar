from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    use_keyboard = LaunchConfiguration('use_keyboard')
    params_file = LaunchConfiguration('params_file')

    return LaunchDescription([
        DeclareLaunchArgument('use_keyboard', default_value='true'),
        DeclareLaunchArgument(
            'params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_control'),
                'config',
                'control.yaml',
            ]),
            description='Optional parameter file for control nodes.',
        ),
        Node(
            package='car_control',
            executable='safety_mux',
            name='safety_mux',
            parameters=[params_file],
            output='screen',
        ),
        Node(
            package='car_control',
            executable='motion_controller',
            name='motion_controller',
            parameters=[params_file],
            output='screen',
        ),
        Node(
            package='car_control',
            executable='keyboard_teleop',
            name='keyboard_teleop',
            parameters=[params_file],
            condition=IfCondition(use_keyboard),
            output='screen',
        ),
            Node(
                package='car_control',
                executable='light_controller',
                name='light_controller',
                parameters=[params_file],
                output='screen',
            ),
    ])