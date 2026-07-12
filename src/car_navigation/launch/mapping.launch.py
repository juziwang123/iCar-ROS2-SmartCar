from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    use_rviz = LaunchConfiguration('use_rviz')
    use_sim_time = LaunchConfiguration('use_sim_time')
    scan_topic = LaunchConfiguration('scan_topic')
    use_scan_filter = LaunchConfiguration('use_scan_filter')
    scan_filter_multiple = LaunchConfiguration('scan_filter_multiple')
    publish_laser_tf = LaunchConfiguration('publish_laser_tf')
    publish_base_link_tf = LaunchConfiguration('publish_base_link_tf')
    use_map_saver = LaunchConfiguration('use_map_saver')
    map_save_timeout_sec = LaunchConfiguration('map_save_timeout_sec')
    max_laser_range = LaunchConfiguration('max_laser_range')

    return LaunchDescription([
        DeclareLaunchArgument('use_rviz', default_value='false'),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('scan_topic', default_value='/scan'),
        DeclareLaunchArgument('use_scan_filter', default_value='false'),
        DeclareLaunchArgument('scan_filter_multiple', default_value='2'),
        DeclareLaunchArgument('publish_laser_tf', default_value='false'),
        DeclareLaunchArgument('publish_base_link_tf', default_value='false'),
        # The APP bridge calls this lifecycle service to persist a completed
        # SLAM map.  It is intentionally started only in mapping mode.
        DeclareLaunchArgument('use_map_saver', default_value='true'),
        # Foxy nav2_map_server declares this parameter as an integer.
        DeclareLaunchArgument('map_save_timeout_sec', default_value='10'),
        DeclareLaunchArgument('max_laser_range', default_value='12.0'),
        SetEnvironmentVariable('QT_AUTO_SCREEN_SCALE_FACTOR', '0'),
        SetEnvironmentVariable('QT_SCALE_FACTOR', '0.8'),
        SetEnvironmentVariable('QT_FONT_DPI', '96'),
        Node(
            package='car_navigation',
            executable='scan_filter',
            name='scan_filter',
            parameters=[{
                'input_topic': '/scan',
                'output_topic': '/downsampled_scan',
                'multiple': scan_filter_multiple,
            }],
            condition=IfCondition(use_scan_filter),
            output='screen',
        ),
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='static_base_footprint_to_base_link',
            arguments=['0', '0', '0', '0', '0', '0', 'base_footprint', 'base_link'],
            condition=IfCondition(publish_base_link_tf),
            output='screen',
        ),
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='static_base_link_to_laser',
            arguments=['0.0435', '0.00005258', '0.11', '3.14', '0', '0', 'base_link', 'laser'],
            condition=IfCondition(publish_laser_tf),
            output='screen',
        ),
        Node(
            package='slam_toolbox',
            executable='sync_slam_toolbox_node',
            name='sync_slam_toolbox_node',
            parameters=[{
                'use_sim_time': use_sim_time,
                'base_frame': 'base_footprint',
                'odom_frame': 'odom',
                'map_frame': 'map',
                'scan_topic': scan_topic,
                # Match the SLLidar A1 capability reported by the vehicle
                # driver; the slam_toolbox default is 25 m.
                'max_laser_range': ParameterValue(max_laser_range, value_type=float),
            }],
            output='screen',
        ),
        Node(
            package='nav2_map_server',
            executable='map_saver_server',
            name='map_saver',
            parameters=[{
                'save_map_timeout': ParameterValue(map_save_timeout_sec, value_type=int),
                'free_thresh_default': 0.25,
                'occupied_thresh_default': 0.65,
            }],
            condition=IfCondition(use_map_saver),
            output='screen',
        ),
        # On the Jetson the map_saver process can take longer to create its
        # lifecycle services than the manager takes to issue its first
        # transition. Start the manager after the server has registered so
        # the map-saver service reliably reaches ACTIVE.
        TimerAction(
            period=1.0,
            actions=[Node(
                package='nav2_lifecycle_manager',
                executable='lifecycle_manager',
                name='map_saver_lifecycle_manager',
                parameters=[{
                    'autostart': True,
                    'node_names': ['map_saver'],
                    'use_sim_time': use_sim_time,
                }],
                condition=IfCondition(use_map_saver),
                output='screen',
            )],
        ),
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            condition=IfCondition(use_rviz),
            output='screen',
        ),
    ])
