#!/usr/bin/env bash

# 启动真实路线巡检联调环境。脚本只启动依赖，不会自动下发巡检任务或移动小车。
#
# 使用示例：
#   bash scripts/start_mission_test.sh
#   MAP=/data/maps/lab.yaml ROUTE=/data/routes/night.yaml ROUTE_ID=night_route \
#     bash scripts/start_mission_test.sh
#   USE_YOLO=true USE_RVIZ=true bash scripts/start_mission_test.sh

set -euo pipefail

# shellcheck source=scripts/common_real_car.sh
source "$(cd "$(dirname "$0")" && pwd)/common_real_car.sh"

MAP="${MAP:-${ROOT_DIR}/src/car_navigation/maps/lab_map.yaml}"
ROUTE="${ROUTE:-${ROOT_DIR}/src/car_mission/config/demo_inspection_route.yaml}"
ROUTE_ID="${ROUTE_ID:-demo_visual_inspection}"
USE_YOLO="${USE_YOLO:-false}"
USE_RVIZ="${USE_RVIZ:-false}"
APP_BRIDGE_PORT="${APP_BRIDGE_PORT:-8765}"

main() {
  source_ros_environment
  prepare_logs
  trap cleanup_common EXIT INT TERM HUP

  echo "========================================"
  echo "  iCar 巡检任务联调环境"
  echo "========================================"
  echo "地图：${MAP}"
  echo "路线：${ROUTE}"
  echo "路线 ID：${ROUTE_ID}"
  echo "YOLO：${USE_YOLO}"
  echo "本脚本不会自动启动巡检任务或移动小车。"
  echo

  start_vendor_base_stack
  start_vendor_camera
  if ! wait_for_topic /camera/color/image_raw 5 "${LOG_DIR}/camera.log"; then
    echo "错误：巡检必须有 RGB 图像。当前 Astra 驱动未发布 /camera/color/image_raw。" >&2
    echo "请先用正确的相机启动配置启用彩色流，再重新运行本脚本。" >&2
    echo "可通过 CAMERA_CMD 覆盖，例如 Astra Pro Plus 常用的 astrapro 启动文件。" >&2
    exit 1
  fi

  start_background_args \
    "导航、巡检、视觉、健康监测和 APP 桥接" \
    "${LOG_DIR}/mission_test.log" \
    ros2 launch car_bringup bringup.launch.py \
      use_keyboard:=false \
      use_lidar_avoidance:=true \
      use_lidar_tracker:=false \
      use_lidar_warning:=true \
      use_mapping:=false \
      use_navigation:=true \
      use_mission:=true \
      use_patrol:=false \
      use_inspection:=true \
      use_vision:=true \
      use_color_detector:=true \
      use_color_tracker:=false \
      use_yolo:="${USE_YOLO}" \
      use_app_bridge:=true \
      app_bridge_port:="${APP_BRIDGE_PORT}" \
      navigation_use_rviz:="${USE_RVIZ}" \
      map:="${MAP}" \
      mission_route_file:="${ROUTE}" \
      mission_require_localization:=true

  wait_for_node /safety_mux 20 "${LOG_DIR}/mission_test.log" || true
  wait_for_node /mission_manager 30 "${LOG_DIR}/mission_test.log" || true
  wait_for_node /health_monitor 30 "${LOG_DIR}/mission_test.log" || true
  wait_for_node /checkpoint_verifier 30 "${LOG_DIR}/mission_test.log" || true
  wait_for_node /inspection_executor 30 "${LOG_DIR}/mission_test.log" || true
  wait_for_node /app_server 30 "${LOG_DIR}/mission_test.log" || true

  echo
  echo "依赖已启动。先在 RViz 或 APP 中设置正确初始位姿，然后另开终端："
  echo "  source ${ROOT_DIR}/install/setup.bash"
  echo "  ros2 run car_bringup icar console"
  echo "  icar> status"
  echo "  icar> start ${ROUTE_ID} 0 0"
  echo "运行中可使用 pause、resume、cancel、report；人工接管必须先 pause。"
  echo "查看状态：ros2 topic echo /mission/status"
  echo "查看事件：ros2 topic echo /mission/event"
  echo "在当前终端按 Ctrl+C 停止并安全清理。"
  while true; do sleep 1; done
}

main "$@"
