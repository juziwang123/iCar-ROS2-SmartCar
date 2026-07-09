#!/usr/bin/env bash

# 实车雷达功能一键测试脚本。
#
# 使用示例：
#   bash scripts/start_lidar_test.sh
#   USE_TRACKER=true bash scripts/start_lidar_test.sh
#   USE_WARNING=true USE_AVOIDANCE=false bash scripts/start_lidar_test.sh
#   START_VENDOR_BRINGUP=0 bash scripts/start_lidar_test.sh
#
# 安全提示：
#   第一次运行建议把小车架空，确认方向和速度正常后再落地。
#   按 Ctrl+C 会停止脚本，并发布零速度。

set -euo pipefail

# shellcheck source=scripts/common_real_car.sh
source "$(cd "$(dirname "$0")" && pwd)/common_real_car.sh"

USE_AVOIDANCE="${USE_AVOIDANCE:-true}"
USE_TRACKER="${USE_TRACKER:-false}"
USE_WARNING="${USE_WARNING:-false}"
USE_KEYBOARD="${USE_KEYBOARD:-true}"

main() {
  source_ros_environment
  prepare_logs
  trap cleanup_common EXIT INT TERM

  echo "========================================"
  echo "  iCar 雷达功能测试"
  echo "========================================"
  echo "避障功能：${USE_AVOIDANCE}"
  echo "跟随功能：${USE_TRACKER}"
  echo "警戒功能：${USE_WARNING}"
  echo "键盘遥控：${USE_KEYBOARD}"
  echo

  start_vendor_base_stack

  start_background_args \
    "本项目控制链路和雷达节点" \
    "${LOG_DIR}/lidar_test.log" \
    ros2 launch car_bringup bringup.launch.py \
      use_keyboard:="${USE_KEYBOARD}" \
      use_lidar_avoidance:="${USE_AVOIDANCE}" \
      use_lidar_tracker:="${USE_TRACKER}" \
      use_lidar_warning:="${USE_WARNING}" \
      use_mapping:=false \
      use_navigation:=false \
      use_patrol:=false \
      use_vision:=false \
      use_app_bridge:=false

  wait_for_node /safety_mux 20 "${LOG_DIR}/lidar_test.log" || true
  if [[ "${USE_AVOIDANCE}" == "true" ]]; then
    wait_for_node /lidar_avoidance 20 "${LOG_DIR}/lidar_test.log" || true
  fi
  if [[ "${USE_TRACKER}" == "true" ]]; then
    wait_for_node /lidar_tracker 20 "${LOG_DIR}/lidar_test.log" || true
    ros2 topic pub --once /mode_select std_msgs/msg/String "{data: follow}" >/dev/null 2>&1 || true
  fi
  if [[ "${USE_WARNING}" == "true" ]]; then
    wait_for_node /lidar_warning 20 "${LOG_DIR}/lidar_test.log" || true
  fi

  echo "雷达测试正在运行。可在另一个终端查看："
  echo "  ros2 topic echo /lidar/override_active"
  echo "  ros2 topic echo /cmd_vel_lidar"
  echo "  ros2 topic echo /lidar/warning_state"
  echo "在当前终端按 Ctrl+C 停止。"
  while true; do sleep 1; done
}

main "$@"
