#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROS_DISTRO_NAME="${ROS_DISTRO:-foxy}"
LOG_DIR="${LOG_DIR:-${ROOT_DIR}/.run_logs}"
PIDS=()

source_ros_environment() {
  local ros_setup="/opt/ros/${ROS_DISTRO_NAME}/setup.bash"
  local workspace_setup="${ROOT_DIR}/install/setup.bash"

  if [[ ! -f "${ros_setup}" ]]; then
    echo "ERROR: ${ros_setup} not found. Set ROS_DISTRO or source ROS manually." >&2
    exit 1
  fi

  if [[ ! -f "${workspace_setup}" ]]; then
    echo "ERROR: ${workspace_setup} not found. Run colcon build in ${ROOT_DIR} first." >&2
    exit 1
  fi

  set +u
  # shellcheck source=/dev/null
  source "${ros_setup}"
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

  echo "Starting ${name}"
  echo "  command: ${command}"
  echo "  log    : ${log_file}"
  bash -lc "${command}" >"${log_file}" 2>&1 &
  PIDS+=("$!")
  echo
}

start_background_args() {
  local name=$1
  local log_file=$2
  shift 2

  echo "Starting ${name}"
  echo "  log: ${log_file}"
  "$@" >"${log_file}" 2>&1 &
  PIDS+=("$!")
  echo
}

wait_for_topic() {
  local topic=$1
  local timeout_sec=$2
  local log_file=$3
  local start_time
  start_time=$(date +%s)

  echo "Waiting for topic ${topic}"
  while true; do
    if ros2 topic list 2>/dev/null | grep -qx "${topic}"; then
      echo "  ready: ${topic}"
      echo
      return 0
    fi

    if (( $(date +%s) - start_time >= timeout_sec )); then
      echo "  WARN: timed out waiting for ${topic}; check ${log_file}" >&2
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

  echo "Waiting for node ${node}"
  while true; do
    if ros2 node list 2>/dev/null | grep -qx "${node}"; then
      echo "  ready: ${node}"
      echo
      return 0
    fi

    if (( $(date +%s) - start_time >= timeout_sec )); then
      echo "  WARN: timed out waiting for ${node}; check ${log_file}" >&2
      echo
      return 1
    fi
    sleep 1
  done
}

publish_stop() {
  ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{}" >/dev/null 2>&1 || true
  ros2 topic pub --once /cmd_vel_manual geometry_msgs/msg/Twist "{}" >/dev/null 2>&1 || true
  ros2 topic pub --once /control/cmd_vel geometry_msgs/msg/Twist "{}" >/dev/null 2>&1 || true
}

stop_background_nodes() {
  for pid in "${PIDS[@]}"; do
    if kill -0 "${pid}" >/dev/null 2>&1; then
      kill "${pid}" >/dev/null 2>&1 || true
    fi
  done
  wait >/dev/null 2>&1 || true
}

cleanup_common() {
  local exit_code=$?
  trap - EXIT INT TERM
  echo
  echo "Stopping robot motion and background nodes..."
  publish_stop
  stop_background_nodes
  echo "Logs: ${LOG_DIR}"
  exit "${exit_code}"
}

start_vendor_base_stack() {
  local start_vendor_bringup="${START_VENDOR_BRINGUP:-1}"
  local robot_type="${ROBOT_TYPE:-x3}"
  local rplidar_type="${RPLIDAR_TYPE:-a1}"
  local vendor_bringup_cmd="${VENDOR_BRINGUP_CMD:-ros2 launch icar_nav laser_bringup_launch.py robot_type:=${robot_type} rplidar_type:=${rplidar_type}}"
  local base_driver_cmd="${BASE_DRIVER_CMD:-ros2 run icar_bringup Mcnamu_driver_X3}"
  local lidar_cmd="${LIDAR_CMD:-ros2 launch sllidar_ros2 sllidar_launch.py}"

  if [[ "${start_vendor_bringup}" == "1" ]]; then
    start_background_command "vendor base/lidar/TF bringup" "${LOG_DIR}/vendor_bringup.log" "${vendor_bringup_cmd}"
    wait_for_topic /scan 25 "${LOG_DIR}/vendor_bringup.log" || true
    wait_for_topic /odom 25 "${LOG_DIR}/vendor_bringup.log" || true
    return
  fi

  if [[ "${START_BASE_DRIVER:-1}" == "1" ]]; then
    start_background_command "vendor base driver" "${LOG_DIR}/base_driver.log" "${base_driver_cmd}"
    sleep 2
  fi

  if [[ "${START_LIDAR:-1}" == "1" ]]; then
    start_background_command "lidar driver" "${LOG_DIR}/lidar.log" "${lidar_cmd}"
    wait_for_topic /scan 20 "${LOG_DIR}/lidar.log" || true
  fi
}

start_vendor_camera() {
  local start_camera="${START_CAMERA:-1}"
  local camera_cmd="${CAMERA_CMD:-ros2 launch astra_camera astra.launch.xml}"

  if [[ "${start_camera}" == "1" ]]; then
    start_background_command "camera driver" "${LOG_DIR}/camera.log" "${camera_cmd}"
    wait_for_topic /camera/color/image_raw 25 "${LOG_DIR}/camera.log" || true
  fi
}
