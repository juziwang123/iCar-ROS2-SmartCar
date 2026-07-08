#!/usr/bin/env bash

# One-key APP/TCP bridge test.
#
# Examples:
#   bash scripts/start_app_bridge_test.sh
#   PORT=9000 bash scripts/start_app_bridge_test.sh
#
# From another terminal:
#   printf 'forward\nstop\nmode nav\nestop off\n' | nc <car-ip> 8765
#   printf '{"cmd":"move","linear":0.1,"angular":0.0}\n' | nc <car-ip> 8765

set -euo pipefail

# shellcheck source=scripts/common_real_car.sh
source "$(cd "$(dirname "$0")" && pwd)/common_real_car.sh"

USE_KEYBOARD="${USE_KEYBOARD:-false}"
PORT="${PORT:-8765}"

main() {
  source_ros_environment
  prepare_logs
  trap cleanup_common EXIT INT TERM

  echo "========================================"
  echo "  iCar APP bridge test"
  echo "========================================"
  echo "port: ${PORT}"
  echo

  start_vendor_base_stack

  start_background_args \
    "project control + app bridge" \
    "${LOG_DIR}/app_bridge_test.log" \
    ros2 launch car_bringup bringup.launch.py \
      use_keyboard:="${USE_KEYBOARD}" \
      use_lidar_avoidance:=true \
      use_lidar_tracker:=false \
      use_lidar_warning:=false \
      use_mapping:=false \
      use_navigation:=false \
      use_patrol:=false \
      use_vision:=false \
      use_app_bridge:=true \
      app_bridge_port:="${PORT}" \
      app_bridge_params_file:="${ROOT_DIR}/src/car_app_bridge/config/app_bridge.yaml"

  wait_for_node /safety_mux 20 "${LOG_DIR}/app_bridge_test.log" || true
  wait_for_node /app_server 20 "${LOG_DIR}/app_bridge_test.log" || true

  echo "APP bridge is running."
  echo "Try from another terminal:"
  echo "  printf 'forward\\nstop\\n' | nc <car-ip> ${PORT}"
  echo "  printf '{\"cmd\":\"move\",\"linear\":0.1,\"angular\":0.0}\\n' | nc <car-ip> ${PORT}"
  echo "Press Ctrl+C here to stop."
  while true; do sleep 1; done
}

main "$@"
