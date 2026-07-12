from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    params_file = LaunchConfiguration('params_file')
    use_color_detector = LaunchConfiguration('use_color_detector')
    use_color_tracker = LaunchConfiguration('use_color_tracker')
    use_yolo = LaunchConfiguration('use_yolo')
    use_person_detector = LaunchConfiguration('use_person_detector')

    return LaunchDescription([
        DeclareLaunchArgument('use_color_detector', default_value='true'),
        DeclareLaunchArgument('use_color_tracker', default_value='false'),
        DeclareLaunchArgument('use_yolo', default_value='false'),
        DeclareLaunchArgument('use_person_detector', default_value='false'),
        DeclareLaunchArgument(
            'params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('car_vision'),
                'config',
                'vision.yaml',
            ]),
        ),
        Node(
            package='car_vision',
            executable='color_detector',
            name='color_detector',
            parameters=[params_file],
            condition=IfCondition(use_color_detector),
            output='screen',
        ),
        Node(
            package='car_vision',
            executable='color_tracker',
            name='color_tracker',
            parameters=[params_file],
            condition=IfCondition(use_color_tracker),
            output='screen',
        ),
        Node(
            package='car_vision',
            executable='yolo_detector',
            name='yolo_detector',
            parameters=[params_file],
            condition=IfCondition(use_yolo),
            output='screen',
        ),
        Node(
            package='car_vision',
            executable='person_detector',
            name='person_detector',
            parameters=[params_file],
            condition=IfCondition(use_person_detector),
            output='screen',
        ),
    ])
