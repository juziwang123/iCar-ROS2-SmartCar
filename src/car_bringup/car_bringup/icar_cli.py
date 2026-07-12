"""Unified iCar startup command and a deliberately narrow operator console."""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional, Sequence

from .cli_core import CliError, build_launch_profile, finite_motion, parse_console_command, validate_mode


def _start(args: argparse.Namespace) -> int:
    try:
        profile = build_launch_profile(
            args.profile, map_file=args.map, route_file=args.route,
            use_app_bridge=args.app_bridge, use_yolo=args.yolo, use_rviz=args.rviz,
        )
    except CliError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    command = ['ros2', 'launch', 'car_bringup', 'bringup.launch.py']
    command.extend(f'{key}:={value}' for key, value in sorted(profile.arguments.items()))
    print('Starting iCar profile:', profile.name)
    print(' '.join(command))
    if args.dry_run:
        return 0
    try:
        return subprocess.call(command)
    except FileNotFoundError:
        print('ros2 was not found. Source the ROS installation and workspace first.', file=sys.stderr)
        return 127


class OperatorConsole:
    """Mission-only console: it has no direct velocity or arbitrary ROS access."""

    def __init__(self, database_path: str, max_linear_speed: float, max_angular_speed: float) -> None:
        import rclpy
        from car_interfaces.action import ExecutePatrol
        from car_interfaces.msg import MissionStatus, PatrolEvent
        from car_interfaces.srv import MissionControl
        from geometry_msgs.msg import PoseStamped, Twist
        from nav2_msgs.action import NavigateToPose
        from rclpy.action import ActionClient
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.node import Node
        from std_msgs.msg import Bool
        from std_msgs.msg import String

        class ConsoleNode(Node):
            pass

        self.rclpy = rclpy
        self.ExecutePatrol = ExecutePatrol
        self.MissionControl = MissionControl
        self.NavigateToPose = NavigateToPose
        self.node = ConsoleNode('icar_operator_console')
        self.mission_client = ActionClient(self.node, ExecutePatrol, 'execute_patrol')
        self.navigation_client = ActionClient(self.node, NavigateToPose, 'navigate_to_pose')
        self.control_client = self.node.create_client(MissionControl, '/mission/control')
        self.estop_pub = self.node.create_publisher(Bool, '/emergency_stop', 10)
        self.manual_pub = self.node.create_publisher(Twist, '/cmd_vel_manual', 10)
        self.mode_pub = self.node.create_publisher(String, '/mode_select', 10)
        self.Bool = Bool
        self.String = String
        self.Twist = Twist
        self.PoseStamped = PoseStamped
        self.database_path = database_path
        self.max_linear_speed = max_linear_speed
        self.max_angular_speed = max_angular_speed
        self.last_mission_id = ''
        self.mission_state = 'IDLE'
        self.last_status = 'No mission status received yet.'
        self.mode = 'manual'
        self.effective_estop_active = False
        self.lidar_override_active = False
        self.person_estop_active = False
        self.health = 'unknown'
        self.direct_nav_goal = None
        self.node.create_subscription(MissionStatus, '/mission/status', self._on_status, 10)
        self.node.create_subscription(PatrolEvent, '/mission/event', self._on_event, 10)
        self.node.create_subscription(String, '/mode_select', self._on_mode, 10)
        self.node.create_subscription(Bool, '/control/effective_estop', self._on_effective_estop, 10)
        self.node.create_subscription(Bool, '/lidar/override_active', self._on_lidar_override, 10)
        self.node.create_subscription(Bool, '/vision/person_estop', self._on_person_estop, 10)
        self.node.create_subscription(String, '/system/health', self._on_health, 10)
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.node)
        self.spin_thread = threading.Thread(target=self.executor.spin, daemon=True)
        self.spin_thread.start()

    def close(self) -> None:
        self.executor.shutdown()
        self.node.destroy_node()

    def _on_status(self, message) -> None:
        self.last_mission_id = message.mission_id or self.last_mission_id
        self.mission_state = message.state.strip().upper()
        self.last_status = (
            f'{message.mission_id} {message.state} checkpoint={message.checkpoint_id} '
            f'progress={message.progress:.0%} retries={message.retry_count}: {message.detail}'
        )

    def _on_event(self, message) -> None:
        self.node.get_logger().info(f'[{message.code}] {message.detail}')

    def _on_mode(self, message) -> None:
        self.mode = message.data.strip().lower()

    def _on_effective_estop(self, message) -> None:
        self.effective_estop_active = bool(message.data)

    def _on_lidar_override(self, message) -> None:
        self.lidar_override_active = bool(message.data)

    def _on_person_estop(self, message) -> None:
        self.person_estop_active = bool(message.data)

    def _on_health(self, message) -> None:
        self.health = message.data

    def run(self) -> int:
        print('iCar operator console. Type help for safe mission commands.')
        while True:
            try:
                command, values = parse_console_command(input('icar> '))
                if not command:
                    continue
                if command in {'quit', 'exit'}:
                    return 0
                self._execute(command, values)
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            except CliError as exc:
                print(f'Error: {exc}')

    def _execute(self, command: str, values: Sequence[str]) -> None:
        if command == 'help':
            print('status | mode manual|nav|vision|follow | move LINEAR ANGULAR | stop')
            print('nav X Y YAW | nav_cancel | start ROUTE [VERSION] [INDEX]')
            print('pause [MISSION_ID] | resume [MISSION_ID] | cancel [MISSION_ID]')
            print('estop on|off | report [MISSION_ID] | recoveries | quit')
        elif command == 'status':
            print(self.last_status)
            print(
                f'mode={self.mode} effective_estop={self.effective_estop_active} '
                f'lidar_override={self.lidar_override_active} person_estop={self.person_estop_active} '
                f'health={self.health}'
            )
        elif command == 'start':
            self._start_mission(values)
        elif command in {'pause', 'resume', 'cancel'}:
            if len(values) > 1:
                raise CliError(f'usage: {command} [MISSION_ID]')
            self._mission_control(command, values[0] if values else self.last_mission_id)
        elif command == 'estop':
            if len(values) != 1 or values[0].lower() not in {'on', 'off'}:
                raise CliError('usage: estop on|off')
            self.estop_pub.publish(self.Bool(data=values[0].lower() == 'on'))
            print('Emergency stop command sent; mission resume always requires a separate confirmation.')
        elif command == 'mode':
            if len(values) != 1:
                raise CliError('usage: mode manual|nav|vision|follow')
            mode = validate_mode(values[0])
            if self._mission_active() and not (
                self.mission_state == 'PAUSED' and mode == 'manual'
            ):
                raise CliError('an active mission owns the mode; pause it before local manual takeover')
            self.mode = mode
            self.mode_pub.publish(self.String(data=mode))
            print(f'Mode request sent: {mode}')
        elif command == 'move':
            self._move(values)
        elif command == 'stop':
            if values:
                raise CliError('usage: stop')
            self._publish_motion(0.0, 0.0)
            if self.direct_nav_goal is not None:
                self._cancel_navigation()
            print('Manual zero-velocity command sent. Use mission_pause for an active patrol.')
        elif command == 'nav':
            self._navigate(values)
        elif command == 'nav_cancel':
            if values:
                raise CliError('usage: nav_cancel')
            self._cancel_navigation()
        elif command == 'report':
            if len(values) > 1:
                raise CliError('usage: report [MISSION_ID]')
            self._report(values[0] if values else self.last_mission_id)
        elif command == 'recoveries':
            if values:
                raise CliError('usage: recoveries')
            from car_mission.mission_repository import MissionRepository
            for mission in MissionRepository(self.database_path).list_recoverable_missions():
                print(mission)

    def _start_mission(self, values: Sequence[str]) -> None:
        if not values or len(values) > 3:
            raise CliError('usage: start ROUTE [VERSION] [INDEX]')
        if not self.mission_client.wait_for_server(timeout_sec=2.0):
            raise CliError('execute_patrol action server is unavailable')
        goal = self.ExecutePatrol.Goal()
        goal.route_id = values[0]
        try:
            goal.route_version = int(values[1]) if len(values) > 1 else 0
            goal.start_checkpoint_index = int(values[2]) if len(values) > 2 else 0
        except ValueError as exc:
            raise CliError('VERSION and INDEX must be integers') from exc
        if goal.route_version < 0 or goal.start_checkpoint_index < 0:
            raise CliError('VERSION and INDEX cannot be negative')
        goal.loop = False
        self.mission_client.send_goal_async(goal).add_done_callback(
            lambda future: print('Mission accepted.' if future.result().accepted else 'Mission was rejected.')
        )

    def _move(self, values: Sequence[str]) -> None:
        if len(values) != 2:
            raise CliError('usage: move LINEAR_M_S ANGULAR_RAD_S')
        if self.mode != 'manual':
            raise CliError('switch to mode manual before sending manual velocity')
        if self.effective_estop_active:
            raise CliError('effective emergency stop is active')
        linear = finite_motion(values[0], 'linear', self.max_linear_speed)
        angular = finite_motion(values[1], 'angular', self.max_angular_speed)
        self._publish_motion(linear, angular)

    def _publish_motion(self, linear: float, angular: float) -> None:
        message = self.Twist()
        message.linear.x = linear
        message.angular.z = angular
        self.manual_pub.publish(message)

    def _navigate(self, values: Sequence[str]) -> None:
        if len(values) != 3:
            raise CliError('usage: nav X Y YAW')
        if self._mission_active():
            raise CliError('mission is active; use mission control instead of direct navigation')
        if self.mode != 'nav':
            raise CliError('switch to mode nav before sending a navigation goal')
        if self.effective_estop_active:
            raise CliError('effective emergency stop is active')
        x = finite_motion(values[0], 'x', 1000.0)
        y = finite_motion(values[1], 'y', 1000.0)
        yaw = finite_motion(values[2], 'yaw', 6.283185307179586)
        if not self.navigation_client.wait_for_server(timeout_sec=2.0):
            raise CliError('navigate_to_pose action server is unavailable')
        goal = self.NavigateToPose.Goal()
        goal.pose = self.PoseStamped()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self.node.get_clock().now().to_msg()
        goal.pose.pose.position.x, goal.pose.pose.position.y = x, y
        import math
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)
        self.navigation_client.send_goal_async(goal).add_done_callback(self._on_nav_goal_response)

    def _on_nav_goal_response(self, future) -> None:
        goal_handle = future.result()
        if not goal_handle.accepted:
            print('Navigation goal was rejected.')
            return
        self.direct_nav_goal = goal_handle
        print('Navigation goal accepted.')
        goal_handle.get_result_async().add_done_callback(self._on_nav_result)

    def _on_nav_result(self, future) -> None:
        self.direct_nav_goal = None
        try:
            print(f'Navigation finished with status {future.result().status}.')
        except Exception as exc:
            print(f'Navigation result error: {exc}')

    def _cancel_navigation(self) -> None:
        if self.direct_nav_goal is None:
            print('No direct navigation goal is active.')
            return
        self.direct_nav_goal.cancel_goal_async()
        print('Direct navigation cancellation requested.')

    def _mission_active(self) -> bool:
        return any(token in self.last_status.lower() for token in (
            'preparing', 'localizing', 'navigating', 'checking_in', 'capturing', 'inspecting',
            'recording', 'recovering', 'blocked', 'pausing', 'paused', 'waiting_operator', 'estopped',
        ))

    def _mission_control(self, command: str, mission_id: str) -> None:
        if not mission_id:
            raise CliError('mission_id is required; wait for status or specify it explicitly')
        if not self.control_client.wait_for_service(timeout_sec=2.0):
            raise CliError('mission control service is unavailable')
        request = self.MissionControl.Request()
        request.mission_id, request.command = mission_id, command
        future = self.control_client.call_async(request)
        future.add_done_callback(lambda result: print(result.result().message))

    def _report(self, mission_id: str) -> None:
        if not mission_id:
            raise CliError('mission_id is required')
        from car_mission.report_exporter import export_report
        from car_mission.mission_repository import MissionRepository
        report = MissionRepository(self.database_path).get_report(mission_id)
        path = export_report(report, str(Path(self.database_path).expanduser().parent / 'reports'))
        print(f'Report exported: {path}')


def _console(args: argparse.Namespace) -> int:
    if args.max_linear_speed <= 0.0 or args.max_angular_speed <= 0.0:
        print('Console speed limits must be positive.', file=sys.stderr)
        return 2
    try:
        import rclpy
    except ImportError:
        print('rclpy is unavailable. Run this command in a sourced ROS 2 workspace.', file=sys.stderr)
        return 127
    rclpy.init()
    console: Optional[OperatorConsole] = None
    try:
        console = OperatorConsole(args.database_path, args.max_linear_speed, args.max_angular_speed)
        return console.run()
    finally:
        if console is not None:
            console.close()
        rclpy.shutdown()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog='icar', description='iCar unified startup and safe operator console')
    subparsers = parser.add_subparsers(dest='command', required=True)
    start = subparsers.add_parser('start', help='launch a validated system profile')
    start.add_argument('profile', choices=('mapping', 'navigation', 'mission'))
    start.add_argument('--map', default='', help='Nav2 map YAML path')
    start.add_argument('--route', default='', help='mission route YAML path')
    start.add_argument('--app-bridge', action='store_true')
    start.add_argument('--yolo', action='store_true')
    start.add_argument('--rviz', action='store_true')
    start.add_argument('--dry-run', action='store_true')
    start.set_defaults(handler=_start)
    console = subparsers.add_parser('console', help='open the safe interactive mission console')
    console.add_argument('--database-path', default='~/.icar/icar.db')
    console.add_argument('--max-linear-speed', type=float, default=0.4)
    console.add_argument('--max-angular-speed', type=float, default=1.2)
    console.set_defaults(handler=_console)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == '__main__':
    raise SystemExit(main())
