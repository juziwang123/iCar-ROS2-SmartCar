from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    route_file = LaunchConfiguration('route_file')
    database_path = LaunchConfiguration('database_path')
    require_localization = LaunchConfiguration('require_localization')
    use_health_monitor = LaunchConfiguration('use_health_monitor')

    return LaunchDescription([
        DeclareLaunchArgument(
            'route_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_mission'), 'config', 'demo_route.yaml',
            ]),
        ),
        DeclareLaunchArgument('database_path', default_value='~/.icar/icar.db'),
        DeclareLaunchArgument('require_localization', default_value='false'),
        DeclareLaunchArgument('use_health_monitor', default_value='true'),
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
        Node(
            package='car_mission', executable='health_monitor', name='health_monitor',
            condition=IfCondition(use_health_monitor),
            output='screen',
        ),
    ])
