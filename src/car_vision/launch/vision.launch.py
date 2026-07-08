from launch import LaunchDescription
from launch_ros.actions import Node
from launch.substitutions import LaunchConfiguration
from launch.actions import DeclareLaunchArgument
import launch.conditions


def generate_launch_description():
    image_topic = LaunchConfiguration('image_topic', default='/camera/color/image_raw')
    target_color = LaunchConfiguration('target_color', default='red')
    
    return LaunchDescription([
        DeclareLaunchArgument(
            'image_topic',
            default_value='/camera/color/image_raw',
            description='Image topic name'
        ),
        DeclareLaunchArgument(
            'target_color',
            default_value='red',
            description='Target color for color detection'
        ),
        DeclareLaunchArgument(
            'mode',
            default_value='color_tracking',
            description='Operation mode: color_tracking, yolo_detection, line_following, defect_detection'
        ),
        
        Node(
            package='car_vision',
            executable='color_detector',
            name='color_detector',
            parameters=[{
                'image_topic': image_topic,
                'target_color': target_color,
                'min_area': 100
            }],
            remappings=[
                ('/camera/color/image_raw', image_topic)
            ],
            condition=launch.conditions.IfCondition(
                LaunchConfiguration('mode').equals('color_tracking')
            )
        ),
        
        Node(
            package='car_vision',
            executable='color_tracker',
            name='color_tracker',
            parameters=[{
                'image_width': 640,
                'image_height': 480,
                'kp_angular': 0.005,
                'kp_linear': 0.001,
                'max_linear_speed': 0.3,
                'max_angular_speed': 0.5
            }],
            condition=launch.conditions.IfCondition(
                LaunchConfiguration('mode').equals('color_tracking')
            )
        ),
        
        Node(
            package='car_vision',
            executable='yolo_detector',
            name='yolo_detector',
            parameters=[{
                'image_topic': image_topic,
                'confidence_threshold': 0.5,
                'device': 'cuda'
            }],
            remappings=[
                ('/camera/color/image_raw', image_topic)
            ],
            condition=launch.conditions.IfCondition(
                LaunchConfiguration('mode').equals('yolo_detection')
            )
        ),
        
        Node(
            package='car_vision',
            executable='line_follower',
            name='line_follower',
            parameters=[{
                'image_topic': image_topic,
                'image_width': 640,
                'image_height': 480,
                'kp_angular': 0.008,
                'max_linear_speed': 0.2,
                'line_color': 'black'
            }],
            remappings=[
                ('/camera/color/image_raw', image_topic)
            ],
            condition=launch.conditions.IfCondition(
                LaunchConfiguration('mode').equals('line_following')
            )
        ),
        
        Node(
            package='car_vision',
            executable='defect_detector',
            name='defect_detector',
            parameters=[{
                'image_topic': image_topic,
                'min_defect_area': 100
            }],
            remappings=[
                ('/camera/color/image_raw', image_topic)
            ],
            condition=launch.conditions.IfCondition(
                LaunchConfiguration('mode').equals('defect_detection')
            )
        ),
    ])
