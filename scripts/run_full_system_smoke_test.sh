#!/usr/bin/env bash

# iCar 车端全链路无运动冒烟测试。
#
# 这个脚本会依次启动控制/雷达、视觉、建图、导航、巡检与 APP 桥接，
# 检查 ROS 图、关键数据流和 Action/Service。它不会发布运动速度、导航
# 目标、巡检任务或“解除急停”命令；底盘必须放在安全位置并保持有人监护。
#
# 用法：
#   bash scripts/run_full_system_smoke_test.sh
#   MAP=/data/maps/lab.yaml bash scripts/run_full_system_smoke_test.sh
#   WITH_YOLO=true TOPIC_TIMEOUT=12 bash scripts/run_full_system_smoke_test.sh
#   SKIP_UNIT_TESTS=true START_CAMERA=0 bash scripts/run_full_system_smoke_test.sh

set -u -o pipefail

# shellcheck source=scripts/common_real_car.sh
source "$(cd "$(dirname "$0")" && pwd)/common_real_car.sh"

WITH_YOLO="${WITH_YOLO:-false}"
SKIP_UNIT_TESTS="${SKIP_UNIT_TESTS:-false}"
TOPIC_TIMEOUT="${TOPIC_TIMEOUT:-8}"
MAP="${MAP:-}"
APP_BRIDGE_TOKEN="${APP_BRIDGE_TOKEN:-}"
FAILURES=0
CURRENT_PID=""
CURRENT_PGID=""

pass() {
  echo "[PASS] $*"
}

fail() {
  echo "[FAIL] $*" >&2
  FAILURES=$((FAILURES + 1))
}

check_package() {
  local package=$1
  if ros2 pkg prefix "${package}" >/dev/null 2>&1; then
    pass "软件包 ${package} 已安装"
  else
    fail "找不到软件包 ${package}；请确认已 source install/setup.bash"
  fi
}

check_node() {
  local node=$1
  local log_file=$2
  if wait_for_node "${node}" 20 "${log_file}"; then
    pass "节点 ${node}"
  else
    fail "节点 ${node} 未就绪（日志：${log_file}）"
  fi
}

check_topic_message() {
  local topic=$1
  local log_file=$2
  if ! ros2 topic list 2>/dev/null | grep -qx "${topic}"; then
    fail "话题 ${topic} 不存在（日志：${log_file}）"
    return
  fi
  if capture_topic_message "${topic}" "${log_file}.topic${topic//\//_}.log"; then
    pass "话题 ${topic} 有新鲜数据"
  else
    fail "话题 ${topic} 在 ${TOPIC_TIMEOUT} 内没有数据（日志：${log_file}）"
  fi
}

capture_topic_message() {
  local topic=$1
  local output_file=$2
  local start_time child_pid
  : >"${output_file}"
  # ROS 2 Foxy has no single-message echo option. Start echo in the
  # background, wait for its first bytes, then stop only the CLI process.
  ros2 topic echo "${topic}" --qos-reliability best_effort >"${output_file}" 2>&1 &
  child_pid=$!
  start_time=$(date +%s)
  while true; do
    if [[ -s "${output_file}" ]]; then
      if grep -Eqi '(^usage:|^ros2: error:|unrecognized arguments)' "${output_file}"; then
        kill "${child_pid}" >/dev/null 2>&1 || true
        wait "${child_pid}" >/dev/null 2>&1 || true
        return 1
      fi
      kill "${child_pid}" >/dev/null 2>&1 || true
      wait "${child_pid}" >/dev/null 2>&1 || true
      return 0
    fi
    if ! kill -0 "${child_pid}" >/dev/null 2>&1; then
      wait "${child_pid}" >/dev/null 2>&1 || true
      return 1
    fi
    if (( $(date +%s) - start_time >= TOPIC_TIMEOUT )); then
      kill "${child_pid}" >/dev/null 2>&1 || true
      wait "${child_pid}" >/dev/null 2>&1 || true
      return 1
    fi
    sleep 0.1
  done
}

check_topic_contains() {
  local topic=$1
  local expected=$2
  local log_file=$3
  local output_file="${log_file}.topic${topic//\//_}.log"
  if ! ros2 topic list 2>/dev/null | grep -qx "${topic}"; then
    fail "话题 ${topic} 不存在（日志：${log_file}）"
    return
  fi
  if capture_topic_message "${topic}" "${output_file}" \
      && grep -Fq "${expected}" "${output_file}"; then
    pass "话题 ${topic} 包含预期状态 ${expected}"
  else
    fail "话题 ${topic} 未报告预期状态 ${expected}（日志：${output_file}）"
  fi
}

check_lifecycle_active() {
  local node=$1
  local log_file=$2
  local start_time state
  start_time=$(date +%s)
  while true; do
    state=$(ros2 lifecycle get "${node}" 2>&1 || true)
    if grep -Eqi 'active.*\[3\]|\[3\].*active' <<<"${state}"; then
      pass "生命周期节点 ${node} 已激活"
      return
    fi
    if (( $(date +%s) - start_time >= 20 )); then
      printf '%s\n' "${state}" >>"${log_file}"
      fail "生命周期节点 ${node} 未进入 active（日志：${log_file}）"
      return
    fi
    sleep 1
  done
}

check_action() {
  local action=$1
  if ros2 action list 2>/dev/null | grep -qx "${action}"; then
    pass "Action ${action}"
  else
    fail "Action ${action} 未注册"
  fi
}

check_service() {
  local service=$1
  if ros2 service list 2>/dev/null | grep -qx "${service}"; then
    pass "Service ${service}"
  else
    fail "Service ${service} 未注册"
  fi
}

start_project() {
  local name=$1
  shift
  local log_file="${LOG_DIR}/smoke_${name}.log"

  stop_project
  echo
  echo "========================================"
  echo "  测试阶段：${name}"
  echo "  日志：${log_file}"
  echo "========================================"
  setsid ros2 launch car_bringup bringup.launch.py "$@" >"${log_file}" 2>&1 &
  CURRENT_PID=$!
  sleep 0.2
  CURRENT_PGID="$(ps -o pgid= -p "${CURRENT_PID}" 2>/dev/null | tr -d ' ' || true)"
  if [[ -z "${CURRENT_PGID}" ]]; then
    CURRENT_PGID="${CURRENT_PID}"
  fi
  sleep 2
}

stop_project() {
  if [[ -z "${CURRENT_PID}" ]]; then
    return
  fi
  publish_stop
  if kill -0 -- "-${CURRENT_PGID}" >/dev/null 2>&1; then
    kill -TERM -- "-${CURRENT_PGID}" >/dev/null 2>&1 || true
  elif kill -0 "${CURRENT_PID}" >/dev/null 2>&1; then
    kill -TERM "${CURRENT_PID}" >/dev/null 2>&1 || true
  fi
  wait "${CURRENT_PID}" >/dev/null 2>&1 || true
  CURRENT_PID=""
  CURRENT_PGID=""
  sleep 1
}

run_unit_tests() {
  if [[ "${SKIP_UNIT_TESTS}" == "true" ]]; then
    echo "[SKIP] 已跳过纯 Python 单元测试"
    return
  fi
  echo
  echo "========================================"
  echo "  纯 Python 单元测试"
  echo "========================================"
  if (cd "${ROOT_DIR}" && python3 -m unittest discover -s tests -v); then
    pass "纯 Python 单元测试"
  else
    fail "纯 Python 单元测试失败"
  fi
}

cleanup() {
  trap - EXIT INT TERM HUP
  stop_project
  publish_stop
  stop_background_nodes
  publish_stop
  echo
  echo "测试日志目录：${LOG_DIR}"
}

main() {
  source_ros_environment
  prepare_logs
  trap cleanup EXIT INT TERM HUP

  echo "========================================"
  echo " iCar 全链路无运动冒烟测试"
  echo " 不会自动驱动车辆"
  echo "========================================"
  echo "YOLO 检查：${WITH_YOLO}"
  echo "话题等待超时：${TOPIC_TIMEOUT}"
  echo

  for package in \
    car_interfaces car_control car_lidar car_vision car_navigation car_map_manager \
    car_inspection car_mission car_app_bridge car_bringup; do
    check_package "${package}"
  done
  run_unit_tests

  # 厂家底盘/雷达和相机只启动一次；其余工程节点在每个互斥阶段重启。
  start_vendor_base_stack
  start_vendor_camera
  check_topic_message /scan "${LOG_DIR}/vendor_bringup.log"
  check_topic_message /odom "${LOG_DIR}/vendor_bringup.log"
  check_topic_message /camera/color/image_raw "${LOG_DIR}/camera.log"

  start_project control_lidar \
    use_keyboard:=false \
    use_lidar_avoidance:=true \
    use_lidar_warning:=true \
    use_mapping:=false use_navigation:=false use_patrol:=false \
    use_vision:=false use_app_bridge:=false
  check_node /safety_mux "${LOG_DIR}/smoke_control_lidar.log"
  check_node /motion_controller "${LOG_DIR}/smoke_control_lidar.log"
  check_node /lidar_avoidance "${LOG_DIR}/smoke_control_lidar.log"
  check_node /lidar_warning "${LOG_DIR}/smoke_control_lidar.log"
  check_topic_message /control/effective_estop "${LOG_DIR}/smoke_control_lidar.log"
  check_topic_message /control/cmd_vel "${LOG_DIR}/smoke_control_lidar.log"
  check_topic_message /lidar/warning_state "${LOG_DIR}/smoke_control_lidar.log"

  start_project vision_color \
    use_keyboard:=false \
    use_lidar_avoidance:=false \
    use_mapping:=false use_navigation:=false use_patrol:=false \
    use_vision:=true use_color_detector:=true use_color_tracker:=false \
    use_yolo:=false use_app_bridge:=false
  check_node /color_detector "${LOG_DIR}/smoke_vision_color.log"
  check_topic_message /vision/detections "${LOG_DIR}/smoke_vision_color.log"
  if [[ "${WITH_YOLO}" == "true" ]]; then
    # Do not run color_detector here: both detectors publish /vision/detections
    # and would let a failed YOLO node be hidden by color-detector messages.
    start_project vision_yolo \
      use_keyboard:=false \
      use_lidar_avoidance:=false \
      use_mapping:=false use_navigation:=false use_patrol:=false \
      use_vision:=true use_color_detector:=false use_color_tracker:=false \
      use_yolo:=true use_app_bridge:=false
    check_node /yolo_detector "${LOG_DIR}/smoke_vision_yolo.log"
    check_topic_message /vision/detections "${LOG_DIR}/smoke_vision_yolo.log"
    check_topic_message /vision/person_estop "${LOG_DIR}/smoke_vision_yolo.log"
  fi

  start_project mapping \
    use_keyboard:=false use_lidar_avoidance:=false \
    use_mapping:=true use_navigation:=false use_patrol:=false \
    use_vision:=false use_app_bridge:=false
  check_node /sync_slam_toolbox_node "${LOG_DIR}/smoke_mapping.log"
  check_node /map_saver "${LOG_DIR}/smoke_mapping.log"
  check_lifecycle_active /map_saver "${LOG_DIR}/smoke_mapping.log"
  check_topic_message /map "${LOG_DIR}/smoke_mapping.log"
  check_service /map_saver/save_map

  local nav_args=(
    use_keyboard:=false use_lidar_avoidance:=true
    use_mapping:=false use_navigation:=true use_mission:=false use_patrol:=false
    use_vision:=false use_app_bridge:=false
  )
  if [[ -n "${MAP}" ]]; then
    nav_args+=("map:=${MAP}")
  fi
  start_project navigation "${nav_args[@]}"
  check_node /amcl "${LOG_DIR}/smoke_navigation.log"
  check_node /bt_navigator "${LOG_DIR}/smoke_navigation.log"
  check_node /controller_server "${LOG_DIR}/smoke_navigation.log"
  check_node /planner_server "${LOG_DIR}/smoke_navigation.log"
  check_lifecycle_active /bt_navigator "${LOG_DIR}/smoke_navigation.log"
  check_lifecycle_active /controller_server "${LOG_DIR}/smoke_navigation.log"
  check_lifecycle_active /planner_server "${LOG_DIR}/smoke_navigation.log"
  check_topic_message /map "${LOG_DIR}/smoke_navigation.log"
  check_action /navigate_to_pose

  local mission_args=(
    use_keyboard:=false use_lidar_avoidance:=true
    use_mapping:=false use_navigation:=true use_mission:=true use_patrol:=false
    use_inspection:=true use_vision:=true use_color_detector:=true
    use_yolo:="${WITH_YOLO}" use_app_bridge:=true
    mission_require_localization:=true
  )
  if [[ -n "${MAP}" ]]; then
    mission_args+=("map:=${MAP}")
  fi
  start_project mission "${mission_args[@]}"
  check_node /mission_manager "${LOG_DIR}/smoke_mission.log"
  check_node /health_monitor "${LOG_DIR}/smoke_mission.log"
  check_node /checkpoint_verifier "${LOG_DIR}/smoke_mission.log"
  check_node /inspection_executor "${LOG_DIR}/smoke_mission.log"
  check_node /app_server "${LOG_DIR}/smoke_mission.log"
  check_node /lidar_avoidance "${LOG_DIR}/smoke_mission.log"
  check_topic_contains /system/health '"healthy":true' "${LOG_DIR}/smoke_mission.log"
  check_topic_contains /system/sensor_fault 'data: false' "${LOG_DIR}/smoke_mission.log"
  check_action /execute_patrol
  check_action /verify_checkpoint
  check_action /run_inspection
  check_service /mission/control
  local client_auth_args=()
  if [[ -n "${APP_BRIDGE_TOKEN}" ]]; then
    client_auth_args=(--token "${APP_BRIDGE_TOKEN}")
  fi
  if python3 "${ROOT_DIR}/scripts/app_bridge_client.py" \
      --host 127.0.0.1 "${client_auth_args[@]}" \
      --request '{"cmd":"capabilities"}'; then
    pass "APP v2 capabilities 请求"
  else
    fail "APP v2 capabilities 请求失败"
  fi

  echo
  if (( FAILURES == 0 )); then
    echo "[PASS] 全链路无运动冒烟测试通过。"
  else
    echo "[FAIL] 冒烟测试发现 ${FAILURES} 项问题；请查看 ${LOG_DIR}。" >&2
  fi

  return "${FAILURES}"
}

main "$@"
