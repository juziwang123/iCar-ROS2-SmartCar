#!/usr/bin/env bash

# 自主导航功能一键测试脚本。
#
# 使用示例：
#   bash scripts/start_navigation_test.sh
#   SEND_GOAL=true GOAL_X=1.0 GOAL_Y=0.0 GOAL_YAW=0.0 bash scripts/start_navigation_test.sh
#   NAV_MODE=legacy_patrol USE_RVIZ=true bash scripts/start_navigation_test.sh
#   MAP=/地图文件绝对路径/map.yaml bash scripts/start_navigation_test.sh

set -euo pipefail

# shellcheck source=scripts/common_real_car.sh
source "$(cd "$(dirname "$0")" && pwd)/common_real_car.sh"

NAV_MODE="${NAV_MODE:-single}"
USE_RVIZ="${USE_RVIZ:-false}"
MAP="${MAP:-${ROOT_DIR}/src/car_navigation/maps/lab_map.yaml}"
GOAL_X="${GOAL_X:-0.5}"
GOAL_Y="${GOAL_Y:-0.0}"
GOAL_YAW="${GOAL_YAW:-0.0}"
SEND_GOAL="${SEND_GOAL:-false}"
WAYPOINTS_FILE="${WAYPOINTS_FILE:-${ROOT_DIR}/src/car_navigation/config/waypoints.yaml}"

main() {
  source_ros_environment
  prepare_logs
  trap cleanup_common EXIT INT TERM HUP

  echo "========================================"
  echo "  iCar 自主导航测试"
  echo "========================================"
  echo "导航模式：${NAV_MODE}"
  echo "地图文件：${MAP}"
  echo "启动 RViz：${USE_RVIZ}"
  echo

  start_vendor_base_stack

  if [[ "${NAV_MODE}" != "single" && "${NAV_MODE}" != "legacy_patrol" ]]; then
    echo "错误：NAV_MODE 只能是 single 或 legacy_patrol。巡检请使用 start_mission_test.sh。" >&2
    exit 2
  fi

  if [[ "${NAV_MODE}" == "legacy_patrol" ]]; then
    start_background_args \
      "本项目多点巡航导航" \
      "${LOG_DIR}/navigation_patrol.log" \
      ros2 launch car_bringup bringup.launch.py \
        use_keyboard:=false \
        use_lidar_avoidance:=true \
        use_lidar_tracker:=false \
        use_lidar_warning:=false \
        use_mapping:=false \
        use_navigation:=false \
        use_patrol:=true \
        navigation_use_rviz:="${USE_RVIZ}" \
        map:="${MAP}" \
        waypoints_file:="${WAYPOINTS_FILE}" \
        use_sim_time:=false
  else
    start_background_args \
      "本项目单点目标导航" \
      "${LOG_DIR}/navigation_single.log" \
      ros2 launch car_bringup bringup.launch.py \
        use_keyboard:=false \
        use_lidar_avoidance:=true \
        use_lidar_tracker:=false \
        use_lidar_warning:=false \
        use_mapping:=false \
        use_navigation:=true \
        use_patrol:=false \
        navigation_use_rviz:="${USE_RVIZ}" \
        navigation_goal_x:="${GOAL_X}" \
        navigation_goal_y:="${GOAL_Y}" \
        navigation_goal_yaw:="${GOAL_YAW}" \
        navigation_send_goal:="${SEND_GOAL}" \
        map:="${MAP}" \
        use_sim_time:=false
  fi

  wait_for_node /safety_mux 20 "${LOG_DIR}/navigation_${NAV_MODE}.log" || true
  wait_for_node /bt_navigator 60 "${LOG_DIR}/navigation_${NAV_MODE}.log" || true

  ros2 topic pub --once /mode_select std_msgs/msg/String "{data: nav}" >/dev/null 2>&1 || true
  if [[ "${NAV_MODE}" == "single" && "${SEND_GOAL}" != "true" ]]; then
    echo "Nav2 已启动但未下发目标。请在另一个终端使用控制台："
    echo "  ros2 run car_bringup icar console"
    echo "  icar> mode nav"
    echo "  icar> nav <x> <y> <yaw>"
  fi
  echo "导航测试正在运行。在当前终端按 Ctrl+C 停止。"
  while true; do sleep 1; done
}

main "$@"
