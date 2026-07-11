from __future__ import annotations

import math
from typing import Optional, Sequence

import rclpy
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String


class GoalPublisher(Node):
    def __init__(self) -> None:
        super().__init__('goal_publisher')
        self.declare_parameter('frame_id', 'map')
        self.declare_parameter('goal_topic', '/goal_pose')
        self.declare_parameter('x', 0.0)
        self.declare_parameter('y', 0.0)
        self.declare_parameter('yaw', 0.0)
        self.declare_parameter('send_on_start', True)
        self.declare_parameter('send_action_goal', True)
        self.declare_parameter('action_name', 'navigate_to_pose')
        self.declare_parameter('mode_topic', '/mode_select')
        self.declare_parameter('navigation_mode', 'nav')

        self.frame_id = str(self.get_parameter('frame_id').value)
        self.goal_topic = str(self.get_parameter('goal_topic').value)
        self.send_on_start = bool(self.get_parameter('send_on_start').value)
        self.send_action_goal = bool(self.get_parameter('send_action_goal').value)
        action_name = str(self.get_parameter('action_name').value)

        self.publisher = self.create_publisher(PoseStamped, self.goal_topic, 10)
        self.mode_publisher = self.create_publisher(
            String, str(self.get_parameter('mode_topic').value), 10
        )
        self.action_client = ActionClient(self, NavigateToPose, action_name)
        self._published_visual_goal = False
        self._action_goal_sent = False
        self._navigation_mode_published = False

        if self.send_on_start:
            self.create_timer(0.5, self._send_once)

    def _send_once(self) -> None:
        if self._action_goal_sent:
            return
        if not self._navigation_mode_published:
            mode = str(self.get_parameter('navigation_mode').value).strip().lower()
            self.mode_publisher.publish(String(data=mode))
            self._navigation_mode_published = True
            self.get_logger().info(f'Selected {mode} control mode for navigation')
        goal = self._build_goal(
            float(self.get_parameter('x').value),
            float(self.get_parameter('y').value),
            float(self.get_parameter('yaw').value),
        )
        if not self._published_visual_goal:
            self.publisher.publish(goal)
            self._published_visual_goal = True
            self.get_logger().info(
                f'Published goal_pose x={goal.pose.position.x:.2f}, y={goal.pose.position.y:.2f}'
            )
        if self.send_action_goal:
            self._send_action_goal(goal)
        else:
            self._action_goal_sent = True

    def _send_action_goal(self, pose: PoseStamped) -> None:
        if not self.action_client.wait_for_server(timeout_sec=2.0):
            self.get_logger().warn('navigate_to_pose action server not available yet; will retry')
            return
        goal = NavigateToPose.Goal()
        goal.pose = pose
        self.action_client.send_goal_async(goal)
        self._action_goal_sent = True
        self.get_logger().info('Sent NavigateToPose action goal')

    def _build_goal(self, x: float, y: float, yaw: float) -> PoseStamped:
        goal = PoseStamped()
        goal.header.frame_id = self.frame_id
        goal.header.stamp = self.get_clock().now().to_msg()
        goal.pose.position.x = x
        goal.pose.position.y = y
        goal.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.orientation.w = math.cos(yaw / 2.0)
        return goal


def main(args: Optional[Sequence[str]] = None) -> None:
    rclpy.init(args=args)
    node = GoalPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
