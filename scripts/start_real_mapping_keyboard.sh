#!/usr/bin/env bash

# 一键启动实车建图 + 键盘遥控。
#
# 使用方式：
#   cd ~/ros2_ws
#   source /opt/ros/foxy/setup.bash
#   source install/setup.bash
#   bash scripts/start_real_mapping_keyboard.sh
#
# 常用可选参数：
#   USE_RVIZ=true bash scripts/start_real_mapping_keyboard.sh
#   USE_LIDAR_AVOIDANCE=true bash scripts/start_real_mapping_keyboard.sh
#   START_BASE_DRIVER=0 bash scripts/start_real_mapping_keyboard.sh
#   START_LIDAR=0 bash scripts/start_real_mapping_keyboard.sh

set -euo pipefail

# =========================
# 配置区：按实车情况可覆盖
# =========================

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ROS_DISTRO_NAME="${ROS_DISTRO:-foxy}"
LOG_DIR="${ROOT_DIR}/.run_logs"
MAP_SAVE_PREFIX="${MAP_SAVE_PREFIX:-${ROOT_DIR}/src/car_navigation/maps/lab_map}"

# 默认使用本项目封装的厂家基础 bringup：启动底盘、里程计/EKF、雷达和必要 TF，但不启动厂家 joy_ctrl。
START_VENDOR_BRINGUP="${START_VENDOR_BRINGUP:-1}"
ROBOT_TYPE="${ROBOT_TYPE:-x3}"
RPLIDAR_TYPE="${RPLIDAR_TYPE:-a1}"
VENDOR_BRINGUP_CMD="${VENDOR_BRINGUP_CMD:-ros2 launch car_bringup vendor_x3_base_no_joy.launch.py rplidar_type:=${RPLIDAR_TYPE}}"

# 如果不使用厂家完整 bringup，可以分开启动底盘/雷达。
START_BASE_DRIVER="${START_BASE_DRIVER:-1}"
START_LIDAR="${START_LIDAR:-1}"

# 是否随建图启动 RViz。Jetson 图形压力较大时建议保持 false。
USE_RVIZ="${USE_RVIZ:-false}"

# 是否启用本项目雷达避障输出。首次建图建议 false，避免影响手动扫图。
USE_LIDAR_AVOIDANCE="${USE_LIDAR_AVOIDANCE:-false}"

# 建图输入。A1 雷达通常直接使用 /scan；S2/4ROS 点数较多时可启用降采样。
MAPPING_SCAN_TOPIC="${MAPPING_SCAN_TOPIC:-/scan}"
MAPPING_USE_SCAN_FILTER="${MAPPING_USE_SCAN_FILTER:-false}"
MAPPING_SCAN_FILTER_MULTIPLE="${MAPPING_SCAN_FILTER_MULTIPLE:-2}"

# 如果不用厂家完整 bringup，可打开这两个静态 TF 兜底。
MAPPING_PUBLISH_LASER_TF="${MAPPING_PUBLISH_LASER_TF:-false}"
MAPPING_PUBLISH_BASE_LINK_TF="${MAPPING_PUBLISH_BASE_LINK_TF:-false}"

# 厂家节点命令。如你的车上包名不同，可通过环境变量覆盖。
BASE_DRIVER_CMD="${BASE_DRIVER_CMD:-ros2 run icar_bringup Mcnamu_driver_X3}"
LIDAR_CMD="${LIDAR_CMD:-ros2 launch sllidar_ros2 sllidar_launch.py}"

PIDS=()
PGIDS=()

# =========================
# 工具函数
# =========================

print_title() {
  echo
  echo "========================================"
  echo "  iCar 实车建图与键盘遥控启动器"
  echo "========================================"
  echo
}

print_config() {
  echo "当前配置："
  echo "  ROS 版本        : ${ROS_DISTRO_NAME}"
  echo "  工作空间        : ${ROOT_DIR}"
  echo "  日志目录        : ${LOG_DIR}"
  echo "  地图保存前缀    : ${MAP_SAVE_PREFIX}"
  echo "  厂家完整启动    : ${START_VENDOR_BRINGUP}"
  echo "  车型/雷达       : ${ROBOT_TYPE} / ${RPLIDAR_TYPE}"
  echo "  启动底盘驱动    : ${START_BASE_DRIVER}"
  echo "  启动雷达驱动    : ${START_LIDAR}"
  echo "  启动 RViz       : ${USE_RVIZ}"
  echo "  启用雷达避障    : ${USE_LIDAR_AVOIDANCE}"
  echo "  建图 scan       : ${MAPPING_SCAN_TOPIC}"
  echo "  scan 降采样     : ${MAPPING_USE_SCAN_FILTER}"
  echo "  发布 laser TF   : ${MAPPING_PUBLISH_LASER_TF}"
  echo
}

print_keys() {
  echo "键盘控制说明："
  echo "  w / s  : 前进 / 后退"
  echo "  a / d  : 左转 / 右转"
  echo "  q / e  : 左前弧线 / 右前弧线"
  echo "  x      : 停止"
  echo "  空格   : 急停"
  echo "  r      : 解除急停"
  echo "  m      : 切回手动模式"
  echo "  Ctrl+C : 结束建图流程"
  echo
}

source_ros_environment() {
  local ros_setup="/opt/ros/${ROS_DISTRO_NAME}/setup.bash"
  local workspace_setup="${ROOT_DIR}/install/setup.bash"

  if [[ ! -f "${ros_setup}" ]]; then
    echo "错误：找不到 ${ros_setup}" >&2
    echo "请确认小车 ROS2 环境已安装，或设置 ROS_DISTRO=foxy。" >&2
    exit 1
  fi

  if [[ ! -f "${workspace_setup}" ]]; then
    echo "错误：找不到 ${workspace_setup}" >&2
    echo "请先在 ${ROOT_DIR} 执行 colcon build。" >&2
    exit 1
  fi

  # ROS2 Foxy 的 setup.bash 会读取少量未预先定义的环境变量。
  # 这里临时关闭 nounset，避免 set -u 把正常的 setup 流程误判为错误。
  set +u
  # shellcheck source=/dev/null
  source "${ros_setup}"
  # shellcheck source=/dev/null
  source "${workspace_setup}"
  set -u
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
  ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{}" >/dev/null 2>&1 || true
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

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM HUP

  echo
  echo "正在停止小车运动和后台节点..."
  publish_stop
  stop_background_nodes

  echo
  echo "建图流程已结束。"
  echo
  echo "如果地图效果满意，请执行下面的命令保存地图："
  echo "  ros2 run nav2_map_server map_saver_cli -f ${MAP_SAVE_PREFIX}"
  echo
  echo "地图会保存为："
  echo "  ${MAP_SAVE_PREFIX}.yaml"
  echo "  ${MAP_SAVE_PREFIX}.pgm"
  echo
  echo "本次运行日志目录："
  echo "  ${LOG_DIR}"
  echo

  exit "${exit_code}"
}

# =========================
# 启动流程
# =========================

main() {
  if [[ ! -t 0 ]]; then
    echo "错误：键盘遥控需要在交互式终端中运行。" >&2
    exit 1
  fi

  source_ros_environment
  mkdir -p "${LOG_DIR}"
  trap cleanup EXIT INT TERM HUP

  print_title
  print_config
  print_keys

  if [[ "${START_VENDOR_BRINGUP}" == "1" ]]; then
    start_background_command "厂家底盘/雷达/TF 启动（不启动 joy_ctrl）" "${LOG_DIR}/vendor_bringup.log" "${VENDOR_BRINGUP_CMD}"
    wait_for_topic /scan 25 "${LOG_DIR}/vendor_bringup.log" || true
    wait_for_topic /odom 25 "${LOG_DIR}/vendor_bringup.log" || true
  else
    if [[ "${START_BASE_DRIVER}" == "1" ]]; then
      start_background_command "厂家底盘驱动" "${LOG_DIR}/base_driver.log" "${BASE_DRIVER_CMD}"
      sleep 2
    else
      echo "跳过厂家底盘驱动：START_BASE_DRIVER=0"
      echo
    fi

    if [[ "${START_LIDAR}" == "1" ]]; then
      start_background_command "激光雷达驱动" "${LOG_DIR}/lidar.log" "${LIDAR_CMD}"
      wait_for_topic /scan 20 "${LOG_DIR}/lidar.log" || true
    else
      echo "跳过激光雷达驱动：START_LIDAR=0"
      echo
    fi
  fi

  start_background_args \
    "本项目建图与控制链路" \
    "${LOG_DIR}/bringup_mapping.log" \
    ros2 launch car_bringup bringup.launch.py \
      use_keyboard:=false \
      use_mapping:=true \
      mapping_use_rviz:="${USE_RVIZ}" \
      mapping_scan_topic:="${MAPPING_SCAN_TOPIC}" \
      mapping_use_scan_filter:="${MAPPING_USE_SCAN_FILTER}" \
      mapping_scan_filter_multiple:="${MAPPING_SCAN_FILTER_MULTIPLE}" \
      mapping_publish_laser_tf:="${MAPPING_PUBLISH_LASER_TF}" \
      mapping_publish_base_link_tf:="${MAPPING_PUBLISH_BASE_LINK_TF}" \
      use_sim_time:=false \
      use_lidar_avoidance:="${USE_LIDAR_AVOIDANCE}" \
      use_lidar_tracker:=false \
      use_navigation:=false \
      use_patrol:=false

  wait_for_node /safety_mux 20 "${LOG_DIR}/bringup_mapping.log" || true
  wait_for_node /sync_slam_toolbox_node 20 "${LOG_DIR}/bringup_mapping.log" || true

  echo "准备完成，现在进入键盘遥控。"
  echo "请低速移动小车，让雷达逐步扫完整个场地。"
  echo "想查看建图效果，可在另一个终端运行 rviz2，并添加 /map、/scan、/tf、/odom。"
  echo

  ros2 run car_control keyboard_teleop
}

main "$@"
