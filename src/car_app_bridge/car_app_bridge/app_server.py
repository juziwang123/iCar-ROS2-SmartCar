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
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Set

import rclpy
from car_interfaces.action import ExecutePatrol
from car_interfaces.msg import InspectionResult, MissionStatus, PatrolEvent
from car_interfaces.srv import MissionControl
from car_map_manager.map_repository import MapNotFoundError, MapRepository, MapRepositoryError
from car_mission.mission_repository import MissionRepository
from car_mission.route_repository import RouteNotFoundError, RouteRepository
from car_mission.route_schema import RouteValidationError, parse_route, route_to_mapping
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped, Twist
from nav2_msgs.action import NavigateToPose
from nav2_msgs.srv import SaveMap
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import Bool, String

from .control_lease import ControlLeaseManager, LeaseError
from .protocol import (
    PROTOCOL_VERSION,
    TELEMETRY_CHANNELS,
    VALID_MODES,
    ProtocolError,
    boolean,
    event,
    finite_number,
    nonempty_string,
    nonnegative_integer,
    object_value,
    response,
    string_list,
)


@dataclass(eq=False)
class ClientSession:
    socket: socket.socket
    address: Any
    authenticated: bool
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
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
        self.service_call_timeout_sec = float(self.get_parameter('service_call_timeout_sec').value)
        self.map_repository = MapRepository(str(self.get_parameter('maps_root').value))
        self.route_repository = RouteRepository(str(self.get_parameter('route_database_path').value))
        self.mission_repository = MissionRepository(
            str(self.get_parameter('route_database_path').value)
        )
        self._control_lease = ControlLeaseManager(
            float(self.get_parameter('control_lease_timeout_sec').value)
        )
        self._lease_lock = threading.Lock()

        self._stop_event = threading.Event()
        self._server: Optional[socket.socket] = None
        self._sessions: Set[ClientSession] = set()
        self._sessions_lock = threading.Lock()
        self._app_goal_handle = None
        self._mission_goal_handle = None
        self._state: Dict[str, Any] = {
            'mode': str(self.get_parameter('default_mode').value),
            'estop_active': False,
            'effective_estop_active': False,
            'lidar_override_active': False,
            'lidar_warning_active': False,
            'lidar_warning_state': 'unknown',
            'vision_detection': None,
            'follow_target_id': None,
            'person_safety': {'slow_active': False, 'estop_active': False},
            'command': {'linear': 0.0, 'angular': 0.0},
            'navigation': {'state': 'idle'},
            'pose': None,
            'mission': {'state': 'idle'},
            'inspection': None,
        }

        self.cmd_pub = self.create_publisher(Twist, self._parameter_topic('manual_topic'), 10)
        self.mode_pub = self.create_publisher(String, self._parameter_topic('mode_topic'), 10)
        self.estop_pub = self.create_publisher(Bool, self._parameter_topic('estop_topic'), 10)
        self.goal_pub = self.create_publisher(PoseStamped, self._parameter_topic('goal_topic'), 10)
        self.initial_pose_pub = self.create_publisher(
            PoseWithCovarianceStamped, self._parameter_topic('initial_pose_topic'), 10
        )
        self.follow_target_pub = self.create_publisher(
            String, self._parameter_topic('follow_target_topic'), 10
        )
        self.status_pub = self.create_publisher(String, self._parameter_topic('status_topic'), 10)
        self.nav_client = ActionClient(
            self, NavigateToPose, str(self.get_parameter('navigation_action').value)
        )
        self.map_saver_client = self.create_client(
            SaveMap, self._parameter_topic('map_saver_service')
        )
        self.mission_client = ActionClient(
            self, ExecutePatrol, self._parameter_topic('mission_action')
        )
        self.mission_control_client = self.create_client(
            MissionControl, self._parameter_topic('mission_control_service')
        )

        self.create_subscription(String, self._parameter_topic('mode_topic'), self._on_mode, 10)
        self.create_subscription(Bool, self._parameter_topic('estop_topic'), self._on_estop, 10)
        self.create_subscription(
            Bool, self._parameter_topic('effective_estop_topic'), self._on_effective_estop, 10
        )
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
        self.create_subscription(
            PoseWithCovarianceStamped, self._parameter_topic('robot_pose_topic'), self._on_robot_pose, 10
        )
        self.create_subscription(
            MissionStatus, self._parameter_topic('mission_status_topic'), self._on_mission_status, 10
        )
        self.create_subscription(
            PatrolEvent, self._parameter_topic('mission_event_topic'), self._on_mission_event, 10
        )
        self.create_subscription(
            InspectionResult,
            self._parameter_topic('inspection_result_topic'),
            self._on_inspection_result,
            10,
        )
        self.create_timer(0.1, self._expire_control_lease)

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
        self.declare_parameter('effective_estop_topic', '/control/effective_estop')
        self.declare_parameter('goal_topic', '/goal_pose')
        self.declare_parameter('navigation_action', 'navigate_to_pose')
        self.declare_parameter('navigation_frame_id', 'map')
        self.declare_parameter('initial_pose_topic', '/initialpose')
        self.declare_parameter('control_output_topic', '/control/cmd_vel')
        self.declare_parameter('lidar_override_topic', '/lidar/override_active')
        self.declare_parameter('lidar_warning_topic', '/lidar/warning')
        self.declare_parameter('lidar_warning_state_topic', '/lidar/warning_state')
        self.declare_parameter('vision_detection_topic', '/vision/detections')
        self.declare_parameter('follow_target_topic', '/vision/follow_target')
        self.declare_parameter('person_slow_topic', '/vision/person_slow')
        self.declare_parameter('person_estop_topic', '/vision/person_estop')
        self.declare_parameter('status_topic', '/app_bridge/status')
        self.declare_parameter('robot_pose_topic', '/amcl_pose')
        self.declare_parameter('mission_status_topic', '/mission/status')
        self.declare_parameter('mission_event_topic', '/mission/event')
        self.declare_parameter('inspection_result_topic', '/inspection/result')
        self.declare_parameter('mission_action', 'execute_patrol')
        self.declare_parameter('mission_control_service', '/mission/control')
        self.declare_parameter('maps_root', '~/.icar/maps')
        self.declare_parameter('route_database_path', '~/.icar/icar.db')
        self.declare_parameter('map_saver_service', '/map_saver/save_map')
        self.declare_parameter('map_topic', '/map')
        self.declare_parameter('map_image_format', 'pgm')
        self.declare_parameter('map_mode', 'trinary')
        self.declare_parameter('map_free_thresh', 0.25)
        self.declare_parameter('map_occupied_thresh', 0.65)
        self.declare_parameter('service_call_timeout_sec', 10.0)
        self.declare_parameter('control_lease_timeout_sec', 1.0)
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
            self._release_control_lease(session, lease_id=None, reason='client disconnected')
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
        if command == 'teleop_acquire':
            return self._acquire_control_lease(session)
        if command == 'teleop_heartbeat':
            return self._heartbeat_control_lease(session, payload)
        if command == 'teleop_release':
            return self._release_control_lease(
                session,
                lease_id=nonempty_string(payload.get('lease_id'), 'lease_id'),
                reason='released by client',
            )
        if command in {'move', 'twist'}:
            self._validate_control_lease(session, payload)
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
        if command == 'map_list':
            return {'maps': self.map_repository.list_maps()}
        if command == 'map_get':
            map_id = nonempty_string(payload.get('map_id'), 'map_id')
            try:
                return {'map': self.map_repository.get_map(map_id)}
            except (MapNotFoundError, MapRepositoryError) as exc:
                raise ProtocolError(str(exc)) from exc
        if command == 'map_save':
            return self._save_map(payload)
        if command == 'initial_pose':
            return self._set_initial_pose(payload)
        if command == 'route_list':
            map_id = payload.get('map_id')
            if map_id is not None:
                map_id = nonempty_string(map_id, 'map_id')
            return {'routes': self.route_repository.list_routes(map_id)}
        if command == 'route_get':
            route_id = nonempty_string(payload.get('route_id'), 'route_id')
            version = payload.get('version')
            if version is not None:
                version = nonnegative_integer(version, 'version')
                if version == 0:
                    version = None
            try:
                route = self.route_repository.load(route_id, version)
            except RouteNotFoundError as exc:
                raise ProtocolError(str(exc)) from exc
            return {'route': route_to_mapping(route)}
        if command == 'route_validate':
            return self._validate_route(object_value(payload.get('route'), 'route'))
        if command == 'route_save':
            return self._save_route(payload)
        if command == 'route_delete':
            return self._delete_route(payload)
        if command == 'mission_start':
            return self._start_mission(payload)
        if command == 'mission_pause':
            return self._mission_control(payload, 'pause')
        if command == 'mission_resume':
            return self._mission_control(payload, 'resume')
        if command == 'mission_cancel':
            return self._mission_control(payload, 'cancel')
        if command == 'mission_checkins':
            mission_id = nonempty_string(payload.get('mission_id'), 'mission_id')
            return {'checkins': self.mission_repository.list_checkins(mission_id)}
        if command == 'mission_inspections':
            mission_id = nonempty_string(payload.get('mission_id'), 'mission_id')
            return {'inspections': self.mission_repository.list_inspections(mission_id)}
        if command == 'mission_report':
            mission_id = nonempty_string(payload.get('mission_id'), 'mission_id')
            return {'report': self.mission_repository.get_report(mission_id)}
        raise ProtocolError(f'unknown command: {command}')

    def _handle_legacy_text(self, session: ClientSession, line: str) -> None:
        """Keep existing keyboard-style clients working while new APPs use JSON."""
        parts = line.lower().split()
        command = parts[0] if parts else ''
        try:
            if command in {'w', 'forward', 's', 'back', 'backward', 'a', 'left', 'd', 'right'}:
                raise ProtocolError('legacy movement is disabled; use teleop_acquire and move with lease_id')
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

    # P2 control lease ----------------------------------------------------
    def _acquire_control_lease(self, session: ClientSession) -> Dict[str, Any]:
        if self._navigation_is_active():
            raise ProtocolError('cancel the active direct navigation goal before manual takeover')
        mission_state = str(self._state['mission'].get('state', '')).lower()
        if self._mission_is_active() and mission_state != 'paused':
            raise ProtocolError('pause the mission and wait for PAUSED before manual takeover')
        with self._lease_lock:
            try:
                lease = self._control_lease.acquire(session.session_id, time.monotonic())
            except LeaseError as exc:
                raise ProtocolError(str(exc)) from exc
            snapshot = self._control_lease.snapshot(time.monotonic())
        # Manual is selected only after a lease has been created.  Releasing
        # the lease deliberately leaves the car stopped in manual mode; an
        # explicit mission resume is required before autonomous movement.
        self._set_mode('manual')
        self._broadcast('control_lease', snapshot)
        return {'lease_id': lease.lease_id, 'expires_in_sec': self._control_lease.timeout_sec}

    def _heartbeat_control_lease(self, session: ClientSession, payload: Dict[str, Any]) -> Dict[str, Any]:
        lease_id = nonempty_string(payload.get('lease_id'), 'lease_id')
        with self._lease_lock:
            try:
                lease = self._control_lease.heartbeat(session.session_id, lease_id, time.monotonic())
            except LeaseError as exc:
                raise ProtocolError(str(exc)) from exc
            snapshot = self._control_lease.snapshot(time.monotonic())
        self._broadcast('control_lease', snapshot)
        return {'lease_id': lease.lease_id, 'expires_in_sec': self._control_lease.timeout_sec}

    def _validate_control_lease(self, session: ClientSession, payload: Dict[str, Any]) -> None:
        lease_id = nonempty_string(payload.get('lease_id'), 'lease_id')
        with self._lease_lock:
            try:
                self._control_lease.heartbeat(session.session_id, lease_id, time.monotonic())
            except LeaseError as exc:
                raise ProtocolError(str(exc)) from exc

    def _release_control_lease(
        self,
        session: ClientSession,
        *,
        lease_id: Optional[str],
        reason: str,
    ) -> Dict[str, Any]:
        with self._lease_lock:
            try:
                released = self._control_lease.release(session.session_id, lease_id, time.monotonic())
            except LeaseError as exc:
                if reason == 'client disconnected':
                    return {'released': False, 'reason': reason}
                raise ProtocolError(str(exc)) from exc
            snapshot = self._control_lease.snapshot(time.monotonic())
        if released:
            self._publish_twist(0.0, 0.0)
            self._broadcast('control_lease', snapshot)
        return {'released': released, 'reason': reason}

    def _expire_control_lease(self) -> None:
        with self._lease_lock:
            expired = self._control_lease.expire(time.monotonic())
            snapshot = self._control_lease.snapshot(time.monotonic())
        if expired:
            self._publish_twist(0.0, 0.0)
            self._broadcast('control_lease', snapshot)

    # P2 map and route interfaces ---------------------------------------
    def _save_map(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = nonempty_string(payload.get('name'), 'name')
        if len(name) > 80:
            raise ProtocolError('name must be at most 80 characters')
        if not self.map_saver_client.service_is_ready():
            raise ProtocolError('map saver service is unavailable; start mapping mode with map_saver enabled')
        map_id = self.map_repository.create_map_id(name)
        try:
            map_base = self.map_repository.prepare_save_location(map_id)
            request = SaveMap.Request()
            request.map_topic = self._parameter_topic('map_topic')
            request.map_url = str(map_base)
            request.image_format = str(self.get_parameter('map_image_format').value)
            request.map_mode = str(self.get_parameter('map_mode').value)
            request.free_thresh = float(self.get_parameter('map_free_thresh').value)
            request.occupied_thresh = float(self.get_parameter('map_occupied_thresh').value)
            result = self._wait_for_future(self.map_saver_client.call_async(request), 'map save')
            if not bool(result.result):
                raise ProtocolError('map saver reported failure')
            manifest = self.map_repository.register_saved_map(map_id, name, str(map_base))
        except MapRepositoryError as exc:
            raise ProtocolError(str(exc)) from exc
        return {'saved': True, 'map': manifest}

    def _set_initial_pose(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        map_id = nonempty_string(payload.get('map_id'), 'map_id')
        try:
            self.map_repository.get_map(map_id)
        except (MapNotFoundError, MapRepositoryError) as exc:
            raise ProtocolError(str(exc)) from exc
        x = finite_number(payload.get('x'), 'x')
        y = finite_number(payload.get('y'), 'y')
        yaw = finite_number(payload.get('yaw', 0.0), 'yaw')
        pose = PoseWithCovarianceStamped()
        pose.header.frame_id = self.frame_id
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.pose.position.x = x
        pose.pose.pose.position.y = y
        pose.pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.pose.orientation.w = math.cos(yaw / 2.0)
        pose.pose.covariance[0] = 0.25
        pose.pose.covariance[7] = 0.25
        pose.pose.covariance[35] = 0.0685
        self.initial_pose_pub.publish(pose)
        return {'map_id': map_id, 'x': x, 'y': y, 'yaw': yaw, 'frame_id': self.frame_id}

    def _validate_route(self, definition: Dict[str, Any]) -> Dict[str, Any]:
        try:
            route = parse_route(definition)
            validation = self.map_repository.validate_route(route)
        except (RouteValidationError, MapNotFoundError, MapRepositoryError) as exc:
            return {'valid': False, 'errors': [{'code': 'INVALID_ROUTE', 'message': str(exc)}]}
        return {**validation, 'route': route_to_mapping(route)}

    def _save_route(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        definition = object_value(payload.get('route'), 'route')
        validation = self._validate_route(definition)
        if not validation['valid']:
            return {'saved': False, 'validation': validation}
        route = parse_route(definition)
        replace = boolean(payload.get('replace', False), 'replace')
        try:
            self.route_repository.save(route, replace=replace)
        except Exception as exc:
            raise ProtocolError(
                'route version already exists; increment version or set replace=true'
            ) from exc
        return {'saved': True, 'route_id': route.route_id, 'version': route.version, 'validation': validation}

    def _delete_route(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        route_id = nonempty_string(payload.get('route_id'), 'route_id')
        version = payload.get('version')
        if version is not None:
            version = nonnegative_integer(version, 'version')
            if version == 0:
                version = None
        deleted = self.route_repository.delete(route_id, version)
        return {'deleted': deleted, 'route_id': route_id, 'version': version}

    # P2 mission interfaces ----------------------------------------------
    def _start_mission(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        route_id = nonempty_string(payload.get('route_id'), 'route_id')
        route_version = nonnegative_integer(payload.get('route_version', 0), 'route_version')
        start_index = nonnegative_integer(payload.get('start_checkpoint_index', 0), 'start_checkpoint_index')
        loop = boolean(payload.get('loop', False), 'loop')
        try:
            self.route_repository.load(route_id, route_version or None)
        except RouteNotFoundError as exc:
            raise ProtocolError(str(exc)) from exc
        if self._mission_is_active():
            raise ProtocolError('a mission is already active or awaiting acceptance')
        if self._navigation_is_active():
            raise ProtocolError('cancel the active direct navigation goal before starting a mission')
        if not self.mission_client.server_is_ready():
            raise ProtocolError('mission action server is unavailable')
        goal = ExecutePatrol.Goal()
        goal.route_id = route_id
        goal.route_version = route_version
        goal.start_checkpoint_index = start_index
        goal.loop = loop
        self._state['mission'] = {
            'state': 'goal_requested',
            'route_id': route_id,
            'route_version': route_version,
        }
        self.mission_client.send_goal_async(goal, feedback_callback=self._on_mission_feedback).add_done_callback(
            self._on_mission_goal_response
        )
        self._broadcast('mission', dict(self._state['mission']))
        return dict(self._state['mission'])

    def _mission_control(self, payload: Dict[str, Any], command: str) -> Dict[str, Any]:
        mission_id = nonempty_string(payload.get('mission_id'), 'mission_id')
        if not self.mission_control_client.service_is_ready():
            raise ProtocolError('mission control service is unavailable')
        request = MissionControl.Request()
        request.mission_id = mission_id
        request.command = command
        result = self._wait_for_future(
            self.mission_control_client.call_async(request), f'mission {command}'
        )
        return {'accepted': bool(result.accepted), 'state': result.state, 'message': result.message}

    def _wait_for_future(self, future: Any, operation: str) -> Any:
        completed = threading.Event()
        future.add_done_callback(lambda _: completed.set())
        if not completed.wait(self.service_call_timeout_sec):
            raise ProtocolError(f'{operation} timed out')
        try:
            return future.result()
        except Exception as exc:
            raise ProtocolError(f'{operation} failed: {exc}') from exc

    def _set_navigation_goal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._mission_is_active():
            raise ProtocolError('mission is active; use mission control instead of direct navigation')
        x = finite_number(payload.get('x'), 'x')
        y = finite_number(payload.get('y'), 'y')
        yaw = finite_number(payload.get('yaw', 0.0), 'yaw')
        frame_id = str(payload.get('frame_id', self.frame_id)).strip()
        if not frame_id:
            raise ProtocolError('frame_id must not be empty')
        # Once Nav2 is routed through safety_mux, it must be the selected
        # source or the safe default is a zero command. Switching here keeps
        # APP single-goal navigation functional without bypassing the mux.
        self._set_mode('nav')
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

    def _navigation_is_active(self) -> bool:
        return self._app_goal_handle is not None or self._state['navigation'].get('state') in {
            'goal_sent', 'accepted', 'cancel_requested',
        }

    def _mission_is_active(self) -> bool:
        state = str(self._state['mission'].get('state', '')).lower()
        return self._mission_goal_handle is not None or state in {
            'goal_requested', 'accepted', 'preparing', 'localizing', 'navigating',
            'arrival_confirming', 'checking_in', 'recording', 'recovering',
            'capturing', 'inspecting', 'pausing', 'paused', 'resuming',
            'waiting_operator', 'estopped',
        }

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

    def _on_mission_goal_response(self, future: Any) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:
            self._state['mission'] = {'state': 'failed', 'error': str(exc)}
        else:
            if not goal_handle.accepted:
                self._state['mission'] = {'state': 'rejected'}
            else:
                self._mission_goal_handle = goal_handle
                self._state['mission']['state'] = 'accepted'
                goal_handle.get_result_async().add_done_callback(self._on_mission_result)
        self._broadcast('mission', dict(self._state['mission']))

    def _on_mission_feedback(self, feedback_message: Any) -> None:
        feedback = feedback_message.feedback
        self._state['mission'] = {
            'mission_id': feedback.mission_id,
            'state': feedback.state,
            'checkpoint_id': feedback.checkpoint_id,
            'checkpoint_index': int(feedback.checkpoint_index),
            'checkpoint_total': int(feedback.checkpoint_total),
            'progress': float(feedback.progress),
            'retry_count': int(feedback.retry_count),
            'detail': feedback.detail,
        }
        self._broadcast('mission', dict(self._state['mission']))

    def _on_mission_result(self, future: Any) -> None:
        try:
            result_wrapper = future.result()
            result = result_wrapper.result
            self._state['mission'] = {
                'mission_id': result.mission_id,
                'state': result.final_state,
                'success': bool(result.success),
                'completed_checkpoints': int(result.completed_checkpoints),
                'failed_checkpoints': int(result.failed_checkpoints),
                'skipped_checkpoints': int(result.skipped_checkpoints),
                'report_path': result.report_path,
                'message': result.message,
            }
        except Exception as exc:
            self._state['mission'] = {'state': 'failed', 'error': str(exc)}
        self._mission_goal_handle = None
        self._broadcast('mission', dict(self._state['mission']))

    # ROS telemetry --------------------------------------------------------
    def _on_mode(self, msg: String) -> None:
        self._state['mode'] = msg.data.strip() or self._state['mode']
        self._broadcast('status', self._snapshot())

    def _on_estop(self, msg: Bool) -> None:
        self._state['estop_active'] = bool(msg.data)
        self._broadcast('status', self._snapshot())

    def _on_effective_estop(self, msg: Bool) -> None:
        self._state['effective_estop_active'] = bool(msg.data)
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

    def _on_robot_pose(self, msg: PoseWithCovarianceStamped) -> None:
        orientation = msg.pose.pose.orientation
        yaw = math.atan2(
            2.0 * (orientation.w * orientation.z + orientation.x * orientation.y),
            1.0 - 2.0 * (orientation.y * orientation.y + orientation.z * orientation.z),
        )
        self._state['pose'] = {
            'frame_id': msg.header.frame_id or self.frame_id,
            'stamp': {'sec': int(msg.header.stamp.sec), 'nanosec': int(msg.header.stamp.nanosec)},
            'x': msg.pose.pose.position.x,
            'y': msg.pose.pose.position.y,
            'yaw': yaw,
            'covariance': {
                'x': msg.pose.covariance[0],
                'y': msg.pose.covariance[7],
                'yaw': msg.pose.covariance[35],
            },
        }
        self._broadcast('pose', dict(self._state['pose']))

    def _on_mission_status(self, msg: MissionStatus) -> None:
        self._state['mission'] = {
            'mission_id': msg.mission_id,
            'route_id': msg.route_id,
            'route_version': int(msg.route_version),
            'state': msg.state,
            'checkpoint_id': msg.checkpoint_id,
            'checkpoint_index': int(msg.checkpoint_index),
            'checkpoint_total': int(msg.checkpoint_total),
            'progress': float(msg.progress),
            'retry_count': int(msg.retry_count),
            'detail': msg.detail,
        }
        self._broadcast('mission', dict(self._state['mission']))

    def _on_mission_event(self, msg: PatrolEvent) -> None:
        self._broadcast('event', {
            'mission_id': msg.mission_id,
            'previous_state': msg.previous_state,
            'state': msg.state,
            'checkpoint_id': msg.checkpoint_id,
            'code': msg.code,
            'detail': msg.detail,
            'stamp': {'sec': int(msg.header.stamp.sec), 'nanosec': int(msg.header.stamp.nanosec)},
        })

    def _on_inspection_result(self, msg: InspectionResult) -> None:
        inspection = {
            'mission_id': msg.mission_id,
            'checkpoint_id': msg.checkpoint_id,
            'task_id': msg.task_id,
            'task_type': msg.task_type,
            'target': msg.target,
            'conclusion': msg.conclusion,
            'confidence': float(msg.confidence),
            'needs_human_review': bool(msg.needs_human_review),
            'evidence_paths': list(msg.evidence_paths),
            'detail_json': msg.detail_json,
            'stamp': {'sec': int(msg.header.stamp.sec), 'nanosec': int(msg.header.stamp.nanosec)},
        }
        self._state['inspection'] = inspection
        self._broadcast('inspection', dict(inspection))
        self._broadcast('status', self._snapshot())

    # Responses and telemetry ---------------------------------------------
    def _capabilities(self) -> Dict[str, Any]:
        return {
            'protocol_version': PROTOCOL_VERSION,
            'commands': [
                'ping', 'capabilities', 'status', 'subscribe', 'unsubscribe',
                'teleop_acquire', 'teleop_heartbeat', 'teleop_release', 'move',
                'mode', 'estop', 'nav_goal', 'nav_cancel', 'follow_person', 'stop_follow',
                'map_list', 'map_get', 'map_save', 'initial_pose',
                'route_list', 'route_get', 'route_validate', 'route_save', 'route_delete',
                'mission_start', 'mission_pause', 'mission_resume', 'mission_cancel',
                'mission_checkins', 'mission_inspections', 'mission_report',
            ],
            'modes': sorted(VALID_MODES),
            'telemetry_channels': sorted(TELEMETRY_CHANNELS),
            'limits': {'max_linear_speed': self.max_linear_speed, 'max_angular_speed': self.max_angular_speed},
        }

    def _snapshot(self) -> Dict[str, Any]:
        return {
            'mode': self._state['mode'],
            'estop_active': self._state['estop_active'],
            'effective_estop_active': self._state['effective_estop_active'],
            'lidar': self._lidar_snapshot(),
            'vision_detection': self._state['vision_detection'],
            'follow_target_id': self._state['follow_target_id'],
            'person_safety': dict(self._state['person_safety']),
            'command': dict(self._state['command']),
            'navigation': dict(self._state['navigation']),
            'pose': dict(self._state['pose']) if self._state['pose'] is not None else None,
            'mission': dict(self._state['mission']),
            'inspection': dict(self._state['inspection']) if self._state['inspection'] is not None else None,
            'control_lease': self._control_lease_snapshot(),
        }

    def _lidar_snapshot(self) -> Dict[str, Any]:
        return {
            'override_active': self._state['lidar_override_active'],
            'warning_active': self._state['lidar_warning_active'],
            'warning_state': self._state['lidar_warning_state'],
        }

    def _control_lease_snapshot(self) -> Dict[str, Any]:
        with self._lease_lock:
            return self._control_lease.snapshot(time.monotonic())

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
