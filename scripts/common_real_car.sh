#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROS_DISTRO_NAME="${ROS_DISTRO:-foxy}"
LOG_DIR="${LOG_DIR:-${ROOT_DIR}/.run_logs}"
PIDS=()
PGIDS=()

source_ros_environment() {
  local ros_setup="/opt/ros/${ROS_DISTRO_NAME}/setup.bash"
  local workspace_setup="${ROOT_DIR}/install/setup.bash"
  local vendor_library_setup="${ICAR_VENDOR_LIBRARY_SETUP:-/root/icar_ros2_ws/software/library_ws/install/setup.bash}"
  local vendor_workspace_setup="${ICAR_VENDOR_WORKSPACE_SETUP:-/root/icar_ros2_ws/icar_ws/install/setup.bash}"

  if [[ ! -f "${ros_setup}" ]]; then
    echo "错误：找不到 ${ros_setup}。请设置 ROS_DISTRO，或先手动加载 ROS 环境。" >&2
    exit 1
  fi

  if [[ ! -f "${workspace_setup}" ]]; then
    echo "错误：找不到 ${workspace_setup}。请先在 ${ROOT_DIR} 执行 colcon build。" >&2
    exit 1
  fi

  set +u
  # shellcheck source=/dev/null
  source "${ros_setup}"
  # The factory packages (Astra, lidar, base driver and robot description)
  # live in two vendor overlays rather than this repository. A selective
  # colcon build rewrites this workspace's setup files, so source those
  # overlays explicitly before the project overlay is applied.
  for vendor_setup in "${vendor_library_setup}" "${vendor_workspace_setup}"; do
    if [[ -f "${vendor_setup}" ]]; then
      # shellcheck source=/dev/null
      source "${vendor_setup}"
    fi
  done
  # shellcheck source=/dev/null
  source "${workspace_setup}"
  set -u
}

prepare_logs() {
  mkdir -p "${LOG_DIR}"
}

start_background_command() {
  local name=$1
  local log_file=$2
  local command=$3

  echo "启动：${name}"
  echo "  命令：${command}"
  echo "  日志：${log_file}"
  if command -v setsid >/dev/null 2>&1; then
    setsid bash -lc "${command}" >"${log_file}" 2>&1 &
  else
    bash -lc "${command}" >"${log_file}" 2>&1 &
  fi
  register_background_process "$!"
  echo
}

start_background_args() {
  local name=$1
  local log_file=$2
  shift 2

  echo "启动：${name}"
  echo "  日志：${log_file}"
  if command -v setsid >/dev/null 2>&1; then
    setsid "$@" >"${log_file}" 2>&1 &
  else
    "$@" >"${log_file}" 2>&1 &
  fi
  register_background_process "$!"
  echo
}

register_background_process() {
  local pid=$1
  local pgid

  PIDS+=("${pid}")
  sleep 0.1
  pgid="$(ps -o pgid= -p "${pid}" 2>/dev/null | tr -d ' ' || true)"
  if [[ -n "${pgid}" ]]; then
    PGIDS+=("${pgid}")
  else
    PGIDS+=("${pid}")
  fi
}

wait_for_topic() {
  local topic=$1
  local timeout_sec=$2
  local log_file=$3
  local start_time
  start_time=$(date +%s)

  echo "等待话题：${topic}"
  while true; do
    if ros2 topic list 2>/dev/null | grep -qx "${topic}"; then
      echo "  已就绪：${topic}"
      echo
      return 0
    fi

    if (( $(date +%s) - start_time >= timeout_sec )); then
      echo "  警告：等待 ${topic} 超时，请查看 ${log_file}" >&2
      echo
      return 1
    fi
    sleep 1
  done
}

wait_for_node() {
  local node=$1
  local timeout_sec=$2
  local log_file=$3
  local start_time
  start_time=$(date +%s)

  echo "等待节点：${node}"
  while true; do
    if ros2 node list 2>/dev/null | grep -qx "${node}"; then
      echo "  已就绪：${node}"
      echo
      return 0
    fi

    if (( $(date +%s) - start_time >= timeout_sec )); then
      echo "  警告：等待 ${node} 超时，请查看 ${log_file}" >&2
      echo
      return 1
    fi
    sleep 1
  done
}

publish_stop() {
  local i
  for i in 1 2 3; do
    # Never publish to /cmd_vel or /control/cmd_vel here: those are the
    # protected final outputs owned by motion_controller and safety_mux.
    # Sending zero only to mux inputs preserves the single safety outlet.
    ros2 topic pub --once /cmd_vel_manual geometry_msgs/msg/Twist "{}" >/dev/null 2>&1 || true
    ros2 topic pub --once /cmd_vel_nav geometry_msgs/msg/Twist "{}" >/dev/null 2>&1 || true
    ros2 topic pub --once /cmd_vel_lidar geometry_msgs/msg/Twist "{}" >/dev/null 2>&1 || true
    ros2 topic pub --once /cmd_vel_follow geometry_msgs/msg/Twist "{}" >/dev/null 2>&1 || true
    ros2 topic pub --once /cmd_vel_vision geometry_msgs/msg/Twist "{}" >/dev/null 2>&1 || true
    sleep 0.1
  done
  ros2 topic pub --once /mode_select std_msgs/msg/String "{data: manual}" >/dev/null 2>&1 || true
}

stop_background_nodes() {
  for pgid in "${PGIDS[@]}"; do
    if kill -0 -- "-${pgid}" >/dev/null 2>&1; then
      kill -TERM -- "-${pgid}" >/dev/null 2>&1 || true
    fi
  done

  for pid in "${PIDS[@]}"; do
    if kill -0 "${pid}" >/dev/null 2>&1; then
      kill -TERM "${pid}" >/dev/null 2>&1 || true
    fi
  done

  sleep 1

  for pgid in "${PGIDS[@]}"; do
    if kill -0 -- "-${pgid}" >/dev/null 2>&1; then
      kill -KILL -- "-${pgid}" >/dev/null 2>&1 || true
    fi
  done

  for pid in "${PIDS[@]}"; do
    if kill -0 "${pid}" >/dev/null 2>&1; then
      kill -KILL "${pid}" >/dev/null 2>&1 || true
    fi
  done

  wait >/dev/null 2>&1 || true
}

cleanup_common() {
  local exit_code=$?
  trap - EXIT INT TERM HUP
  echo
  echo "正在停止小车运动和后台节点..."
  publish_stop
  stop_background_nodes
  publish_stop
  echo "日志目录：${LOG_DIR}"
  exit "${exit_code}"
}

start_vendor_base_stack() {
  local start_vendor_bringup="${START_VENDOR_BRINGUP:-1}"
  local robot_type="${ROBOT_TYPE:-x3}"
  local rplidar_type="${RPLIDAR_TYPE:-a1}"
  # slam_toolbox and Nav2 need the dynamic odom -> base_footprint transform.
  # The vendor base node is the authoritative source for it; disabling it
  # leaves /odom available but makes both mapping and navigation unable to
  # transform incoming scans.
  local vendor_pub_odom_tf="${VENDOR_PUB_ODOM_TF:-true}"
  local vendor_bringup_cmd="${VENDOR_BRINGUP_CMD:-ros2 launch car_bringup vendor_x3_base_no_joy.launch.py rplidar_type:=${rplidar_type} pub_odom_tf:=${vendor_pub_odom_tf}}"
  local base_driver_cmd="${BASE_DRIVER_CMD:-ros2 run icar_bringup Mcnamu_driver_X3}"
  local lidar_cmd="${LIDAR_CMD:-ros2 launch sllidar_ros2 sllidar_launch.py}"

  if [[ "${start_vendor_bringup}" == "1" ]]; then
    start_background_command "厂家底盘/雷达/TF 总启动" "${LOG_DIR}/vendor_bringup.log" "${vendor_bringup_cmd}"
    wait_for_topic /scan 25 "${LOG_DIR}/vendor_bringup.log" || true
    wait_for_topic /odom 25 "${LOG_DIR}/vendor_bringup.log" || true
    return
  fi

  if [[ "${START_BASE_DRIVER:-1}" == "1" ]]; then
    start_background_command "厂家底盘驱动" "${LOG_DIR}/base_driver.log" "${base_driver_cmd}"
    sleep 2
  fi

  if [[ "${START_LIDAR:-1}" == "1" ]]; then
    start_background_command "雷达驱动" "${LOG_DIR}/lidar.log" "${lidar_cmd}"
    wait_for_topic /scan 20 "${LOG_DIR}/lidar.log" || true
  fi
}

start_vendor_camera() {
  local start_camera="${START_CAMERA:-1}"
  local camera_cmd="${CAMERA_CMD:-ros2 launch astra_camera astra.launch.xml}"

  if [[ "${start_camera}" == "1" ]]; then
    start_background_command "相机驱动" "${LOG_DIR}/camera.log" "${camera_cmd}"
    wait_for_topic /camera/color/image_raw 25 "${LOG_DIR}/camera.log" || true
  fi
}
