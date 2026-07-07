import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    x = LaunchConfiguration('x')
    y = LaunchConfiguration('y')
    yaw = LaunchConfiguration('yaw')
    send_goal = LaunchConfiguration('send_goal')
    use_gzclient = LaunchConfiguration('use_gzclient')
    use_rviz = LaunchConfiguration('use_rviz')

    pkg_wpr = get_package_share_directory('wpr_simulation2')
    pkg_car_nav = get_package_share_directory('car_navigation')

    map_file = os.path.join(pkg_car_nav, 'maps', 'lab_map.yaml')
    nav_params = os.path.join(pkg_wpr, 'config', 'nav2_params.yaml')
    rviz_config = os.path.join(pkg_wpr, 'rviz', 'navi.rviz')

    return LaunchDescription([
        DeclareLaunchArgument('x', default_value='0.5'),
        DeclareLaunchArgument('y', default_value='0.0'),
        DeclareLaunchArgument('yaw', default_value='0.0'),
        DeclareLaunchArgument('send_goal', default_value='false'),
        DeclareLaunchArgument('use_gzclient', default_value='true'),
        DeclareLaunchArgument('use_rviz', default_value='false'),

        # Simulation scene
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(pkg_wpr, 'launch', 'robocup_home.launch.py')
            ),
            launch_arguments={'use_gzclient': use_gzclient}.items(),
        ),

        # Nav2 bringup with our map
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(
                    get_package_share_directory('nav2_bringup'),
                    'launch',
                    'bringup_launch.py',
                )
            ),
            launch_arguments={
                'map': map_file,
                'use_sim_time': 'true',
                'params_file': nav_params,
            }.items(),
        ),

        # Optional RViz
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            arguments=['-d', rviz_config],
            condition=IfCondition(use_rviz),
            output='screen',
        ),

        # Goal publisher
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