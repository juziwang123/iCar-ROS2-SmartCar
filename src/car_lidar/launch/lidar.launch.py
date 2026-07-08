from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    params_file = LaunchConfiguration('params_file')
    use_avoidance = LaunchConfiguration('use_avoidance')
    use_tracker = LaunchConfiguration('use_tracker')
    use_warning = LaunchConfiguration('use_warning')

    return LaunchDescription([
        DeclareLaunchArgument('use_avoidance', default_value='true'),
        DeclareLaunchArgument('use_tracker', default_value='false'),
        DeclareLaunchArgument('use_warning', default_value='false'),
        DeclareLaunchArgument(
            'params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_lidar'),
                'config',
                'lidar.yaml',
            ]),
        ),
        Node(
            package='car_lidar',
            executable='avoidance',
            name='lidar_avoidance',
            parameters=[params_file],
            condition=IfCondition(use_avoidance),
            output='screen',
        ),
        Node(
            package='car_lidar',
            executable='tracker',
            name='lidar_tracker',
            parameters=[params_file, {'output_topic': '/cmd_vel_follow'}],
            condition=IfCondition(use_tracker),
            output='screen',
        ),
        Node(
            package='car_lidar',
            executable='warning',
            name='lidar_warning',
            parameters=[params_file],
            condition=IfCondition(use_warning),
            output='screen',
        ),
    ])
