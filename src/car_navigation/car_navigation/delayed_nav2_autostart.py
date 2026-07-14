"""Activate Nav2 after its TF listeners have joined the running graph."""

from __future__ import annotations

from typing import Optional, Sequence

import rclpy
from nav2_msgs.srv import ManageLifecycleNodes
from rclpy.node import Node


class DelayedNav2Autostart(Node):
    """Avoid the X3/Foxy lifecycle race with the persistent odom transform."""

    def __init__(self) -> None:
        super().__init__('delayed_nav2_autostart')
        self.declare_parameter('delay_sec', 2.5)
        self._service_names = iter((
            '/lifecycle_manager_localization/manage_nodes',
            '/lifecycle_manager_navigation/manage_nodes',
        ))
        self._client = None
        self._timer = self.create_timer(float(self.get_parameter('delay_sec').value), self._begin)

    def _begin(self) -> None:
        self._timer.cancel()
        self._start_next()

    def _start_next(self) -> None:
        try:
            service_name = next(self._service_names)
        except StopIteration:
            self.get_logger().info('Nav2 lifecycle managers are active')
            return
        self._client = self.create_client(ManageLifecycleNodes, service_name)
        if not self._client.wait_for_service(timeout_sec=10.0):
            self.get_logger().error(f'Nav2 lifecycle manager unavailable: {service_name}')
            return
        request = ManageLifecycleNodes.Request()
        request.command = ManageLifecycleNodes.Request.STARTUP
        future = self._client.call_async(request)
        future.add_done_callback(self._on_started)

    def _on_started(self, future) -> None:
        try:
            response = future.result()
            if not response.success:
                self.get_logger().error('Nav2 lifecycle manager rejected startup')
                return
        except Exception as exc:
            self.get_logger().error(f'Nav2 lifecycle startup failed: {exc}')
            return
        self._start_next()


def main(args: Optional[Sequence[str]] = None) -> None:
    rclpy.init(args=args)
    node = DelayedNav2Autostart()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
