import math
from typing import List, Optional, Tuple

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import LaserScan


class TrackerNode(Node):
    def __init__(self) -> None:
        super().__init__('lidar_tracker')
        self.declare_parameter('scan_topic', '/scan')
        self.declare_parameter('output_topic', '/cmd_vel_follow')
        self.declare_parameter('follow_angle_deg', 35.0)
        self.declare_parameter('front_center_deg', 180.0)
        self.declare_parameter('desired_distance', 0.8)
        self.declare_parameter('distance_tolerance', 0.1)
        self.declare_parameter('max_follow_distance', 2.0)
        self.declare_parameter('linear_gain', 0.5)
        self.declare_parameter('angular_gain', 1.2)
        self.declare_parameter('max_linear_speed', 0.2)
        self.declare_parameter('max_angular_speed', 0.8)

        self.output_topic = str(self.get_parameter('output_topic').value)
        self.follow_angle_deg = float(self.get_parameter('follow_angle_deg').value)
        self.front_center_deg = float(self.get_parameter('front_center_deg').value)
        self.front_center_rad = math.radians(self.front_center_deg)
        self.desired_distance = float(self.get_parameter('desired_distance').value)
        self.distance_tolerance = float(self.get_parameter('distance_tolerance').value)
        self.max_follow_distance = float(self.get_parameter('max_follow_distance').value)
        self.linear_gain = float(self.get_parameter('linear_gain').value)
        self.angular_gain = float(self.get_parameter('angular_gain').value)
        self.max_linear_speed = float(self.get_parameter('max_linear_speed').value)
        self.max_angular_speed = float(self.get_parameter('max_angular_speed').value)

        self.publisher = self.create_publisher(Twist, self.output_topic, 10)
        self.create_subscription(
            LaserScan,
            str(self.get_parameter('scan_topic').value),
            self._on_scan,
            10,
        )
        self.get_logger().info(
            f'Lidar tracker started: front_center_deg={self.front_center_deg}, '
            f'desired_distance={self.desired_distance}'
        )

    def _on_scan(self, msg: LaserScan) -> None:
        target = self._find_target(msg)
        command = Twist()
        if target is None:
            self.publisher.publish(command)
            return

        target_distance, target_angle = target
        distance_error = target_distance - self.desired_distance
        if abs(distance_error) > self.distance_tolerance:
            command.linear.x = self._clamp(distance_error * self.linear_gain, self.max_linear_speed)
        command.angular.z = self._clamp(target_angle * self.angular_gain, self.max_angular_speed)
        self.publisher.publish(command)

    def _find_target(self, msg: LaserScan) -> Optional[Tuple[float, float]]:
        candidates: List[Tuple[float, float]] = []
        half_window = math.radians(self.follow_angle_deg)
        angle = msg.angle_min
        for distance in msg.ranges:
            if math.isinf(distance) or math.isnan(distance):
                angle += msg.angle_increment
                continue
            relative_angle = self._angle_delta(angle, self.front_center_rad)
            if msg.range_min < distance < min(msg.range_max, self.max_follow_distance) and abs(relative_angle) <= half_window:
                candidates.append((distance, relative_angle))
            angle += msg.angle_increment

        if not candidates:
            return None
        return min(candidates, key=lambda item: item[0])

    @staticmethod
    def _clamp(value: float, limit: float) -> float:
        return max(-limit, min(limit, value))

    @staticmethod
    def _angle_delta(angle: float, center: float) -> float:
        return math.atan2(math.sin(angle - center), math.cos(angle - center))

    def stop(self) -> None:
        self.publisher.publish(Twist())


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TrackerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()
        node.destroy_node()
        rclpy.shutdown()
