import os

from ament_index_python.packages import get_package_share_directory, get_package_share_path
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition, LaunchConfigurationEquals
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    rplidar_type = LaunchConfiguration('rplidar_type')
    pub_odom_tf = LaunchConfiguration('pub_odom_tf')
    use_robot_description = LaunchConfiguration('use_robot_description')

    description_path = get_package_share_path('icar_description')
    default_model_path = description_path / 'urdf/icar_X3.urdf'
    robot_description = ParameterValue(Command(['xacro ', str(default_model_path)]), value_type=str)

    imu_filter_config = os.path.join(
        get_package_share_directory('icar_bringup'),
        'param',
        'imu_filter_param.yaml',
    )

    return LaunchDescription([
        DeclareLaunchArgument('rplidar_type', default_value='a1', choices=['a1', 's2', '4ROS']),
        DeclareLaunchArgument('pub_odom_tf', default_value='false'),
        DeclareLaunchArgument('use_robot_description', default_value='true'),
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            parameters=[{'robot_description': robot_description}],
            condition=IfCondition(use_robot_description),
            output='screen',
        ),
        Node(
            package='joint_state_publisher',
            executable='joint_state_publisher',
            condition=IfCondition(use_robot_description),
            output='screen',
        ),
        Node(
            package='icar_bringup',
            executable='Mcnamu_driver_X3',
            output='screen',
        ),
        Node(
            package='icar_base_node',
            executable='base_node_X3',
            parameters=[{'pub_odom_tf': pub_odom_tf}],
            output='screen',
        ),
        Node(
            package='imu_filter_madgwick',
            executable='imu_filter_madgwick_node',
            parameters=[imu_filter_config],
            output='screen',
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                os.path.join(get_package_share_directory('robot_localization'), 'launch'),
                '/ekf_x1_x3_launch.py',
            ]),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                os.path.join(get_package_share_directory('sllidar_ros2'), 'launch'),
                '/sllidar_launch.py',
            ]),
            condition=LaunchConfigurationEquals('rplidar_type', 'a1'),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                os.path.join(get_package_share_directory('sllidar_ros2'), 'launch'),
                '/sllidar_s2_launch.py',
            ]),
            condition=LaunchConfigurationEquals('rplidar_type', 's2'),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                os.path.join(get_package_share_directory('ydlidar_ros2_driver'), 'launch'),
                '/ydlidar_raw_launch.py',
            ]),
            condition=LaunchConfigurationEquals('rplidar_type', '4ROS'),
        ),
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            arguments=['0.0435', '5.258E-05', '0.11', '3.14', '0', '0', 'base_link', 'laser'],
            output='screen',
        ),
    ])
