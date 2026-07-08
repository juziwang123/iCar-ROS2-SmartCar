#!/usr/bin/env bash

# One-key real-car lidar test.
#
# Examples:
#   bash scripts/start_lidar_test.sh
#   USE_TRACKER=true bash scripts/start_lidar_test.sh
#   USE_WARNING=true USE_AVOIDANCE=false bash scripts/start_lidar_test.sh
#   START_VENDOR_BRINGUP=0 bash scripts/start_lidar_test.sh
#
# Safety:
#   Put the car on blocks for the first run.
#   Press Ctrl+C to stop and publish zero velocity.

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
  echo "  iCar lidar test"
  echo "========================================"
  echo "avoidance: ${USE_AVOIDANCE}"
  echo "tracker  : ${USE_TRACKER}"
  echo "warning  : ${USE_WARNING}"
  echo "keyboard : ${USE_KEYBOARD}"
  echo

  start_vendor_base_stack

  start_background_args \
    "project control + lidar nodes" \
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

  echo "Lidar test is running. Useful monitors:"
  echo "  ros2 topic echo /lidar/override_active"
  echo "  ros2 topic echo /cmd_vel_lidar"
  echo "  ros2 topic echo /lidar/warning_state"
  echo "Press Ctrl+C here to stop."
  while true; do sleep 1; done
}

main "$@"
