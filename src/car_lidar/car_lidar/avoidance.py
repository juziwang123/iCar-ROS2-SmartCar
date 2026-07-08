import math
from typing import List, Optional, Tuple

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool


class AvoidanceNode(Node):
    def __init__(self) -> None:
        super().__init__('lidar_avoidance')
        self.declare_parameter('scan_topic', '/scan')
        self.declare_parameter('output_topic', '/cmd_vel_lidar')
        self.declare_parameter('override_topic', '/lidar/override_active')
        self.declare_parameter('estop_topic', '/emergency_stop')
        self.declare_parameter('front_distance_threshold', 0.5)
        self.declare_parameter('slow_distance_threshold', 0.9)
        self.declare_parameter('linear_speed', 0.15)
        self.declare_parameter('turn_speed', 0.6)
        self.declare_parameter('front_angle_deg', 25.0)
        self.declare_parameter('front_center_deg', 0.0)
        self.declare_parameter('publish_estop', False)

        self.output_topic = str(self.get_parameter('output_topic').value)
        self.override_topic = str(self.get_parameter('override_topic').value)
        self.estop_topic = str(self.get_parameter('estop_topic').value)
        self.front_distance_threshold = float(self.get_parameter('front_distance_threshold').value)
        self.slow_distance_threshold = float(self.get_parameter('slow_distance_threshold').value)
        self.linear_speed = float(self.get_parameter('linear_speed').value)
        self.turn_speed = float(self.get_parameter('turn_speed').value)
        self.front_angle_deg = float(self.get_parameter('front_angle_deg').value)
        self.front_center_rad = math.radians(float(self.get_parameter('front_center_deg').value))
        self.publish_estop = bool(self.get_parameter('publish_estop').value)

        self.cmd_publisher = self.create_publisher(Twist, self.output_topic, 10)
        self.override_publisher = self.create_publisher(Bool, self.override_topic, 10)
        self.estop_publisher = self.create_publisher(Bool, self.estop_topic, 10)
        self.create_subscription(
            LaserScan,
            str(self.get_parameter('scan_topic').value),
            self._on_scan,
            10,
        )
        self.get_logger().info('Lidar avoidance started')

    def _on_scan(self, msg: LaserScan) -> None:
        front_distance, left_distance, right_distance = self._extract_distances(msg)
        if front_distance is None:
            return

        command = Twist()
        estop = False
        override_active = False

        if front_distance < self.front_distance_threshold:
            override_active = True
            command.angular.z = self.turn_speed if left_distance >= right_distance else -self.turn_speed
            estop = self.publish_estop
        elif front_distance < self.slow_distance_threshold:
            override_active = True
            command.linear.x = self.linear_speed
            command.angular.z = (self.turn_speed * 0.5) if left_distance >= right_distance else (-self.turn_speed * 0.5)

        if override_active:
            self.cmd_publisher.publish(command)
        self.override_publisher.publish(Bool(data=override_active))
        if self.publish_estop and estop:
            self.estop_publisher.publish(Bool(data=True))

    def _extract_distances(self, msg: LaserScan) -> Tuple[Optional[float], float, float]:
        front_samples: List[float] = []
        left_samples: List[float] = []
        right_samples: List[float] = []
        half_window = math.radians(self.front_angle_deg)

        angle = msg.angle_min
        for distance in msg.ranges:
            if math.isinf(distance) or math.isnan(distance):
                angle += msg.angle_increment
                continue
            if msg.range_min < distance < msg.range_max:
                relative_angle = self._angle_delta(angle, self.front_center_rad)
                if abs(relative_angle) <= half_window:
                    front_samples.append(distance)
                elif 0.0 < relative_angle <= math.pi / 2.0:
                    left_samples.append(distance)
                elif -math.pi / 2.0 <= relative_angle < 0.0:
                    right_samples.append(distance)
            angle += msg.angle_increment

        front_distance = min(front_samples) if front_samples else None
        left_distance = min(left_samples) if left_samples else float('inf')
        right_distance = min(right_samples) if right_samples else float('inf')
        return front_distance, left_distance, right_distance

    @staticmethod
    def _angle_delta(angle: float, center: float) -> float:
        return math.atan2(math.sin(angle - center), math.cos(angle - center))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AvoidanceNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
