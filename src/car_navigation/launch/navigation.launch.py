from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    x = LaunchConfiguration('x')
    y = LaunchConfiguration('y')
    yaw = LaunchConfiguration('yaw')
    send_goal = LaunchConfiguration('send_goal')

    return LaunchDescription([
        DeclareLaunchArgument('x', default_value='0.5'),
        DeclareLaunchArgument('y', default_value='0.0'),
        DeclareLaunchArgument('yaw', default_value='0.0'),
        DeclareLaunchArgument('send_goal', default_value='true'),
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
            executable='goal_publisher',
            name='goal_publisher',
            parameters=[{
                'x': x,
                'y': y,
                'yaw': yaw,
                'send_on_start': send_goal,
            }],
            output='screen',
        ),
    ])