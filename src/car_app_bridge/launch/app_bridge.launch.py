#!/usr/bin/env python3
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        Node(
            package="car_app_bridge",
            executable="app_server",
            name="app_bridge",
            output="screen",
        ),
    ])
