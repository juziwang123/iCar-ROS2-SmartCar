from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    use_rviz = LaunchConfiguration('use_rviz')
    use_sim_time = LaunchConfiguration('use_sim_time')

    return LaunchDescription([
        DeclareLaunchArgument('use_rviz', default_value='false'),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        SetEnvironmentVariable('QT_AUTO_SCREEN_SCALE_FACTOR', '0'),
        SetEnvironmentVariable('QT_SCALE_FACTOR', '0.8'),
        SetEnvironmentVariable('QT_FONT_DPI', '96'),
        Node(
            package='slam_toolbox',
            executable='sync_slam_toolbox_node',
            name='sync_slam_toolbox_node',
            parameters=[{
                'use_sim_time': use_sim_time,
                'base_frame': 'base_footprint',
                'odom_frame': 'odom',
                'map_frame': 'map',
            }],
            output='screen',
        ),
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            condition=IfCondition(use_rviz),
            output='screen',
        ),
    ])
