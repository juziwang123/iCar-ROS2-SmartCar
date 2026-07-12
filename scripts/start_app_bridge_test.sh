#!/usr/bin/env bash

# APP/TCP 控制桥接一键测试脚本。
#
# 使用示例：
#   bash scripts/start_app_bridge_test.sh
#   PORT=9000 bash scripts/start_app_bridge_test.sh
#
# 在另一个终端启动 v2 协议交互客户端：
#   python3 scripts/app_bridge_client.py --host 127.0.0.1 --port 8765 --interactive

set -euo pipefail

# shellcheck source=scripts/common_real_car.sh
source "$(cd "$(dirname "$0")" && pwd)/common_real_car.sh"

USE_KEYBOARD="${USE_KEYBOARD:-false}"
PORT="${PORT:-8765}"
APP_BRIDGE_TOKEN="${APP_BRIDGE_TOKEN:-}"

main() {
  source_ros_environment
  prepare_logs
  trap cleanup_common EXIT INT TERM HUP

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

  local client_auth_args=()
  if [[ -n "${APP_BRIDGE_TOKEN}" ]]; then
    client_auth_args=(--token "${APP_BRIDGE_TOKEN}")
  fi
  if python3 "${ROOT_DIR}/scripts/app_bridge_client.py" \
      --host 127.0.0.1 --port "${PORT}" "${client_auth_args[@]}" \
      --request '{"cmd":"capabilities"}'; then
    echo "APP v2 capabilities 检查通过。"
  else
    echo "警告：APP v2 capabilities 检查失败，请查看 ${LOG_DIR}/app_bridge_test.log" >&2
  fi

  echo "APP 桥接服务正在运行。"
  echo "可在另一个终端执行："
  echo "  python3 scripts/app_bridge_client.py --host 127.0.0.1 --port ${PORT} --interactive"
  echo "若配置了 auth_token，在命令中追加 --token '<token>'。"
  echo "先输入 {\"cmd\":\"teleop_acquire\"}，记录返回的 lease_id；随后使用："
  echo "  {\"cmd\":\"move\",\"lease_id\":\"<lease_id>\",\"linear\":0.1,\"angular\":0.0}"
  echo "结束时输入 {\"cmd\":\"teleop_release\",\"lease_id\":\"<lease_id>\"}。"
  echo "在当前终端按 Ctrl+C 停止。"
  while true; do sleep 1; done
}

main "$@"
