"""Long-lived, safety-first manager for mutually-exclusive runtime profiles."""

from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from typing import Dict, Iterable, Optional, Sequence, Set, Tuple

import rclpy
from car_interfaces.msg import RuntimeStatus
from car_interfaces.srv import SetRuntimeProfile
from geometry_msgs.msg import Twist
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String

from .runtime_core import (
    RuntimeProfileError,
    RuntimeProfileRequest,
    profile_launch_arguments,
    validate_runtime_files,
)


class NodeManager(Node):
    """Own profile processes while the hardware/control foundation stays alive.

    The node deliberately does not clear emergency stop.  Every transition
    selects manual control and publishes zero velocity before the previous
    profile is stopped, and does the same on every failure path.
    """

    def __init__(self) -> None:
        super().__init__('node_manager')
        self._declare_parameters()
        self._lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._transition_thread: Optional[threading.Thread] = None
        self._profile_process: Optional[subprocess.Popen] = None
        self._profile_log = None
        self._generation = 0
        self._active_profile = 'idle'
        self._requested_profile = 'idle'
        self._transition_state = 'IDLE'
        self._ready = True
        self._message = 'runtime manager started; idle profile is active'
        self._topic_seen_at: Dict[str, float] = {'/scan': 0.0, '/odom': 0.0, '/map': 0.0}

        status_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._status_pub = self.create_publisher(
            RuntimeStatus, self._topic('runtime_status_topic'), status_qos
        )
        self._manual_pub = self.create_publisher(Twist, self._topic('manual_topic'), 10)
        self._mode_pub = self.create_publisher(String, self._topic('mode_topic'), 10)
        self._service = self.create_service(
            SetRuntimeProfile, self._topic('runtime_service'), self._on_set_profile
        )
        self.create_subscription(LaserScan, '/scan', lambda _: self._mark_topic('/scan'), 10)
        self.create_subscription(Odometry, '/odom', lambda _: self._mark_topic('/odom'), 10)
        self.create_subscription(OccupancyGrid, '/map', lambda _: self._mark_topic('/map'), 10)
        self._publish_status()

        initial_profile = str(self.get_parameter('initial_profile').value).strip().lower()
        self._initial_timer = None
        if initial_profile != 'idle':
            self._initial_timer = self.create_timer(0.5, self._start_initial_profile)

    def _declare_parameters(self) -> None:
        self.declare_parameter('runtime_service', '/runtime/set_profile')
        self.declare_parameter('runtime_status_topic', '/runtime/status')
        self.declare_parameter('manual_topic', '/cmd_vel_manual')
        self.declare_parameter('mode_topic', '/mode_select')
        self.declare_parameter('profile_launch_package', 'car_bringup')
        self.declare_parameter('profile_launch_file', 'runtime_profile.launch.py')
        self.declare_parameter('ros2_command', 'ros2')
        self.declare_parameter('profile_ready_timeout_sec', 45.0)
        self.declare_parameter('profile_shutdown_timeout_sec', 10.0)
        self.declare_parameter('readiness_poll_interval_sec', 0.5)
        self.declare_parameter('logs_root', '~/.icar/logs/runtime_profiles')
        self.declare_parameter('initial_profile', 'idle')
        self.declare_parameter('initial_map_path', '')
        self.declare_parameter('initial_route_file', '')
        self.declare_parameter('initial_use_yolo', False)

    def _topic(self, parameter: str) -> str:
        return str(self.get_parameter(parameter).value)

    def _mark_topic(self, topic: str) -> None:
        with self._lock:
            self._topic_seen_at[topic] = time.monotonic()

    def _start_initial_profile(self) -> None:
        # A one-shot timer gives the launch system time to create the base,
        # control and APP bridge nodes before a profile process is requested.
        if self._initial_timer is not None:
            self._initial_timer.cancel()
            self._initial_timer = None
        profile = str(self.get_parameter('initial_profile').value).strip().lower()
        request = RuntimeProfileRequest(
            profile,
            str(self.get_parameter('initial_map_path').value)
            if profile in {'navigation', 'mission'} else '',
            str(self.get_parameter('initial_route_file').value) if profile == 'mission' else '',
            bool(self.get_parameter('initial_use_yolo').value) if profile == 'mission' else False,
        )
        try:
            self._queue_transition(self._complete_defaults(request))
        except RuntimeProfileError as exc:
            self._set_status('idle', request.profile, 'FAILED', False, f'initial profile rejected: {exc}')

    def _on_set_profile(self, request, response):
        candidate = RuntimeProfileRequest(
            request.profile,
            request.map_path,
            request.route_file,
            request.use_yolo,
        )
        try:
            generation = self._queue_transition(self._complete_defaults(candidate))
        except RuntimeProfileError as exc:
            response.accepted = False
            response.generation = self._generation
            response.state = self._transition_state
            response.message = str(exc)
            return response
        response.accepted = True
        response.generation = generation
        response.state = 'STARTING'
        response.message = 'runtime profile transition accepted; watch /runtime/status for completion'
        return response

    def _complete_defaults(self, request: RuntimeProfileRequest) -> RuntimeProfileRequest:
        """Apply launch-configured defaults only where a caller omitted them."""
        profile = request.profile.strip().lower()
        if profile == 'idle':
            return request
        map_path = request.map_path
        route_file = request.route_file
        if profile in {'navigation', 'mission'} and not map_path:
            map_path = str(self.get_parameter('initial_map_path').value)
        if profile == 'mission' and not route_file:
            route_file = str(self.get_parameter('initial_route_file').value)
        return RuntimeProfileRequest(profile, map_path, route_file, request.use_yolo)

    def _queue_transition(self, request: RuntimeProfileRequest) -> int:
        request = validate_runtime_files(request)
        with self._lock:
            if self._shutdown_event.is_set():
                raise RuntimeProfileError('runtime manager is shutting down')
            if self._transition_thread is not None and self._transition_thread.is_alive():
                raise RuntimeProfileError('another runtime profile transition is already in progress')
            if self._ready and self._active_profile == request.profile:
                raise RuntimeProfileError(f'{request.profile} is already active')
            self._generation += 1
            generation = self._generation
            self._requested_profile = request.profile
            self._transition_state = 'STARTING'
            self._ready = False
            self._message = f'accepted transition to {request.profile}'
            self._transition_thread = threading.Thread(
                target=self._run_transition,
                args=(request, generation),
                name=f'runtime-transition-{generation}',
                daemon=True,
            )
        self._publish_status()
        self._transition_thread.start()
        return generation

    def _run_transition(self, request: RuntimeProfileRequest, generation: int) -> None:
        try:
            self._stop_motion()
            if self._profile_process is not None:
                self._set_status(
                    self._active_profile, request.profile, 'STOPPING', False,
                    f'stopping {self._active_profile} before starting {request.profile}', generation,
                )
                self._stop_profile_process()
            if request.profile == 'idle':
                self._set_status('idle', 'idle', 'IDLE', True, 'idle profile is active', generation)
                return

            self._set_status(
                self._active_profile, request.profile, 'STARTING', False,
                f'starting {request.profile} profile', generation,
            )
            started_at = time.monotonic()
            self._start_profile_process(request, generation)
            self._wait_for_profile_ready(request.profile, started_at)
            self._set_status(
                request.profile, request.profile, 'READY', True,
                f'{request.profile} profile is ready', generation,
            )
        except Exception as exc:  # Keep a failed profile from remaining partly active.
            self.get_logger().error(f'runtime transition {generation} failed: {exc}')
            self._stop_profile_process()
            self._stop_motion()
            self._set_status(
                'idle', request.profile, 'FAILED', False,
                f'{request.profile} failed and was stopped: {exc}', generation,
            )

    def _start_profile_process(self, request: RuntimeProfileRequest, generation: int) -> None:
        launch_args = profile_launch_arguments(request)
        command = [
            str(self.get_parameter('ros2_command').value), 'launch',
            str(self.get_parameter('profile_launch_package').value),
            str(self.get_parameter('profile_launch_file').value),
        ]
        command.extend(f'{key}:={value}' for key, value in sorted(launch_args.items()))
        log_root = Path(str(self.get_parameter('logs_root').value)).expanduser().resolve()
        log_root.mkdir(parents=True, exist_ok=True)
        log_path = log_root / f'{generation:04d}_{request.profile}.log'
        self._profile_log = log_path.open('a', encoding='utf-8')
        self._profile_log.write(f'command: {command!r}\n')
        self._profile_log.flush()
        environment = dict(os.environ)
        environment['PYTHONUNBUFFERED'] = '1'
        try:
            self._profile_process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=self._profile_log,
                stderr=subprocess.STDOUT,
                env=environment,
                start_new_session=True,
            )
        except Exception:
            self._close_profile_log()
            raise
        self.get_logger().info(f'started {request.profile} profile pid={self._profile_process.pid}')

    def _wait_for_profile_ready(self, profile: str, started_at: float) -> None:
        deadline = time.monotonic() + float(self.get_parameter('profile_ready_timeout_sec').value)
        interval = max(0.1, float(self.get_parameter('readiness_poll_interval_sec').value))
        missing: Tuple[str, ...] = ()
        while time.monotonic() < deadline:
            process = self._profile_process
            if process is None:
                raise RuntimeProfileError('profile process disappeared')
            return_code = process.poll()
            if return_code is not None:
                raise RuntimeProfileError(f'profile process exited with code {return_code}')
            missing = self._missing_readiness(profile, started_at)
            if not missing:
                return
            if self._shutdown_event.wait(interval):
                raise RuntimeProfileError('runtime manager is shutting down')
        detail = ', '.join(missing) if missing else 'no readiness data received'
        raise RuntimeProfileError(f'{profile} readiness timed out: {detail}')

    def _missing_readiness(self, profile: str, started_at: float) -> Tuple[str, ...]:
        names = {name for name, _namespace in self.get_node_names_and_namespaces()}
        topics = {name for name, _types in self.get_topic_names_and_types()}
        services = {name for name, _types in self.get_service_names_and_types()}
        action_getter = getattr(self, 'get_action_server_names_and_types', None)
        actions = {name for name, _types in action_getter()} if callable(action_getter) else set()

        required_nodes: Set[str] = set()
        required_topics: Set[str] = set()
        required_services: Set[str] = set()
        required_actions: Set[str] = set()
        fresh_topics: Set[str] = {'/scan', '/odom'}
        if profile == 'mapping':
            required_nodes |= {'sync_slam_toolbox_node', 'map_saver'}
            required_services.add('/map_saver/save_map')
            fresh_topics.add('/map')
        elif profile == 'navigation':
            required_nodes |= {'amcl', 'bt_navigator', 'controller_server', 'planner_server', 'map_server'}
            required_actions.add('/navigate_to_pose')
            fresh_topics.add('/map')
        elif profile == 'mission':
            required_nodes |= {
                'amcl', 'bt_navigator', 'controller_server', 'planner_server', 'map_server',
                'mission_manager', 'checkpoint_verifier', 'inspection_executor',
            }
            required_actions |= {'/navigate_to_pose', '/execute_patrol'}
            fresh_topics.add('/map')
        else:
            return (f'unsupported profile {profile}',)

        missing = []
        missing.extend(f'node:{name}' for name in sorted(required_nodes - names))
        missing.extend(f'topic:{name}' for name in sorted(required_topics - topics))
        missing.extend(f'service:{name}' for name in sorted(required_services - services))
        for action in sorted(required_actions):
            action_visible = action in actions
            # Foxy graph introspection does not expose action names on every
            # RMW implementation; the status topic is its portable fallback.
            if not action_visible and f'{action}/_action/status' not in topics:
                missing.append(f'action:{action}')
        with self._lock:
            seen_at = dict(self._topic_seen_at)
        for topic in sorted(fresh_topics):
            if seen_at.get(topic, 0.0) < started_at:
                missing.append(f'fresh:{topic}')
        return tuple(missing)

    def _stop_profile_process(self) -> None:
        process, self._profile_process = self._profile_process, None
        if process is None:
            self._close_profile_log()
            return
        if process.poll() is None:
            self._signal_process_group(process, signal.SIGINT)
            try:
                process.wait(timeout=float(self.get_parameter('profile_shutdown_timeout_sec').value))
            except subprocess.TimeoutExpired:
                self.get_logger().warning(f'profile pid={process.pid} ignored SIGINT; sending SIGTERM')
                self._signal_process_group(process, signal.SIGTERM)
                try:
                    process.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    self.get_logger().error(f'profile pid={process.pid} ignored SIGTERM; sending SIGKILL')
                    self._signal_process_group(process, signal.SIGKILL)
                    process.wait(timeout=3.0)
        self._close_profile_log()

    @staticmethod
    def _signal_process_group(process: subprocess.Popen, signal_number: int) -> None:
        if os.name == 'posix':
            os.killpg(process.pid, signal_number)
        else:  # The manager runs on Jetson/Linux; retain a useful local fallback.
            process.send_signal(signal_number)

    def _close_profile_log(self) -> None:
        if self._profile_log is not None:
            self._profile_log.close()
            self._profile_log = None

    def _stop_motion(self) -> None:
        # Do not publish to /emergency_stop here: only an operator may clear it.
        self._mode_pub.publish(String(data='manual'))
        for _ in range(3):
            self._manual_pub.publish(Twist())
            time.sleep(0.05)

    def _set_status(
        self,
        active_profile: str,
        requested_profile: str,
        state: str,
        ready: bool,
        message: str,
        generation: Optional[int] = None,
    ) -> None:
        with self._lock:
            self._active_profile = active_profile
            self._requested_profile = requested_profile
            self._transition_state = state
            self._ready = ready
            self._message = message
            if generation is not None:
                self._generation = generation
        self._publish_status()

    def _publish_status(self) -> None:
        with self._lock:
            message = RuntimeStatus()
            message.active_profile = self._active_profile
            message.requested_profile = self._requested_profile
            message.state = self._transition_state
            message.generation = self._generation
            message.ready = self._ready
            message.message = self._message
        self._status_pub.publish(message)

    def shutdown(self) -> None:
        self._shutdown_event.set()
        self._stop_motion()
        self._stop_profile_process()


def main(args: Optional[Sequence[str]] = None) -> None:
    rclpy.init(args=args)
    node = NodeManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        rclpy.shutdown()
