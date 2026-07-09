#!/usr/bin/env bash

# 视觉功能一键测试脚本。
#
# 使用示例：
#   bash scripts/start_vision_test.sh
#   USE_TRACKER=true bash scripts/start_vision_test.sh
#   USE_YOLO=true bash scripts/start_vision_test.sh
#   START_CAMERA=0 bash scripts/start_vision_test.sh

set -euo pipefail

# shellcheck source=scripts/common_real_car.sh
source "$(cd "$(dirname "$0")" && pwd)/common_real_car.sh"

USE_COLOR_DETECTOR="${USE_COLOR_DETECTOR:-true}"
USE_TRACKER="${USE_TRACKER:-false}"
USE_YOLO="${USE_YOLO:-false}"
USE_KEYBOARD="${USE_KEYBOARD:-false}"

main() {
  source_ros_environment
  prepare_logs
  trap cleanup_common EXIT INT TERM HUP

  echo "========================================"
  echo "  iCar 视觉功能测试"
  echo "========================================"
  echo "颜色检测：${USE_COLOR_DETECTOR}"
  echo "颜色追踪：${USE_TRACKER}"
  echo "YOLO 检测：${USE_YOLO}"
  echo

  start_vendor_base_stack
  start_vendor_camera

  start_background_args \
    "本项目控制链路和视觉节点" \
    "${LOG_DIR}/vision_test.log" \
    ros2 launch car_bringup bringup.launch.py \
      use_keyboard:="${USE_KEYBOARD}" \
      use_lidar_avoidance:=true \
      use_lidar_tracker:=false \
      use_lidar_warning:=false \
      use_mapping:=false \
      use_navigation:=false \
      use_patrol:=false \
      use_vision:=true \
      use_color_detector:="${USE_COLOR_DETECTOR}" \
      use_color_tracker:="${USE_TRACKER}" \
      use_yolo:="${USE_YOLO}"

  wait_for_node /safety_mux 20 "${LOG_DIR}/vision_test.log" || true
  wait_for_node /color_detector 20 "${LOG_DIR}/vision_test.log" || true
  if [[ "${USE_TRACKER}" == "true" ]]; then
    wait_for_node /color_tracker 20 "${LOG_DIR}/vision_test.log" || true
    ros2 topic pub --once /mode_select std_msgs/msg/String "{data: vision}" >/dev/null 2>&1 || true
  fi

  echo "视觉测试正在运行。可在另一个终端查看："
  echo "  ros2 topic echo /vision/color_target"
  echo "  ros2 topic echo /vision/detections"
  echo "  ros2 topic echo /cmd_vel_vision"
  echo "在当前终端按 Ctrl+C 停止。"
  while true; do sleep 1; done
}

main "$@"
