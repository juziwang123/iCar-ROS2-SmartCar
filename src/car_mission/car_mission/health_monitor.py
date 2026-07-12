"""P5 sensor freshness monitor with fail-safe output for the control mux."""

from __future__ import annotations

import json
import time
from typing import Dict

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import Image, LaserScan
from std_msgs.msg import Bool, String


class HealthMonitor(Node):
    def __init__(self) -> None:
        super().__init__('health_monitor')
        self.declare_parameter('scan_topic', '/scan')
        self.declare_parameter('image_topic', '/camera/color/image_raw')
        self.declare_parameter('odometry_topic', '/odom')
        self.declare_parameter('sensor_fault_topic', '/system/sensor_fault')
        self.declare_parameter('health_topic', '/system/health')
        self.declare_parameter('scan_timeout_sec', 1.0)
        self.declare_parameter('image_timeout_sec', 1.5)
        self.declare_parameter('odometry_timeout_sec', 1.0)
        self.declare_parameter('startup_grace_sec', 5.0)
        self.declare_parameter('check_rate_hz', 5.0)
        self.started_at = time.monotonic()
        self.last_seen: Dict[str, float] = {}
        self.fault_pub = self.create_publisher(Bool, str(self.get_parameter('sensor_fault_topic').value), 10)
        self.health_pub = self.create_publisher(String, str(self.get_parameter('health_topic').value), 10)
        self.create_subscription(LaserScan, str(self.get_parameter('scan_topic').value), lambda _: self._seen('scan'), 10)
        self.create_subscription(Image, str(self.get_parameter('image_topic').value), lambda _: self._seen('image'), 10)
        self.create_subscription(Odometry, str(self.get_parameter('odometry_topic').value), lambda _: self._seen('odometry'), 10)
        self.create_timer(1.0 / max(0.1, float(self.get_parameter('check_rate_hz').value)), self._publish_health)

    def _seen(self, name: str) -> None:
        self.last_seen[name] = time.monotonic()

    def _publish_health(self) -> None:
        now = time.monotonic()
        timeouts = {
            'scan': float(self.get_parameter('scan_timeout_sec').value),
            'image': float(self.get_parameter('image_timeout_sec').value),
            'odometry': float(self.get_parameter('odometry_timeout_sec').value),
        }
        healthy = {
            name: (now - self.last_seen[name] <= limit) if name in self.last_seen else False
            for name, limit in timeouts.items()
        }
        in_grace = now - self.started_at < float(self.get_parameter('startup_grace_sec').value)
        fault = not all(healthy.values()) and not in_grace
        self.fault_pub.publish(Bool(data=fault))
        self.health_pub.publish(String(data=json.dumps({
            'healthy': not fault,
            'startup_grace_active': in_grace,
            'sensors': healthy,
        }, separators=(',', ':'))))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = HealthMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
