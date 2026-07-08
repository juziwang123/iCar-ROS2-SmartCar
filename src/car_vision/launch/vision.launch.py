#!/usr/bin/env python3
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        DeclareLaunchArgument("model", default_value="yolov8n.pt"),
        DeclareLaunchArgument("confidence", default_value="0.5"),
        DeclareLaunchArgument("device", default_value="cpu"),
        DeclareLaunchArgument("publish_control", default_value="true"),

        Node(
            package="car_vision",
            executable="yolo_detector",
            name="yolo_detector",
            parameters=[{
                "model": "$(var model)",
                "confidence": "$(var confidence)",
                "device": "$(var device)",
                "publish_control": "$(var publish_control)",
            }],
            output="screen",
        ),
    ])
