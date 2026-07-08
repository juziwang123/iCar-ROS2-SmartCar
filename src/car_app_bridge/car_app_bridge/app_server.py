from __future__ import annotations

import json
import socket
import threading
from typing import Dict, Optional, Sequence

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Bool, String


class AppServer(Node):
    def __init__(self) -> None:
        super().__init__('app_server')
        self.declare_parameter('host', '0.0.0.0')
        self.declare_parameter('port', 8765)
        self.declare_parameter('manual_topic', '/cmd_vel_manual')
        self.declare_parameter('mode_topic', '/mode_select')
        self.declare_parameter('estop_topic', '/emergency_stop')
        self.declare_parameter('status_topic', '/app_bridge/status')
        self.declare_parameter('linear_speed', 0.2)
        self.declare_parameter('angular_speed', 0.7)
        self.declare_parameter('client_timeout_sec', 0.2)

        self.linear_speed = float(self.get_parameter('linear_speed').value)
        self.angular_speed = float(self.get_parameter('angular_speed').value)
        self.client_timeout_sec = float(self.get_parameter('client_timeout_sec').value)
        self._stop_event = threading.Event()
        self._server: Optional[socket.socket] = None

        self.cmd_pub = self.create_publisher(Twist, str(self.get_parameter('manual_topic').value), 10)
        self.mode_pub = self.create_publisher(String, str(self.get_parameter('mode_topic').value), 10)
        self.estop_pub = self.create_publisher(Bool, str(self.get_parameter('estop_topic').value), 10)
        self.status_pub = self.create_publisher(String, str(self.get_parameter('status_topic').value), 10)

        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        host = str(self.get_parameter('host').value)
        port = int(self.get_parameter('port').value)
        self.get_logger().info(f'App bridge listening on {host}:{port}')

    def destroy_node(self) -> bool:
        self._stop_event.set()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        return super().destroy_node()

    def _serve(self) -> None:
        host = str(self.get_parameter('host').value)
        port = int(self.get_parameter('port').value)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            self._server = server
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, port))
            server.listen(4)
            server.settimeout(self.client_timeout_sec)
            while not self._stop_event.is_set():
                try:
                    client, address = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                threading.Thread(target=self._handle_client, args=(client, address), daemon=True).start()

    def _handle_client(self, client: socket.socket, address) -> None:
        self.status_pub.publish(String(data=f'client connected {address[0]}:{address[1]}'))
        with client:
            client.settimeout(self.client_timeout_sec)
            buffer = ''
            while not self._stop_event.is_set():
                try:
                    data = client.recv(1024)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not data:
                    break
                buffer += data.decode('utf-8', errors='ignore')
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    response = self._handle_command(line.strip())
                    try:
                        client.sendall((response + '\n').encode('utf-8'))
                    except OSError:
                        return
        self.status_pub.publish(String(data=f'client disconnected {address[0]}:{address[1]}'))

    def _handle_command(self, line: str) -> str:
        if not line:
            return 'ERR empty command'
        try:
            payload = json.loads(line)
            if isinstance(payload, dict):
                return self._handle_json(payload)
        except json.JSONDecodeError:
            pass
        return self._handle_text(line)

    def _handle_json(self, payload: Dict) -> str:
        command = str(payload.get('cmd', '')).lower()
        if command in ('move', 'twist'):
            self._publish_twist(float(payload.get('linear', 0.0)), float(payload.get('angular', 0.0)))
            return 'OK move'
        if command == 'mode':
            return self._set_mode(str(payload.get('value', 'manual')))
        if command == 'estop':
            active = bool(payload.get('active', True))
            self.estop_pub.publish(Bool(data=active))
            return f'OK estop {active}'
        return f'ERR unknown json cmd {command}'

    def _handle_text(self, line: str) -> str:
        parts = line.lower().split()
        command = parts[0]
        if command in ('w', 'forward'):
            self._publish_twist(self.linear_speed, 0.0)
        elif command in ('s', 'back', 'backward'):
            self._publish_twist(-self.linear_speed, 0.0)
        elif command in ('a', 'left'):
            self._publish_twist(0.0, self.angular_speed)
        elif command in ('d', 'right'):
            self._publish_twist(0.0, -self.angular_speed)
        elif command in ('x', 'stop'):
            self._publish_twist(0.0, 0.0)
        elif command == 'mode' and len(parts) >= 2:
            return self._set_mode(parts[1])
        elif command == 'estop':
            active = len(parts) == 1 or parts[1] not in ('0', 'false', 'off', 'release')
            self.estop_pub.publish(Bool(data=active))
            return f'OK estop {active}'
        else:
            return f'ERR unknown command {line}'
        return f'OK {command}'

    def _publish_twist(self, linear: float, angular: float) -> None:
        msg = Twist()
        msg.linear.x = linear
        msg.angular.z = angular
        self.cmd_pub.publish(msg)

    def _set_mode(self, mode: str) -> str:
        self.mode_pub.publish(String(data=mode))
        return f'OK mode {mode}'


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
