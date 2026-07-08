#!/usr/bin/env python3
"""iCar 手机 APP 后端服务。

Flask + SocketIO + ROS2 桥接，严格按 docs/APP接口文档.md 实现。
"""

import json
import os
import signal
import subprocess
import threading
from typing import Any, Dict, List, Optional

import rclpy
from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import Bool, String

# ── Flask 应用 ──────────────────────────────────────────────
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── 进程管理 ─────────────────────────────────────────────────
_processes: Dict[str, subprocess.Popen] = {}

PROCESS_COMMANDS: Dict[str, List[str]] = {
    # 基础控制
    "chassis": ["ros2", "run", "icar_bringup", "Mcnamu_driver_X3"],
    "lidar": ["ros2", "launch", "sllidar_ros2", "sllidar_launch.py"],
    # 雷达
    "avoidance": ["ros2", "run", "icar_laser", "laser_Avoidance_a1_X3"],
    "tracker": ["ros2", "run", "icar_laser", "laser_Tracker_a1_X3"],
    "guard": ["ros2", "run", "icar_laser", "laser_Warning_a1_X3"],
    # 建图 & 导航
    "mapping": ["ros2", "launch", "yahboomcar_nav", "map_gmapping_launch.py"],
    "mapping_display": ["ros2", "launch", "yahboomcar_nav", "display_map_launch.py"],
    "save_map": ["ros2", "launch", "yahboomcar_nav", "save_map_launch.py"],
    "nav_bringup": ["ros2", "launch", "yahboomcar_nav", "laser_bringup_launch.py"],
    "nav_display": ["ros2", "launch", "yahboomcar_nav", "display_nav_launch.py"],
    "nav_dwa": ["ros2", "launch", "yahboomcar_nav", "navigation_dwa_launch.py"],
    "nav_teb": ["ros2", "launch", "yahboomcar_nav", "navigation_teb_launch.py"],
    # 视觉
    "camera": ["ros2", "launch", "astra_camera", "astra.launch.xml"],
    "color_detect": ["ros2", "run", "icar_astra", "colorHSV"],
    "color_track": ["ros2", "run", "icar_astra", "colorTracker"],
}


# ── 跨线程共享状态 ───────────────────────────────────────────
_state: Dict[str, Any] = {
    "mode": "manual",
    "estop": False,
    "linear_x": 0.0,
    "angular_z": 0.0,
    "running_nodes": [],
}
_state_lock = threading.Lock()


# ── HTTP 接口 ────────────────────────────────────────────────
@app.route("/api/state")
def api_state():
    with _state_lock:
        return jsonify(dict(_state))


@app.route("/api/cmd", methods=["POST"])
def api_cmd():
    data = request.get_json(force=True)
    err = _dispatch_cmd(data)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True})


@app.route("/api/process/start", methods=["POST"])
def api_process_start():
    data = request.get_json(force=True)
    function = data.get("function", "")
    if function not in PROCESS_COMMANDS:
        return jsonify({"ok": False, "error": f"unknown function: {function}"}), 400
    if function in _processes:
        return jsonify({"ok": False, "error": f"already running: {function}"}), 400

    cmd = PROCESS_COMMANDS[function]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _processes[function] = proc
        return jsonify({"ok": True, "pid": proc.pid})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/process/stop", methods=["POST"])
def api_process_stop():
    data = request.get_json(force=True)
    function = data.get("function", "")
    if function not in _processes:
        return jsonify({"ok": False, "error": f"not running: {function}"}), 400

    proc = _processes.pop(function)
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    return jsonify({"ok": True})


# ── WebSocket 事件 ───────────────────────────────────────────
@socketio.on("cmd")
def on_cmd(data: dict):
    err = _dispatch_cmd(data)
    if err:
        emit("error", {"error": err})


# ── 指令分发 ─────────────────────────────────────────────────
def _dispatch_cmd(data: dict) -> Optional[str]:
    kind = data.get("type", "")
    ros_node = _get_ros_node()
    if ros_node is None:
        return "ROS node not ready"

    if kind == "move":
        linear = float(data.get("linear", 0.0))
        angular = float(data.get("angular", 0.0))
        linear = max(-0.5, min(0.5, linear))
        angular = max(-1.0, min(1.0, angular))
        with _state_lock:
            if _state.get("estop"):
                return "estop active, move refused"
        ros_node.publish_manual(linear, angular)
    elif kind == "stop":
        ros_node.publish_manual(0.0, 0.0)
    elif kind == "mode":
        mode = str(data.get("mode", "manual"))
        if mode not in ("manual", "nav", "vision", "follow"):
            return f"unknown mode: {mode}"
        ros_node.publish_mode(mode)
    elif kind == "estop":
        active = bool(data.get("active", True))
        ros_node.publish_estop(active)
    else:
        return f"unknown type: {kind}"
    return None


# ── ROS2 节点 ─────────────────────────────────────────────────
_ros_node = None


def _get_ros_node():
    return _ros_node


class AppBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("app_bridge")
        self.cmd_pub = self.create_publisher(Twist, "/cmd_vel_manual", 10)
        self.mode_pub = self.create_publisher(String, "/mode_select", 10)
        self.estop_pub = self.create_publisher(Bool, "/emergency_stop", 10)
        self.create_subscription(Odometry, "/odom", self._on_odom, 10)
        self.create_timer(0.2, self._broadcast_state)

    def publish_manual(self, linear: float, angular: float) -> None:
        msg = Twist()
        msg.linear.x = linear
        msg.angular.z = angular
        self.cmd_pub.publish(msg)

    def publish_mode(self, mode: str) -> None:
        self.mode_pub.publish(String(data=mode))
        with _state_lock:
            _state["mode"] = mode

    def publish_estop(self, active: bool) -> None:
        self.estop_pub.publish(Bool(data=active))
        with _state_lock:
            _state["estop"] = active

    def _on_odom(self, msg: Odometry) -> None:
        with _state_lock:
            _state["linear_x"] = round(msg.twist.twist.linear.x, 3)
            _state["angular_z"] = round(msg.twist.twist.angular.z, 3)

    def _broadcast_state(self) -> None:
        with _state_lock:
            _state["running_nodes"] = list(_processes.keys())
            payload = dict(_state)
        socketio.emit("state", payload)


def main(args=None) -> None:
    global _ros_node
    rclpy.init(args=args)
    _ros_node = AppBridgeNode()

    ros_thread = threading.Thread(target=rclpy.spin, args=(_ros_node,), daemon=True)
    ros_thread.start()

    host = "0.0.0.0"
    port = 5000
    _ros_node.get_logger().info(f"APP bridge starting on http://{host}:{port}")
    socketio.run(app, host=host, port=port, allow_unsafe_werkzeug=True)
