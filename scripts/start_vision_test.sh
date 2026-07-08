#!/usr/bin/env bash

# One-key vision test.
#
# Examples:
#   bash scripts/start_vision_test.sh
#   USE_TRACKER=true bash scripts/start_vision_test.sh
#   USE_YOLO=true MODEL_PATH=/path/to/model.onnx bash scripts/start_vision_test.sh
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
  trap cleanup_common EXIT INT TERM

  echo "========================================"
  echo "  iCar vision test"
  echo "========================================"
  echo "color detector: ${USE_COLOR_DETECTOR}"
  echo "color tracker : ${USE_TRACKER}"
  echo "yolo detector : ${USE_YOLO}"
  echo

  start_vendor_base_stack
  start_vendor_camera

  start_background_args \
    "project control + vision nodes" \
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

  echo "Vision test is running. Useful monitors:"
  echo "  ros2 topic echo /vision/color_target"
  echo "  ros2 topic echo /vision/detections"
  echo "  ros2 topic echo /cmd_vel_vision"
  echo "Press Ctrl+C here to stop."
  while true; do sleep 1; done
}

main "$@"
