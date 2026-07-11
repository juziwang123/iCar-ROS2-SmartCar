from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    route_file = LaunchConfiguration('route_file')
    database_path = LaunchConfiguration('database_path')
    require_localization = LaunchConfiguration('require_localization')

    return LaunchDescription([
        DeclareLaunchArgument(
            'route_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_mission'), 'config', 'demo_route.yaml',
            ]),
        ),
        DeclareLaunchArgument('database_path', default_value='~/.icar/icar.db'),
        DeclareLaunchArgument('require_localization', default_value='false'),
        Node(
            package='car_mission',
            executable='mission_manager',
            name='mission_manager',
            parameters=[{
                'route_file': route_file,
                'database_path': database_path,
                'require_localization': require_localization,
            }],
            output='screen',
        ),
    ])
