"""A safe, versioned TCP bridge from APPs to the iCar ROS 2 interfaces.

The wire format is JSON Lines: one UTF-8 JSON object per line.  The bridge
intentionally exposes named car capabilities instead of arbitrary ROS topic
access, so an APP cannot bypass the control mux or publish an unsafe message.
"""

from __future__ import annotations

import json
import math
import socket
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Set

import rclpy
from geometry_msgs.msg import PoseStamped, Twist
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import Bool, String

from .protocol import (
    PROTOCOL_VERSION,
    TELEMETRY_CHANNELS,
    VALID_MODES,
    ProtocolError,
    boolean,
    event,
    finite_number,
    response,
    string_list,
)


@dataclass(eq=False)
class ClientSession:
    socket: socket.socket
    address: Any
    authenticated: bool
    subscriptions: Set[str] = field(default_factory=set)
    send_lock: threading.Lock = field(default_factory=threading.Lock)


class AppServer(Node):
    def __init__(self) -> None:
        super().__init__('app_server')
        self._declare_parameters()

        self.linear_speed = float(self.get_parameter('linear_speed').value)
        self.angular_speed = float(self.get_parameter('angular_speed').value)
        self.max_linear_speed = float(self.get_parameter('max_linear_speed').value)
        self.max_angular_speed = float(self.get_parameter('max_angular_speed').value)
        self.client_timeout_sec = float(self.get_parameter('client_timeout_sec').value)
        self.max_line_bytes = int(self.get_parameter('max_line_bytes').value)
        self.auth_token = str(self.get_parameter('auth_token').value)
        self.frame_id = str(self.get_parameter('navigation_frame_id').value)

        self._stop_event = threading.Event()
        self._server: Optional[socket.socket] = None
        self._sessions: Set[ClientSession] = set()
        self._sessions_lock = threading.Lock()
        self._app_goal_handle = None
        self._state: Dict[str, Any] = {
            'mode': str(self.get_parameter('default_mode').value),
            'estop_active': False,
            'lidar_override_active': False,
            'lidar_warning_active': False,
            'lidar_warning_state': 'unknown',
            'vision_detection': None,
            'follow_target_id': None,
            'person_safety': {'slow_active': False, 'estop_active': False},
            'command': {'linear': 0.0, 'angular': 0.0},
            'navigation': {'state': 'idle'},
        }

        self.cmd_pub = self.create_publisher(Twist, self._parameter_topic('manual_topic'), 10)
        self.mode_pub = self.create_publisher(String, self._parameter_topic('mode_topic'), 10)
        self.estop_pub = self.create_publisher(Bool, self._parameter_topic('estop_topic'), 10)
        self.goal_pub = self.create_publisher(PoseStamped, self._parameter_topic('goal_topic'), 10)
        self.follow_target_pub = self.create_publisher(
            String, self._parameter_topic('follow_target_topic'), 10
        )
        self.status_pub = self.create_publisher(String, self._parameter_topic('status_topic'), 10)
        self.nav_client = ActionClient(
            self, NavigateToPose, str(self.get_parameter('navigation_action').value)
        )

        self.create_subscription(String, self._parameter_topic('mode_topic'), self._on_mode, 10)
        self.create_subscription(Bool, self._parameter_topic('estop_topic'), self._on_estop, 10)
        self.create_subscription(
            Bool, self._parameter_topic('lidar_override_topic'), self._on_lidar_override, 10
        )
        self.create_subscription(
            Bool, self._parameter_topic('lidar_warning_topic'), self._on_lidar_warning, 10
        )
        self.create_subscription(
            String, self._parameter_topic('lidar_warning_state_topic'), self._on_lidar_warning_state, 10
        )
        self.create_subscription(
            String, self._parameter_topic('vision_detection_topic'), self._on_vision_detection, 10
        )
        self.create_subscription(
            Bool, self._parameter_topic('person_slow_topic'), self._on_person_slow, 10
        )
        self.create_subscription(
            Bool, self._parameter_topic('person_estop_topic'), self._on_person_estop, 10
        )
        self.create_subscription(
            Twist, self._parameter_topic('control_output_topic'), self._on_control_output, 10
        )

        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        self.get_logger().info(
            f"APP bridge listening on {self.get_parameter('host').value}:"
            f"{self.get_parameter('port').value} (protocol v{PROTOCOL_VERSION})"
        )

    def _declare_parameters(self) -> None:
        self.declare_parameter('host', '0.0.0.0')
        self.declare_parameter('port', 8765)
        self.declare_parameter('auth_token', '')
        self.declare_parameter('manual_topic', '/cmd_vel_manual')
        self.declare_parameter('mode_topic', '/mode_select')
        self.declare_parameter('estop_topic', '/emergency_stop')
        self.declare_parameter('goal_topic', '/goal_pose')
        self.declare_parameter('navigation_action', 'navigate_to_pose')
        self.declare_parameter('navigation_frame_id', 'map')
        self.declare_parameter('control_output_topic', '/control/cmd_vel')
        self.declare_parameter('lidar_override_topic', '/lidar/override_active')
        self.declare_parameter('lidar_warning_topic', '/lidar/warning')
        self.declare_parameter('lidar_warning_state_topic', '/lidar/warning_state')
        self.declare_parameter('vision_detection_topic', '/vision/detections')
        self.declare_parameter('follow_target_topic', '/vision/follow_target')
        self.declare_parameter('person_slow_topic', '/vision/person_slow')
        self.declare_parameter('person_estop_topic', '/vision/person_estop')
        self.declare_parameter('status_topic', '/app_bridge/status')
        self.declare_parameter('default_mode', 'manual')
        self.declare_parameter('linear_speed', 0.2)
        self.declare_parameter('angular_speed', 0.7)
        self.declare_parameter('max_linear_speed', 0.4)
        self.declare_parameter('max_angular_speed', 1.2)
        self.declare_parameter('client_timeout_sec', 0.2)
        self.declare_parameter('max_line_bytes', 8192)

    def _parameter_topic(self, name: str) -> str:
        return str(self.get_parameter(name).value)

    def destroy_node(self) -> bool:
        self._stop_event.set()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
        with self._sessions_lock:
            sessions = tuple(self._sessions)
        for session in sessions:
            try:
                session.socket.close()
            except OSError:
                pass
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        return super().destroy_node()

    # TCP handling ---------------------------------------------------------
    def _serve(self) -> None:
        host = str(self.get_parameter('host').value)
        port = int(self.get_parameter('port').value)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                self._server = server
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind((host, port))
                server.listen(8)
                server.settimeout(self.client_timeout_sec)
                while not self._stop_event.is_set():
                    try:
                        client, address = server.accept()
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                    threading.Thread(
                        target=self._handle_client, args=(client, address), daemon=True
                    ).start()
        except OSError as exc:
            if not self._stop_event.is_set():
                self.get_logger().error(f'APP bridge could not listen on {host}:{port}: {exc}')

    def _handle_client(self, client: socket.socket, address: Any) -> None:
        session = ClientSession(client, address, authenticated=not bool(self.auth_token))
        with self._sessions_lock:
            self._sessions.add(session)
        self._publish_status(f'client connected {address[0]}:{address[1]}')
        try:
            with client:
                client.settimeout(self.client_timeout_sec)
                self._send(
                    session,
                    {
                        'type': 'hello',
                        'protocol_version': PROTOCOL_VERSION,
                        'authentication_required': bool(self.auth_token),
                    },
                )
                buffer = b''
                while not self._stop_event.is_set():
                    try:
                        chunk = client.recv(4096)
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                    if not chunk:
                        break
                    buffer += chunk
                    if len(buffer) > self.max_line_bytes and b'\n' not in buffer:
                        self._send_error(session, 'request', 'request line is too large')
                        break
                    while b'\n' in buffer:
                        raw_line, buffer = buffer.split(b'\n', 1)
                        if len(raw_line) > self.max_line_bytes:
                            self._send_error(session, 'request', 'request line is too large')
                            continue
                        self._handle_line(session, raw_line)
        finally:
            with self._sessions_lock:
                self._sessions.discard(session)
            self._publish_status(f'client disconnected {address[0]}:{address[1]}')

    def _handle_line(self, session: ClientSession, raw_line: bytes) -> None:
        line = raw_line.decode('utf-8', errors='replace').strip()
        if not line:
            self._send_error(session, 'request', 'empty command')
            return
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            if self.auth_token and not session.authenticated:
                self._send_error(session, 'request', 'authentication required')
                return
            self._handle_legacy_text(session, line)
            return
        if not isinstance(payload, dict):
            self._send_error(session, 'request', 'JSON request must be an object')
            return
        self._handle_json(session, payload)

    def _handle_json(self, session: ClientSession, payload: Dict[str, Any]) -> None:
        command = str(payload.get('cmd', '')).strip().lower()
        request_id = payload.get('id')
        if not command:
            self._send_error(session, 'request', 'cmd is required', request_id)
            return
        if command == 'auth':
            token = payload.get('token', '')
            session.authenticated = bool(self.auth_token) and isinstance(token, str) and token == self.auth_token
            if not self.auth_token:
                session.authenticated = True
            if session.authenticated:
                self._send(session, response(True, command, request_id=request_id, data={'authenticated': True}))
            else:
                self._send_error(session, command, 'invalid authentication token', request_id)
            return
        if self.auth_token and not session.authenticated:
            self._send_error(session, command, 'authentication required', request_id)
            return
        try:
            result = self._dispatch(command, payload, session)
            self._send(session, response(True, command, request_id=request_id, data=result))
        except ProtocolError as exc:
            self._send_error(session, command, str(exc), request_id)
        except Exception as exc:  # Keep malformed APP requests from crashing the ROS node.
            self.get_logger().error(f'APP command {command} failed: {exc}')
            self._send_error(session, command, 'command could not be completed', request_id)

    def _dispatch(self, command: str, payload: Dict[str, Any], session: ClientSession) -> Dict[str, Any]:
        if command in {'ping', 'capabilities'}:
            return self._capabilities() if command == 'capabilities' else {'protocol_version': PROTOCOL_VERSION}
        if command == 'status':
            return self._snapshot()
        if command == 'subscribe':
            channels = string_list(payload.get('channels', []), 'channels')
            invalid = set(channels) - TELEMETRY_CHANNELS
            if invalid:
                raise ProtocolError(f'unsupported telemetry channels: {", ".join(sorted(invalid))}')
            session.subscriptions.update(channels)
            return {'channels': sorted(session.subscriptions), 'state': self._snapshot()}
        if command == 'unsubscribe':
            channels = string_list(payload.get('channels', []), 'channels')
            session.subscriptions.difference_update(channels)
            return {'channels': sorted(session.subscriptions)}
        if command in {'move', 'twist'}:
            linear = finite_number(payload.get('linear', 0.0), 'linear', limit=self.max_linear_speed)
            angular = finite_number(payload.get('angular', 0.0), 'angular', limit=self.max_angular_speed)
            self._publish_twist(linear, angular)
            return {'linear': linear, 'angular': angular}
        if command == 'mode':
            mode = str(payload.get('value', '')).strip().lower()
            if mode not in VALID_MODES:
                raise ProtocolError(f'mode must be one of: {", ".join(sorted(VALID_MODES))}')
            self._set_mode(mode)
            return {'mode': mode}
        if command == 'estop':
            active = boolean(payload.get('active', True), 'active')
            self._set_estop(active)
            return {'active': active}
        if command == 'nav_goal':
            return self._set_navigation_goal(payload)
        if command == 'nav_cancel':
            return self._cancel_navigation_goal()
        if command == 'follow_person':
            return self._follow_person(payload)
        if command == 'stop_follow':
            return self._stop_follow()
        raise ProtocolError(f'unknown command: {command}')

    def _handle_legacy_text(self, session: ClientSession, line: str) -> None:
        """Keep existing keyboard-style clients working while new APPs use JSON."""
        parts = line.lower().split()
        command = parts[0] if parts else ''
        try:
            if command in {'w', 'forward'}:
                self._publish_twist(self.linear_speed, 0.0)
            elif command in {'s', 'back', 'backward'}:
                self._publish_twist(-self.linear_speed, 0.0)
            elif command in {'a', 'left'}:
                self._publish_twist(0.0, self.angular_speed)
            elif command in {'d', 'right'}:
                self._publish_twist(0.0, -self.angular_speed)
            elif command in {'x', 'stop'}:
                self._publish_twist(0.0, 0.0)
            elif command == 'mode' and len(parts) == 2 and parts[1] in VALID_MODES:
                self._set_mode(parts[1])
            elif command == 'estop':
                active = len(parts) == 1 or boolean(parts[1], 'active')
                self._set_estop(active)
            else:
                raise ProtocolError(f'unknown command: {line}')
            self._send(session, response(True, command, data={'legacy': True}))
        except ProtocolError as exc:
            self._send_error(session, command or 'request', str(exc))

    # Car capabilities -----------------------------------------------------
    def _publish_twist(self, linear: float, angular: float) -> None:
        msg = Twist()
        msg.linear.x = linear
        msg.angular.z = angular
        self.cmd_pub.publish(msg)
        self._state['command'] = {'linear': linear, 'angular': angular}
        self._broadcast('status', self._snapshot())

    def _set_mode(self, mode: str) -> None:
        self.mode_pub.publish(String(data=mode))
        self._state['mode'] = mode
        self._broadcast('status', self._snapshot())

    def _set_estop(self, active: bool) -> None:
        self.estop_pub.publish(Bool(data=active))
        self._state['estop_active'] = active
        self._broadcast('status', self._snapshot())

    def _set_navigation_goal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        x = finite_number(payload.get('x'), 'x')
        y = finite_number(payload.get('y'), 'y')
        yaw = finite_number(payload.get('yaw', 0.0), 'yaw')
        frame_id = str(payload.get('frame_id', self.frame_id)).strip()
        if not frame_id:
            raise ProtocolError('frame_id must not be empty')
        pose = PoseStamped()
        pose.header.frame_id = frame_id
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        self.goal_pub.publish(pose)
        self._state['navigation'] = {'state': 'goal_published', 'x': x, 'y': y, 'yaw': yaw, 'frame_id': frame_id}
        action_sent = False
        if self.nav_client.server_is_ready():
            goal = NavigateToPose.Goal()
            goal.pose = pose
            self.nav_client.send_goal_async(goal).add_done_callback(self._on_nav_goal_response)
            self._state['navigation']['state'] = 'goal_sent'
            action_sent = True
        self._broadcast('navigation', dict(self._state['navigation']))
        return {**self._state['navigation'], 'action_sent': action_sent}

    def _cancel_navigation_goal(self) -> Dict[str, Any]:
        if self._app_goal_handle is None:
            raise ProtocolError('no APP navigation goal is active')
        self._app_goal_handle.cancel_goal_async()
        self._state['navigation'] = {'state': 'cancel_requested'}
        self._broadcast('navigation', dict(self._state['navigation']))
        return dict(self._state['navigation'])

    def _follow_person(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raw_track_id = payload.get('track_id')
        if isinstance(raw_track_id, bool):
            raise ProtocolError('track_id must be a non-negative integer')
        try:
            track_id = int(raw_track_id)
        except (TypeError, ValueError) as exc:
            raise ProtocolError('track_id must be a non-negative integer') from exc
        if track_id < 0 or str(track_id) != str(raw_track_id).strip():
            raise ProtocolError('track_id must be a non-negative integer')
        activate = boolean(payload.get('activate', True), 'activate')
        self.follow_target_pub.publish(String(data=str(track_id)))
        self._state['follow_target_id'] = track_id
        if activate:
            self._set_mode('follow')
        self._broadcast('status', self._snapshot())
        return {'track_id': track_id, 'mode': self._state['mode']}

    def _stop_follow(self) -> Dict[str, Any]:
        self.follow_target_pub.publish(String(data=''))
        self._state['follow_target_id'] = None
        if self._state['mode'] == 'follow':
            self._set_mode('manual')
        self._broadcast('status', self._snapshot())
        return {'mode': self._state['mode']}

    def _on_nav_goal_response(self, future: Any) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:
            self._state['navigation'] = {'state': 'failed', 'error': str(exc)}
        else:
            if not goal_handle.accepted:
                self._state['navigation'] = {'state': 'rejected'}
            else:
                self._app_goal_handle = goal_handle
                self._state['navigation']['state'] = 'accepted'
                goal_handle.get_result_async().add_done_callback(self._on_nav_result)
        self._broadcast('navigation', dict(self._state['navigation']))

    def _on_nav_result(self, future: Any) -> None:
        try:
            result = future.result()
            self._state['navigation'] = {'state': 'finished', 'result_status': int(result.status)}
        except Exception as exc:
            self._state['navigation'] = {'state': 'failed', 'error': str(exc)}
        self._app_goal_handle = None
        self._broadcast('navigation', dict(self._state['navigation']))

    # ROS telemetry --------------------------------------------------------
    def _on_mode(self, msg: String) -> None:
        self._state['mode'] = msg.data.strip() or self._state['mode']
        self._broadcast('status', self._snapshot())

    def _on_estop(self, msg: Bool) -> None:
        self._state['estop_active'] = bool(msg.data)
        self._broadcast('status', self._snapshot())

    def _on_lidar_override(self, msg: Bool) -> None:
        self._state['lidar_override_active'] = bool(msg.data)
        self._broadcast('lidar', self._lidar_snapshot())
        self._broadcast('status', self._snapshot())

    def _on_lidar_warning(self, msg: Bool) -> None:
        self._state['lidar_warning_active'] = bool(msg.data)
        self._broadcast('lidar', self._lidar_snapshot())

    def _on_lidar_warning_state(self, msg: String) -> None:
        self._state['lidar_warning_state'] = msg.data
        self._broadcast('lidar', self._lidar_snapshot())

    def _on_vision_detection(self, msg: String) -> None:
        try:
            detection: Any = json.loads(msg.data)
        except json.JSONDecodeError:
            detection = {'raw': msg.data}
        self._state['vision_detection'] = detection
        self._broadcast('vision', {'detection': detection})

    def _on_person_slow(self, msg: Bool) -> None:
        self._state['person_safety']['slow_active'] = bool(msg.data)
        self._broadcast('status', self._snapshot())

    def _on_person_estop(self, msg: Bool) -> None:
        self._state['person_safety']['estop_active'] = bool(msg.data)
        self._broadcast('status', self._snapshot())

    def _on_control_output(self, msg: Twist) -> None:
        self._state['command'] = {'linear': msg.linear.x, 'angular': msg.angular.z}
        self._broadcast('status', self._snapshot())

    # Responses and telemetry ---------------------------------------------
    def _capabilities(self) -> Dict[str, Any]:
        return {
            'protocol_version': PROTOCOL_VERSION,
            'commands': ['ping', 'capabilities', 'status', 'subscribe', 'unsubscribe', 'move', 'mode', 'estop', 'nav_goal', 'nav_cancel', 'follow_person', 'stop_follow'],
            'modes': sorted(VALID_MODES),
            'telemetry_channels': sorted(TELEMETRY_CHANNELS),
            'limits': {'max_linear_speed': self.max_linear_speed, 'max_angular_speed': self.max_angular_speed},
        }

    def _snapshot(self) -> Dict[str, Any]:
        return {
            'mode': self._state['mode'],
            'estop_active': self._state['estop_active'],
            'lidar': self._lidar_snapshot(),
            'vision_detection': self._state['vision_detection'],
            'follow_target_id': self._state['follow_target_id'],
            'person_safety': dict(self._state['person_safety']),
            'command': dict(self._state['command']),
            'navigation': dict(self._state['navigation']),
        }

    def _lidar_snapshot(self) -> Dict[str, Any]:
        return {
            'override_active': self._state['lidar_override_active'],
            'warning_active': self._state['lidar_warning_active'],
            'warning_state': self._state['lidar_warning_state'],
        }

    def _broadcast(self, channel: str, data: Dict[str, Any]) -> None:
        with self._sessions_lock:
            recipients = tuple(session for session in self._sessions if channel in session.subscriptions)
        for session in recipients:
            self._send(session, event(channel, data))

    def _publish_status(self, text: str) -> None:
        self.status_pub.publish(String(data=text))

    def _send_error(self, session: ClientSession, command: str, error_text: str, request_id: Any = None) -> None:
        self._send(session, response(False, command, request_id=request_id, error=error_text))

    @staticmethod
    def _send(session: ClientSession, payload: Dict[str, Any]) -> bool:
        try:
            encoded = (json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
            with session.send_lock:
                session.socket.sendall(encoded)
            return True
        except OSError:
            return False


def main(args: Optional[Sequence[str]] = None) -> None:
    rclpy.init(args=args)
    node = AppServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.cmd_pub.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()
