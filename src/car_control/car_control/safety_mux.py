from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import rclpy
from geometry_msgs.msg import Twist
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.time import Time
from std_msgs.msg import Bool
from std_msgs.msg import String


@dataclass
class TimedTwist:
    msg: Optional[Twist] = None
    stamp: Optional[Time] = None


class SafetyMux(Node):
    def __init__(self) -> None:
        super().__init__('safety_mux')
        self.declare_parameter('manual_topic', '/cmd_vel_manual')
        self.declare_parameter('nav_topic', '/cmd_vel_nav')
        self.declare_parameter('vision_topic', '/cmd_vel_vision')
        self.declare_parameter('lidar_topic', '/cmd_vel_lidar')
        self.declare_parameter('follow_topic', '/cmd_vel_follow')
        self.declare_parameter('lidar_override_topic', '/lidar/override_active')
        self.declare_parameter('mode_topic', '/mode_select')
        self.declare_parameter('estop_topic', '/emergency_stop')
        self.declare_parameter('output_topic', '/control/cmd_vel')
        self.declare_parameter('manual_timeout_sec', 0.6)
        self.declare_parameter('auto_timeout_sec', 0.6)
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('default_mode', 'manual')
        self.declare_parameter('allow_manual_escape_when_lidar_override', True)

        self.mode = str(self.get_parameter('default_mode').value)
        self.estop_active = False
        self.lidar_override_active = False
        self.manual = TimedTwist()
        self.nav = TimedTwist()
        self.vision = TimedTwist()
        self.lidar = TimedTwist()
        self.follow = TimedTwist()

        self.manual_timeout = Duration(seconds=float(self.get_parameter('manual_timeout_sec').value))
        self.auto_timeout = Duration(seconds=float(self.get_parameter('auto_timeout_sec').value))
        self.allow_manual_escape = bool(
            self.get_parameter('allow_manual_escape_when_lidar_override').value
        )

        self.publisher = self.create_publisher(Twist, str(self.get_parameter('output_topic').value), 10)
        self.create_subscription(Twist, str(self.get_parameter('manual_topic').value), self._on_manual, 10)
        self.create_subscription(Twist, str(self.get_parameter('nav_topic').value), self._on_nav, 10)
        self.create_subscription(Twist, str(self.get_parameter('vision_topic').value), self._on_vision, 10)
        self.create_subscription(Twist, str(self.get_parameter('lidar_topic').value), self._on_lidar, 10)
        self.create_subscription(Twist, str(self.get_parameter('follow_topic').value), self._on_follow, 10)
        self.create_subscription(Bool, str(self.get_parameter('lidar_override_topic').value), self._on_lidar_override, 10)
        self.create_subscription(String, str(self.get_parameter('mode_topic').value), self._on_mode, 10)
        self.create_subscription(Bool, str(self.get_parameter('estop_topic').value), self._on_estop, 10)

        publish_period = 1.0 / float(self.get_parameter('publish_rate_hz').value)
        self.create_timer(publish_period, self._publish_selected_twist)
        self.get_logger().info(f'Safety mux started in {self.mode} mode')

    def _on_manual(self, msg: Twist) -> None:
        self.manual = TimedTwist(msg=msg, stamp=self.get_clock().now())

    def _on_nav(self, msg: Twist) -> None:
        self.nav = TimedTwist(msg=msg, stamp=self.get_clock().now())

    def _on_vision(self, msg: Twist) -> None:
        self.vision = TimedTwist(msg=msg, stamp=self.get_clock().now())

    def _on_lidar(self, msg: Twist) -> None:
        self.lidar = TimedTwist(msg=msg, stamp=self.get_clock().now())

    def _on_follow(self, msg: Twist) -> None:
        self.follow = TimedTwist(msg=msg, stamp=self.get_clock().now())

    def _on_mode(self, msg: String) -> None:
        mode = msg.data.strip()
        if not mode:
            return
        self.mode = mode
        self.get_logger().info(f'Mode switched to {self.mode}')

    def _on_lidar_override(self, msg: Bool) -> None:
        self.lidar_override_active = bool(msg.data)

    def _on_estop(self, msg: Bool) -> None:
        self.estop_active = bool(msg.data)
        if self.estop_active:
            self.get_logger().warn('Emergency stop activated')
        else:
            self.get_logger().info('Emergency stop released')

    def _publish_selected_twist(self) -> None:
        msg = Twist()
        if self.estop_active:
            self.publisher.publish(msg)
            return

        lidar_msg = self._fresh_message(self.lidar, self.auto_timeout)
        if self.lidar_override_active:
            manual_msg = self._fresh_message(self.manual, self.manual_timeout)
            if self.allow_manual_escape and self.mode == 'manual' and manual_msg is not None:
                self.publisher.publish(self._block_forward_motion(manual_msg))
                return
            self.publisher.publish(lidar_msg if lidar_msg is not None else msg)
            return

        selected = self._select_by_mode()
        if selected is not None:
            self.publisher.publish(selected)
            return

        self.publisher.publish(msg)

    def _select_by_mode(self) -> Optional[Twist]:
        if self.mode == 'nav':
            return self._fresh_message(self.nav, self.auto_timeout)
        if self.mode == 'vision':
            return self._fresh_message(self.vision, self.auto_timeout)
        if self.mode == 'follow':
            return self._fresh_message(self.follow, self.auto_timeout)
        return self._fresh_message(self.manual, self.manual_timeout)

    def _fresh_message(self, timed_twist: TimedTwist, timeout: Duration) -> Optional[Twist]:
        if timed_twist.msg is None or timed_twist.stamp is None:
            return None
        if self.get_clock().now() - timed_twist.stamp > timeout:
            return None
        return timed_twist.msg

    @staticmethod
    def _block_forward_motion(msg: Twist) -> Twist:
        output = Twist()
        output.linear.x = min(0.0, msg.linear.x)
        output.linear.y = msg.linear.y
        output.linear.z = msg.linear.z
        output.angular.x = msg.angular.x
        output.angular.y = msg.angular.y
        output.angular.z = msg.angular.z
        return output


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SafetyMux()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
