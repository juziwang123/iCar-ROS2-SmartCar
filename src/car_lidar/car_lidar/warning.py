import math
from typing import List, Optional, Tuple

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool, String


class WarningNode(Node):
    def __init__(self) -> None:
        super().__init__('lidar_warning')
        self.declare_parameter('scan_topic', '/scan')
        self.declare_parameter('warning_topic', '/lidar/warning')
        self.declare_parameter('state_topic', '/lidar/warning_state')
        self.declare_parameter('buzzer_topic', '/Buzzer')
        self.declare_parameter('output_topic', '/cmd_vel_lidar')
        self.declare_parameter('override_topic', '/lidar/override_active')
        self.declare_parameter('warning_distance', 0.55)
        self.declare_parameter('clear_distance', 0.65)
        self.declare_parameter('front_angle_deg', 40.0)
        self.declare_parameter('front_center_deg', 180.0)
        self.declare_parameter('enable_control', False)
        self.declare_parameter('turn_speed', 0.5)

        self.warning_distance = float(self.get_parameter('warning_distance').value)
        self.clear_distance = float(self.get_parameter('clear_distance').value)
        self.front_angle_deg = float(self.get_parameter('front_angle_deg').value)
        self.front_center_deg = float(self.get_parameter('front_center_deg').value)
        self.front_center_rad = math.radians(self.front_center_deg)
        self.enable_control = bool(self.get_parameter('enable_control').value)
        self.turn_speed = float(self.get_parameter('turn_speed').value)
        self.warning_active = False

        self.warning_publisher = self.create_publisher(Bool, str(self.get_parameter('warning_topic').value), 10)
        self.state_publisher = self.create_publisher(String, str(self.get_parameter('state_topic').value), 10)
        self.buzzer_publisher = self.create_publisher(Bool, str(self.get_parameter('buzzer_topic').value), 10)
        self.cmd_publisher = self.create_publisher(Twist, str(self.get_parameter('output_topic').value), 10)
        self.override_publisher = self.create_publisher(Bool, str(self.get_parameter('override_topic').value), 10)
        self.create_subscription(LaserScan, str(self.get_parameter('scan_topic').value), self._on_scan, 10)
        self.get_logger().info(
            f'Lidar warning started: front_center_deg={self.front_center_deg}, '
            f'warning_distance={self.warning_distance}'
        )

    def _on_scan(self, msg: LaserScan) -> None:
        front, left, right = self._extract_distances(msg)
        if front is None:
            return

        threshold = self.clear_distance if self.warning_active else self.warning_distance
        self.warning_active = front <= threshold
        side = 'left_clearer' if left >= right else 'right_clearer'
        state = 'clear'
        if self.warning_active:
            state = f'warning front={front:.2f} {side}'

        self.warning_publisher.publish(Bool(data=self.warning_active))
        self.state_publisher.publish(String(data=state))
        self.buzzer_publisher.publish(Bool(data=self.warning_active))

        if self.enable_control:
            command = Twist()
            if self.warning_active:
                command.angular.z = self.turn_speed if left >= right else -self.turn_speed
            self.cmd_publisher.publish(command)
            self.override_publisher.publish(Bool(data=self.warning_active))

    def _extract_distances(self, msg: LaserScan) -> Tuple[Optional[float], float, float]:
        front_samples: List[float] = []
        left_samples: List[float] = []
        right_samples: List[float] = []
        half_window = math.radians(self.front_angle_deg)
        angle = msg.angle_min
        for distance in msg.ranges:
            if math.isfinite(distance) and msg.range_min < distance < msg.range_max:
                relative_angle = self._angle_delta(angle, self.front_center_rad)
                if abs(relative_angle) <= half_window:
                    front_samples.append(distance)
                elif 0.0 < relative_angle <= math.pi / 2.0:
                    left_samples.append(distance)
                elif -math.pi / 2.0 <= relative_angle < 0.0:
                    right_samples.append(distance)
            angle += msg.angle_increment
        return (
            min(front_samples) if front_samples else None,
            min(left_samples) if left_samples else float('inf'),
            min(right_samples) if right_samples else float('inf'),
        )

    @staticmethod
    def _angle_delta(angle: float, center: float) -> float:
        return math.atan2(math.sin(angle - center), math.cos(angle - center))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = WarningNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
