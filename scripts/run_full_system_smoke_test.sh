#!/usr/bin/env bash

# iCar 车端全链路无运动冒烟测试。
#
# 这个脚本会依次启动控制/雷达、视觉、建图、导航、巡检与 APP 桥接，
# 检查 ROS 图、关键数据流和 Action/Service。它不会发布运动速度、导航
# 目标、巡检任务或“解除急停”命令；底盘必须放在安全位置并保持有人监护。
#
# 用法：
#   bash scripts/run_full_system_smoke_test.sh
#   SMOKE_MODULES=control,mapping,navigation bash scripts/run_full_system_smoke_test.sh
#   SMOKE_SKIP_MODULES=packages,unit,base,camera bash scripts/run_full_system_smoke_test.sh
#   MAP=/data/maps/lab.yaml SMOKE_MODULES=navigation,mission bash scripts/run_full_system_smoke_test.sh
#   WITH_YOLO=true SMOKE_MODULES=vision_yolo bash scripts/run_full_system_smoke_test.sh
#
# Modules: packages, unit, base, camera, control, vision_color, vision_yolo,
#          mapping, navigation, mission, node_manager.  Every hardware-dependent module
# starts and stops its own prerequisites, so it is safe to run by itself.

set -u -o pipefail

# shellcheck source=scripts/common_real_car.sh
source "$(cd "$(dirname "$0")" && pwd)/common_real_car.sh"

WITH_YOLO="${WITH_YOLO:-false}"
SKIP_UNIT_TESTS="${SKIP_UNIT_TESTS:-false}"
TOPIC_TIMEOUT="${TOPIC_TIMEOUT:-8}"
# Factory base and camera drivers can register their topics before the first
# sensor sample arrives. Keep their one-time warm-up window separate from the
# shorter timeout used for project-node data-flow checks.
HARDWARE_TOPIC_TIMEOUT="${HARDWARE_TOPIC_TIMEOUT:-25}"
HARDWARE_START_ATTEMPTS="${HARDWARE_START_ATTEMPTS:-2}"
GRAPH_DISCOVERY_SPIN_TIME="${GRAPH_DISCOVERY_SPIN_TIME:-5}"
SERVICE_TIMEOUT="${SERVICE_TIMEOUT:-30}"
RUNTIME_SERVICE_TIMEOUT="${RUNTIME_SERVICE_TIMEOUT:-15}"
LIFECYCLE_TIMEOUT="${LIFECYCLE_TIMEOUT:-30}"
SMOKE_MODULES="${SMOKE_MODULES:-all}"
SMOKE_SKIP_MODULES="${SMOKE_SKIP_MODULES:-}"
MAP="${MAP:-}"
APP_BRIDGE_TOKEN="${APP_BRIDGE_TOKEN:-}"
FAILURES=0
CURRENT_PID=""
CURRENT_PGID=""
RUNTIME_LAST_GENERATION=""

pass() {
  echo "[PASS] $*"
}

fail() {
  echo "[FAIL] $*" >&2
  FAILURES=$((FAILURES + 1))
}

skip() {
  echo "[SKIP] $*"
}

csv_contains() {
  local values="${1//[[:space:]]/}"
  local expected=$2
  [[ ",${values}," == *",${expected},"* ]]
}

module_enabled() {
  local module=$1
  if [[ "${SMOKE_MODULES}" != "all" ]] && ! csv_contains "${SMOKE_MODULES}" "${module}"; then
    return 1
  fi
  ! csv_contains "${SMOKE_SKIP_MODULES}" "${module}"
}

is_known_module() {
  case "$1" in
    packages|unit|base|camera|control|vision_color|vision_yolo|mapping|navigation|mission|node_manager)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

validate_module_list() {
  local values=$1
  local allow_all=$2
  local item
  local -a modules
  if [[ -z "${values}" ]]; then
    return 0
  fi
  if [[ "${values}" == "all" && "${allow_all}" == "true" ]]; then
    return 0
  fi
  if csv_contains "${values}" all; then
    fail "模块 all 只能单独用于 SMOKE_MODULES=all"
    return 1
  fi
  IFS=',' read -r -a modules <<<"${values}"
  for item in "${modules[@]}"; do
    item="${item//[[:space:]]/}"
    if [[ -z "${item}" ]] || ! is_known_module "${item}"; then
      fail "未知冒烟测试模块：${item:-<empty>}"
      return 1
    fi
  done
}

stop_stage() {
  if [[ -n "${CURRENT_PID}" || ${#PIDS[@]} -gt 0 ]]; then
    stop_project
    publish_stop
    stop_background_nodes
  fi
  PIDS=()
  PGIDS=()
}

run_module() {
  local module=$1
  shift
  if ! module_enabled "${module}"; then
    skip "模块 ${module} 未选择"
    return
  fi

  stop_stage
  echo
  echo "========================================"
  echo " 独立测试模块：${module}"
  echo "========================================"
  if ! "$@"; then
    skip "模块 ${module} 的前置硬件未就绪，已跳过其余检查"
  fi
  stop_stage
}

topic_has_message() {
  local topic=$1
  local output_file=$2
  local durability="${3:-volatile}"
  local timeout_sec="${4:-${TOPIC_TIMEOUT}}"
  ros2 topic list 2>/dev/null | grep -qx "${topic}" \
    && capture_topic_message "${topic}" "${output_file}" "${durability}" "${timeout_sec}"
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
  elif ros2 node list --no-daemon --spin-time "${GRAPH_DISCOVERY_SPIN_TIME}" 2>/dev/null \
      | grep -qx "${node}"; then
    pass "节点 ${node}（临时图发现）"
  else
    fail "节点 ${node} 未就绪（日志：${log_file}）"
  fi
}

check_topic() {
  local topic=$1
  local log_file=$2
  if ros2 topic list 2>/dev/null | grep -qx "${topic}"; then
    pass "Topic ${topic}"
  else
    fail "Topic ${topic} is not registered (log: ${log_file})"
  fi
}

check_topic_message() {
  local topic=$1
  local log_file=$2
  local durability="${3:-volatile}"
  local timeout_sec="${4:-${TOPIC_TIMEOUT}}"
  if ! ros2 topic list 2>/dev/null | grep -qx "${topic}"; then
    fail "话题 ${topic} 不存在（日志：${log_file}）"
    return 1
  fi
  if capture_topic_message "${topic}" "${log_file}.topic${topic//\//_}.log" "${durability}" "${timeout_sec}"; then
    pass "话题 ${topic} 有新鲜数据"
    return 0
  else
    fail "话题 ${topic} 在 ${timeout_sec} 内没有数据（日志：${log_file}）"
    return 1
  fi
}

capture_topic_message() {
  local topic=$1
  local output_file=$2
  local durability="${3:-volatile}"
  local timeout_sec="${4:-${TOPIC_TIMEOUT}}"
  local start_time child_pid
  : >"${output_file}"
  # ROS 2 Foxy has no single-message echo option. Start echo in the
  # background, wait for its first bytes, then stop only the CLI process.
  env PYTHONUNBUFFERED=1 ros2 topic echo "${topic}" \
    --qos-reliability best_effort --qos-durability "${durability}" \
    >"${output_file}" 2>&1 &
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
    if (( $(date +%s) - start_time >= timeout_sec )); then
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
    if (( $(date +%s) - start_time >= LIFECYCLE_TIMEOUT )); then
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
  local start_time
  start_time=$(date +%s)
  while true; do
    if ros2 service list 2>/dev/null | grep -qx "${service}" \
        || ros2 service list --no-daemon --spin-time "${GRAPH_DISCOVERY_SPIN_TIME}" 2>/dev/null \
          | grep -qx "${service}"; then
      pass "Service ${service}"
      return
    fi
    if (( $(date +%s) - start_time >= SERVICE_TIMEOUT )); then
      fail "Service ${service} 未注册"
      return
    fi
    sleep 1
  done
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
  local attempt
  if [[ -z "${CURRENT_PID}" ]]; then
    return
  fi
  publish_stop
  # ros2 launch handles SIGINT by shutting down its child graph cleanly. A
  # bounded escalation prevents a stale vendor process from hanging the smoke
  # script forever during cleanup.
  if kill -0 -- "-${CURRENT_PGID}" >/dev/null 2>&1; then
    kill -INT -- "-${CURRENT_PGID}" >/dev/null 2>&1 || true
  elif kill -0 "${CURRENT_PID}" >/dev/null 2>&1; then
    kill -INT "${CURRENT_PID}" >/dev/null 2>&1 || true
  fi
  for attempt in {1..50}; do
    if ! kill -0 "${CURRENT_PID}" >/dev/null 2>&1; then
      wait "${CURRENT_PID}" >/dev/null 2>&1 || true
      CURRENT_PID=""
      CURRENT_PGID=""
      sleep 1
      return
    fi
    sleep 0.1
  done
  if kill -0 -- "-${CURRENT_PGID}" >/dev/null 2>&1; then
    kill -TERM -- "-${CURRENT_PGID}" >/dev/null 2>&1 || true
  elif kill -0 "${CURRENT_PID}" >/dev/null 2>&1; then
    kill -TERM "${CURRENT_PID}" >/dev/null 2>&1 || true
  fi
  for attempt in {1..30}; do
    if ! kill -0 "${CURRENT_PID}" >/dev/null 2>&1; then
      wait "${CURRENT_PID}" >/dev/null 2>&1 || true
      CURRENT_PID=""
      CURRENT_PGID=""
      sleep 1
      return
    fi
    sleep 0.1
  done
  if kill -0 -- "-${CURRENT_PGID}" >/dev/null 2>&1; then
    kill -KILL -- "-${CURRENT_PGID}" >/dev/null 2>&1 || true
  elif kill -0 "${CURRENT_PID}" >/dev/null 2>&1; then
    kill -KILL "${CURRENT_PID}" >/dev/null 2>&1 || true
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

start_node_manager() {
  local log_file="${LOG_DIR}/smoke_node_manager.log"
  stop_project
  echo
  echo "========================================"
  echo "  Node manager runtime smoke test"
  echo "  Log: ${log_file}"
  echo "========================================"
  setsid ros2 launch car_bringup node_manager.launch.py "$@" >"${log_file}" 2>&1 &
  CURRENT_PID=$!
  sleep 0.2
  CURRENT_PGID="$(ps -o pgid= -p "${CURRENT_PID}" 2>/dev/null | tr -d ' ' || true)"
  if [[ -z "${CURRENT_PGID}" ]]; then
    CURRENT_PGID="${CURRENT_PID}"
  fi
  sleep 2
}

prepare_base_stack() {
  local attempt=1
  while (( attempt <= HARDWARE_START_ATTEMPTS )); do
    start_vendor_base_stack
    if topic_has_message /scan "${LOG_DIR}/vendor_bringup.scan_probe.log" volatile "${HARDWARE_TOPIC_TIMEOUT}" \
        && topic_has_message /odom "${LOG_DIR}/vendor_bringup.odom_probe.log" volatile "${HARDWARE_TOPIC_TIMEOUT}"; then
      pass "话题 /scan 有新鲜数据"
      pass "话题 /odom 有新鲜数据"
      return 0
    fi

    if (( attempt < HARDWARE_START_ATTEMPTS )); then
      echo "[RETRY] 厂家底盘尚未产生完整传感器数据，重启后重试 (${attempt}/${HARDWARE_START_ATTEMPTS})"
      publish_stop
      stop_background_nodes
      PIDS=()
      PGIDS=()
    fi
    attempt=$((attempt + 1))
  done

  check_topic_message /scan "${LOG_DIR}/vendor_bringup.log" volatile "${HARDWARE_TOPIC_TIMEOUT}" || true
  check_topic_message /odom "${LOG_DIR}/vendor_bringup.log" volatile "${HARDWARE_TOPIC_TIMEOUT}" || true
  return 1
}

prepare_camera() {
  START_V4L2_BRIDGE=1 start_vendor_camera
  check_topic_message /camera/color/image_raw "${LOG_DIR}/camera.log" volatile "${HARDWARE_TOPIC_TIMEOUT}"
}

run_package_module() {
  local package
  for package in \
    car_interfaces car_control car_lidar car_vision car_navigation car_map_manager \
    car_inspection car_mission car_app_bridge car_bringup car_runtime_manager; do
    check_package "${package}"
  done
}

run_base_module() {
  prepare_base_stack
}

run_camera_module() {
  prepare_camera
}

run_control_module() {
  prepare_base_stack || return 1
  start_project control_lidar \
    use_keyboard:=false \
    use_lidar_avoidance:=true \
    use_lidar_warning:=true \
    use_mapping:=false use_navigation:=false use_patrol:=false \
    use_vision:=false vision_use_camera_bridge:=false use_app_bridge:=false
  check_node /safety_mux "${LOG_DIR}/smoke_control_lidar.log"
  check_node /lidar_avoidance "${LOG_DIR}/smoke_control_lidar.log"
  check_node /lidar_warning "${LOG_DIR}/smoke_control_lidar.log"
  check_topic_message /control/effective_estop "${LOG_DIR}/smoke_control_lidar.log" || true
  check_topic_message /control/cmd_vel "${LOG_DIR}/smoke_control_lidar.log" || true
  check_topic_message /cmd_vel "${LOG_DIR}/smoke_control_lidar.log" || true
  check_topic_message /lidar/warning_state "${LOG_DIR}/smoke_control_lidar.log" || true
}

run_vision_color_module() {
  prepare_camera || return 1
  start_project vision_color \
    use_keyboard:=false \
    use_lidar_avoidance:=false \
    use_mapping:=false use_navigation:=false use_patrol:=false \
    use_vision:=true vision_use_camera_bridge:=false use_color_detector:=true use_color_tracker:=false \
    use_yolo:=false use_app_bridge:=false
  check_node /color_detector "${LOG_DIR}/smoke_vision_color.log"
  check_topic_message /vision/detections "${LOG_DIR}/smoke_vision_color.log" || true
}

run_vision_yolo_module() {
  if [[ "${WITH_YOLO}" != "true" ]]; then
    skip "vision_yolo 需要 WITH_YOLO=true"
    return
  fi
  prepare_camera || return 1
  start_project vision_yolo \
    use_keyboard:=false \
    use_lidar_avoidance:=false \
    use_mapping:=false use_navigation:=false use_patrol:=false \
    use_vision:=true vision_use_camera_bridge:=false use_color_detector:=false use_color_tracker:=false \
    use_yolo:=true use_app_bridge:=false
  check_node /yolo_detector "${LOG_DIR}/smoke_vision_yolo.log"
  check_topic_message /vision/detections "${LOG_DIR}/smoke_vision_yolo.log" || true
  check_topic_message /vision/person_estop "${LOG_DIR}/smoke_vision_yolo.log" || true
}

run_mapping_module() {
  prepare_base_stack || return 1
  start_project mapping \
    use_keyboard:=false use_lidar_avoidance:=false \
    use_mapping:=true use_navigation:=false use_patrol:=false \
    use_vision:=false vision_use_camera_bridge:=false use_app_bridge:=false
  check_node /sync_slam_toolbox_node "${LOG_DIR}/smoke_mapping.log"
  check_topic /map "${LOG_DIR}/smoke_mapping.log"
  # On Foxy, lifecycle node discovery can intermittently omit map_saver even
  # after it has activated.  The APP consumes this save_map service, so its
  # registration is the stable, end-to-end readiness contract.
  check_service /map_saver/save_map
}

run_navigation_module() {
  local nav_args=(
    use_keyboard:=false use_lidar_avoidance:=true
    use_mapping:=false use_navigation:=true use_mission:=false use_patrol:=false
    use_vision:=false vision_use_camera_bridge:=false use_app_bridge:=false
  )
  prepare_base_stack || return 1
  if [[ -n "${MAP}" ]]; then
    nav_args+=("map:=${MAP}")
  fi
  start_project navigation "${nav_args[@]}"
  check_node /amcl "${LOG_DIR}/smoke_navigation.log"
  check_node /bt_navigator "${LOG_DIR}/smoke_navigation.log"
  check_node /controller_server "${LOG_DIR}/smoke_navigation.log"
  check_node /planner_server "${LOG_DIR}/smoke_navigation.log"
  if [[ "${NAVIGATION_EXPECT_ACTIVE:-false}" == "true" ]]; then
    check_lifecycle_active /bt_navigator "${LOG_DIR}/smoke_navigation.log"
    check_lifecycle_active /controller_server "${LOG_DIR}/smoke_navigation.log"
    check_lifecycle_active /planner_server "${LOG_DIR}/smoke_navigation.log"
  else
    skip "Nav2 active check requires an operator-provided initial pose"
  fi
  check_topic /map "${LOG_DIR}/smoke_navigation.log"
  check_action /navigate_to_pose
}

run_mission_module() {
  local camera_ready=true
  local mission_args=(
    use_keyboard:=false use_lidar_avoidance:=true
    use_mapping:=false use_navigation:=true use_mission:=true use_patrol:=false
    use_inspection:=true use_vision:=true vision_use_camera_bridge:=false use_color_detector:=true
    use_yolo:="${WITH_YOLO}" use_app_bridge:=true
    mission_require_localization:=true
  )
  prepare_base_stack || return 1
  prepare_camera || camera_ready=false
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
  if [[ "${camera_ready}" == "true" ]]; then
    check_topic_contains /system/health '"healthy":true' "${LOG_DIR}/smoke_mission.log"
    check_topic_contains /system/sensor_fault 'data: false' "${LOG_DIR}/smoke_mission.log"
  else
    skip "Health green-state requires /camera/color/image_raw"
  fi
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
    pass "APP v3 capabilities 请求"
  else
    fail "APP v3 capabilities 请求失败"
  fi
}

request_runtime_profile() {
  local profile=$1
  local request="{\"cmd\":\"runtime_switch\",\"profile\":\"${profile}\"}"
  local output
  local client_auth_args=()
  if [[ -n "${APP_BRIDGE_TOKEN}" ]]; then
    client_auth_args=(--token "${APP_BRIDGE_TOKEN}")
  fi
  # Test the deployed control path (APP -> Bridge -> Manager), not a
  # short-lived ros2 CLI client whose graph discovery is flaky on Foxy.
  if ! output="$(timeout "${RUNTIME_SERVICE_TIMEOUT}" \
      python3 "${ROOT_DIR}/scripts/app_bridge_client.py" --host 127.0.0.1 \
      --timeout "${RUNTIME_SERVICE_TIMEOUT}" "${client_auth_args[@]}" \
      --request "${request}" 2>&1)"; then
    fail "Runtime profile ${profile} request failed: ${output}"
    return 1
  fi
  if grep -Fq '"accepted": true' <<<"${output}"; then
    RUNTIME_LAST_GENERATION="$(sed -n 's/^[[:space:]]*"generation": \([0-9][0-9]*\),\{0,1\}$/\1/p' <<<"${output}" | tail -n 1)"
    if [[ -z "${RUNTIME_LAST_GENERATION}" ]]; then
      fail "Runtime profile ${profile} response omitted generation: ${output}"
      return 1
    fi
    pass "Runtime profile ${profile} request accepted"
    return 0
  fi
  fail "Runtime profile ${profile} was rejected: ${output}"
  return 1
}

wait_runtime_status() {
  local active_profile=$1
  local expected_state=$2
  local log_file=$3
  local expected_generation=${4:-}
  local start_time output_file child_pid
  output_file="${log_file}.runtime_status.log"
  : >"${output_file}"
  env PYTHONUNBUFFERED=1 ros2 topic echo /runtime/status \
    --qos-reliability reliable --qos-durability transient_local >"${output_file}" 2>&1 &
  child_pid=$!
  start_time=$(date +%s)
  while true; do
    if awk -v profile="${active_profile}" -v state="${expected_state}" \
        -v generation="${expected_generation}" '
      $1 == "active_profile:" { active = $2 }
      $1 == "state:" { current_state = $2 }
      $1 == "generation:" { current_generation = $2 }
      $1 == "ready:" {
        if (active == profile && current_state == state && $2 == "true" \
            && (generation == "" || current_generation == generation)) {
          found = 1
          exit
        }
      }
      END { exit(found ? 0 : 1) }
    ' "${output_file}"; then
      stop_runtime_status_subscriber "${child_pid}"
      pass "Runtime status ${active_profile}/${expected_state}"
      return 0
    fi
    if ! kill -0 "${child_pid}" >/dev/null 2>&1; then
      stop_runtime_status_subscriber "${child_pid}"
      fail "Runtime status subscriber exited unexpectedly (log: ${output_file})"
      return 1
    fi
    if (( $(date +%s) - start_time >= SERVICE_TIMEOUT )); then
      stop_runtime_status_subscriber "${child_pid}"
      fail "Runtime status did not reach ${active_profile}/${expected_state} (log: ${output_file})"
      return 1
    fi
    sleep 0.1
  done
}

stop_runtime_status_subscriber() {
  local child_pid=$1
  local attempt
  kill "${child_pid}" >/dev/null 2>&1 || true
  for attempt in {1..20}; do
    if ! kill -0 "${child_pid}" >/dev/null 2>&1; then
      wait "${child_pid}" >/dev/null 2>&1 || true
      return
    fi
    sleep 0.1
  done
  kill -KILL "${child_pid}" >/dev/null 2>&1 || true
  wait "${child_pid}" >/dev/null 2>&1 || true
}

run_node_manager_module() {
  start_node_manager \
    use_keyboard:=false use_camera:=false use_lidar_avoidance:=false \
    initial_profile:=idle
  check_node /node_manager "${LOG_DIR}/smoke_node_manager.log"
  check_node /app_server "${LOG_DIR}/smoke_node_manager.log"
  check_service /runtime/set_profile
  request_runtime_profile mapping || return 1
  wait_runtime_status mapping READY "${LOG_DIR}/smoke_node_manager.log" "${RUNTIME_LAST_GENERATION}"
  check_node /sync_slam_toolbox_node "${LOG_DIR}/smoke_node_manager.log"
  check_service /map_saver/save_map
  request_runtime_profile idle || return 1
  wait_runtime_status idle IDLE "${LOG_DIR}/smoke_node_manager.log" "${RUNTIME_LAST_GENERATION}"
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

  if ! validate_module_list "${SMOKE_MODULES}" true \
      || ! validate_module_list "${SMOKE_SKIP_MODULES}" false; then
    return 1
  fi

  echo "========================================"
  echo " iCar 全链路无运动冒烟测试"
  echo " 不会自动驱动车辆"
  echo "========================================"
  echo "YOLO 检查：${WITH_YOLO}"
  echo "话题等待超时：${TOPIC_TIMEOUT}"
  echo "测试模块：${SMOKE_MODULES}"
  echo "跳过模块：${SMOKE_SKIP_MODULES:-无}"
  echo

  run_module packages run_package_module
  run_module unit run_unit_tests
  run_module base run_base_module
  run_module camera run_camera_module
  run_module control run_control_module
  run_module vision_color run_vision_color_module
  run_module vision_yolo run_vision_yolo_module
  run_module mapping run_mapping_module
  run_module navigation run_navigation_module
  run_module mission run_mission_module
  run_module node_manager run_node_manager_module

  echo
  if (( FAILURES == 0 )); then
    echo "[PASS] 全链路无运动冒烟测试通过。"
  else
    echo "[FAIL] 冒烟测试发现 ${FAILURES} 项问题；请查看 ${LOG_DIR}。" >&2
  fi

  return "${FAILURES}"
}

main "$@"
