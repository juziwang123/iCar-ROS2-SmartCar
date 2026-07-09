#!/usr/bin/env bash

# APP/TCP 控制桥接一键测试脚本。
#
# 使用示例：
#   bash scripts/start_app_bridge_test.sh
#   PORT=9000 bash scripts/start_app_bridge_test.sh
#
# 在另一个终端发送测试命令：
#   printf 'forward\nstop\nmode nav\nestop off\n' | nc <小车IP> 8765
#   printf '{"cmd":"move","linear":0.1,"angular":0.0}\n' | nc <小车IP> 8765

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
  echo "  iCar APP/TCP 桥接测试"
  echo "========================================"
  echo "监听端口：${PORT}"
  echo

  start_vendor_base_stack

  start_background_args \
    "本项目控制链路和 APP 桥接节点" \
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

  echo "APP 桥接服务正在运行。"
  echo "可在另一个终端尝试："
  echo "  printf 'forward\\nstop\\n' | nc <小车IP> ${PORT}"
  echo "  printf '{\"cmd\":\"move\",\"linear\":0.1,\"angular\":0.0}\\n' | nc <小车IP> ${PORT}"
  echo "在当前终端按 Ctrl+C 停止。"
  while true; do sleep 1; done
}

main "$@"
