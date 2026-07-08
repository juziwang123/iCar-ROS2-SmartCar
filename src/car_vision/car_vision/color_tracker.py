from __future__ import annotations

from typing import Optional, Sequence

import rclpy
from geometry_msgs.msg import PointStamped, Twist
from rclpy.node import Node


class ColorTracker(Node):
    def __init__(self) -> None:
        super().__init__('color_tracker')
        self.declare_parameter('target_topic', '/vision/color_target')
        self.declare_parameter('output_topic', '/cmd_vel_vision')
        self.declare_parameter('target_area_ratio', 0.08)
        self.declare_parameter('area_tolerance', 0.02)
        self.declare_parameter('angular_gain', 0.8)
        self.declare_parameter('linear_gain', 0.5)
        self.declare_parameter('max_linear_speed', 0.18)
        self.declare_parameter('max_angular_speed', 0.8)

        self.publisher = self.create_publisher(Twist, str(self.get_parameter('output_topic').value), 10)
        self.create_subscription(PointStamped, str(self.get_parameter('target_topic').value), self._on_target, 10)
        self.get_logger().info('Color tracker started')

    def _on_target(self, msg: PointStamped) -> None:
        target_area = float(self.get_parameter('target_area_ratio').value)
        area_tolerance = float(self.get_parameter('area_tolerance').value)
        linear_gain = float(self.get_parameter('linear_gain').value)
        angular_gain = float(self.get_parameter('angular_gain').value)
        max_linear = float(self.get_parameter('max_linear_speed').value)
        max_angular = float(self.get_parameter('max_angular_speed').value)

        command = Twist()
        area_error = target_area - float(msg.point.z)
        if abs(area_error) > area_tolerance:
            command.linear.x = self._clamp(area_error * linear_gain, max_linear)
        command.angular.z = self._clamp(-float(msg.point.x) * angular_gain, max_angular)
        self.publisher.publish(command)

    @staticmethod
    def _clamp(value: float, limit: float) -> float:
        return max(-limit, min(limit, value))


def main(args: Optional[Sequence[str]] = None) -> None:
    rclpy.init(args=args)
    node = ColorTracker()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.publisher.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()
