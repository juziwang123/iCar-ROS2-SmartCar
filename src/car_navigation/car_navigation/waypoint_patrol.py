from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import rclpy
import yaml
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String


class WaypointPatrol(Node):
    def __init__(self) -> None:
        super().__init__('waypoint_patrol')
        self.declare_parameter('frame_id', 'map')
        self.declare_parameter('goal_topic', '/goal_pose')
        self.declare_parameter('action_name', 'navigate_to_pose')
        self.declare_parameter('waypoints_file', '')
        self.declare_parameter('loop', True)
        self.declare_parameter('autoload', True)
        self.declare_parameter('mode_topic', '/mode_select')
        self.declare_parameter('navigation_mode', 'nav')

        self.frame_id = str(self.get_parameter('frame_id').value)
        self.goal_topic = str(self.get_parameter('goal_topic').value)
        self.loop = bool(self.get_parameter('loop').value)
        self.publisher = self.create_publisher(PoseStamped, self.goal_topic, 10)
        self.mode_publisher = self.create_publisher(
            String, str(self.get_parameter('mode_topic').value), 10
        )
        self.action_client = ActionClient(
            self,
            NavigateToPose,
            str(self.get_parameter('action_name').value),
        )

        self.waypoints: List[Dict[str, float]] = []
        self.current_index = 0
        if bool(self.get_parameter('autoload').value):
            self._load_waypoints()
            self.create_timer(0.5, self._start_if_ready)
        self._started = False
        self._action_sent_for_current = False

    def _load_waypoints(self) -> None:
        waypoints_file = str(self.get_parameter('waypoints_file').value)
        if not waypoints_file:
            self.get_logger().warn('No waypoints file configured')
            return
        data = yaml.safe_load(Path(waypoints_file).read_text(encoding='utf-8')) or {}
        self.waypoints = data.get('waypoints', [])
        self.get_logger().info(f'Loaded {len(self.waypoints)} waypoints')

    def _start_if_ready(self) -> None:
        if self._started or not self.waypoints:
            return
        if not self.action_client.wait_for_server(timeout_sec=1.0):
            return
        navigation_mode = str(self.get_parameter('navigation_mode').value).strip().lower()
        self.mode_publisher.publish(String(data=navigation_mode))
        self.get_logger().info(f'Selected {navigation_mode} control mode for waypoint patrol')
        self._started = True
        self._send_current_goal()

    def _send_current_goal(self) -> None:
        if not self.waypoints:
            return
        if self.current_index >= len(self.waypoints):
            if self.loop:
                self.current_index = 0
            else:
                self.get_logger().info('Waypoint patrol finished')
                return

        if not self.action_client.wait_for_server(timeout_sec=2.0):
            self.get_logger().warn('navigate_to_pose action server not available; will retry')
            return

        waypoint = self.waypoints[self.current_index]
        pose = self._build_goal(
            float(waypoint.get('x', 0.0)),
            float(waypoint.get('y', 0.0)),
            float(waypoint.get('yaw', 0.0)),
        )
        self.publisher.publish(pose)

        goal = NavigateToPose.Goal()
        goal.pose = pose
        future = self.action_client.send_goal_async(goal)
        future.add_done_callback(self._goal_response_callback)
        self._action_sent_for_current = True
        self.get_logger().info(f'Sent waypoint {self.current_index + 1}/{len(self.waypoints)}')

    def _goal_response_callback(self, future) -> None:
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn('Waypoint goal was rejected')
            return
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._result_callback)

    def _result_callback(self, future: Any) -> None:
        _ = future.result()
        self.current_index += 1
        self._action_sent_for_current = False
        self._send_current_goal()

    def _build_goal(self, x: float, y: float, yaw: float) -> PoseStamped:
        pose = PoseStamped()
        pose.header.frame_id = self.frame_id
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        return pose


def main(args: Optional[Sequence[str]] = None) -> None:
    rclpy.init(args=args)
    node = WaypointPatrol()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
