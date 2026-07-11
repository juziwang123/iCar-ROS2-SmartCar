"""Small Nav2 Action adapter used exclusively by the mission manager."""

from __future__ import annotations

from typing import Any

from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient


class NavigationAdapter:
    def __init__(self, node, action_name: str, callback_group) -> None:
        self._client = ActionClient(
            node, NavigateToPose, action_name, callback_group=callback_group
        )

    def wait_for_server(self, timeout_sec: float) -> bool:
        return self._client.wait_for_server(timeout_sec=timeout_sec)

    def send_goal_async(self, pose) -> Any:
        goal = NavigateToPose.Goal()
        goal.pose = pose
        return self._client.send_goal_async(goal)

    @staticmethod
    def cancel(goal_handle: Any) -> None:
        if goal_handle is not None:
            goal_handle.cancel_goal_async()
