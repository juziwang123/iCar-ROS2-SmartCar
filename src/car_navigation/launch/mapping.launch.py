from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    use_gzclient = LaunchConfiguration('use_gzclient')
    use_rviz = LaunchConfiguration('use_rviz')

    return LaunchDescription([
        DeclareLaunchArgument('use_gzclient', default_value='false'),
        DeclareLaunchArgument('use_rviz', default_value='false'),
        SetEnvironmentVariable('QT_AUTO_SCREEN_SCALE_FACTOR', '0'),
        SetEnvironmentVariable('QT_SCALE_FACTOR', '0.8'),
        SetEnvironmentVariable('QT_FONT_DPI', '96'),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('wpr_simulation2'),
                    'launch',
                    'robocup_home.launch.py',
                ])
            ),
            launch_arguments={
                'use_gzclient': use_gzclient,
            }.items(),
        ),
        Node(
            package='slam_toolbox',
            executable='sync_slam_toolbox_node',
            name='sync_slam_toolbox_node',
            parameters=[{
                'use_sim_time': True,
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
            arguments=['-d', PathJoinSubstitution([
                FindPackageShare('wpr_simulation2'),
                'rviz',
                'slam.rviz',
            ])],
            condition=IfCondition(use_rviz),
            output='screen',
        ),
    ])