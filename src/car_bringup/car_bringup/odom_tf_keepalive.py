"""Keep the odom-to-base TF available for Nav2 while the car is stationary."""

from __future__ import annotations

from typing import Optional, Sequence

import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from tf2_ros import TransformBroadcaster


class OdomTfKeepalive(Node):
    """Republish the latest EKF odometry pose as a fresh dynamic transform.

    The X3 firmware may pause odometry messages when the chassis is still.
    Nav2 creates a new TF buffer when navigation starts, so it otherwise has
    no odom -> base_footprint transform to initialise its costmaps with.
    """

    def __init__(self) -> None:
        super().__init__('odom_tf_keepalive')
        self.declare_parameter('odom_topic', '/odom')
        self.declare_parameter('odom_frame', 'odom')
        self.declare_parameter('base_frame', 'base_footprint')
        self.declare_parameter('publish_rate_hz', 20.0)
        self._transform = TransformStamped()
        self._transform.header.frame_id = str(self.get_parameter('odom_frame').value)
        self._transform.child_frame_id = str(self.get_parameter('base_frame').value)
        self._transform.transform.rotation.w = 1.0
        self._has_ekf_pose = False
        self._broadcaster = TransformBroadcaster(self)
        self.create_subscription(
            Odometry,
            str(self.get_parameter('odom_topic').value),
            self._on_odom,
            qos_profile_sensor_data,
        )
        rate = max(1.0, float(self.get_parameter('publish_rate_hz').value))
        self.create_timer(1.0 / rate, self._publish)

    def _on_odom(self, message: Odometry) -> None:
        if message.header.frame_id:
            self._transform.header.frame_id = message.header.frame_id
        if message.child_frame_id:
            self._transform.child_frame_id = message.child_frame_id
        self._transform.transform.translation.x = message.pose.pose.position.x
        self._transform.transform.translation.y = message.pose.pose.position.y
        self._transform.transform.translation.z = message.pose.pose.position.z
        self._transform.transform.rotation = message.pose.pose.orientation
        self._has_ekf_pose = True

    def _publish(self) -> None:
        self._transform.header.stamp = self.get_clock().now().to_msg()
        self._broadcaster.sendTransform(self._transform)
        if not self._has_ekf_pose:
            self.get_logger().debug('publishing initial odom identity until EKF emits odometry')


def main(args: Optional[Sequence[str]] = None) -> None:
    rclpy.init(args=args)
    node = OdomTfKeepalive()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
