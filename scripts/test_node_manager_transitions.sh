#!/usr/bin/env bash

# Safe on-car integration test for node_manager.  It starts the persistent
# foundation once, switches mapping on/off through the APP bridge, and checks
# the exact transition generation reported by /runtime/status.  Supplying
# MAP_ID also exercises navigation through the APP.  MAP_PATH exercises the
# same navigation profile through the ROS service; supplying ROUTE_FILE then
# additionally checks the mission profile (the APP uses stored route IDs).
#
# Run inside the project Docker container after colcon build:
#   bash scripts/test_node_manager_transitions.sh
#   MAP_ID=lab_20260713 bash scripts/test_node_manager_transitions.sh
#   MAP_PATH=/root/.icar/maps/lab/map.yaml ROUTE_FILE=/root/routes/demo.yaml \
#     bash scripts/test_node_manager_transitions.sh

set -euo pipefail

# shellcheck source=scripts/common_real_car.sh
source "$(cd "$(dirname "$0")" && pwd)/common_real_car.sh"

PROFILE_TIMEOUT="${PROFILE_TIMEOUT:-60}"
APP_BRIDGE_TOKEN="${APP_BRIDGE_TOKEN:-}"
MAP_ID="${MAP_ID:-}"
MAP_PATH="${MAP_PATH:-}"
ROUTE_FILE="${ROUTE_FILE:-}"
LOG_FILE="${LOG_DIR}/node_manager_transitions.log"
STATUS_FILE="${LOG_DIR}/node_manager_runtime_status.log"
STATUS_SUBSCRIBER_PID=""

cleanup() {
  trap - EXIT INT TERM HUP
  if [[ -n "${STATUS_SUBSCRIBER_PID}" ]]; then
    kill "${STATUS_SUBSCRIBER_PID}" >/dev/null 2>&1 || true
    wait "${STATUS_SUBSCRIBER_PID}" >/dev/null 2>&1 || true
  fi
  publish_stop
  stop_background_nodes
  publish_stop
}

start_status_recorder() {
  : >"${STATUS_FILE}"
  env PYTHONUNBUFFERED=1 ros2 topic echo /runtime/status --qos-reliability reliable \
    --qos-durability transient_local >"${STATUS_FILE}" 2>&1 &
  STATUS_SUBSCRIBER_PID=$!
}

wait_for_runtime_state() {
  local profile=$1 state=$2 generation=$3
  local start_time
  start_time=$(date +%s)
  while (( $(date +%s) - start_time < PROFILE_TIMEOUT )); do
    if awk -v profile="${profile}" -v state="${state}" -v generation="${generation}" '
      $1 == "active_profile:" { active = $2 }
      $1 == "state:" { current_state = $2 }
      $1 == "generation:" { current_generation = $2 }
      $1 == "ready:" {
        if (active == profile && current_state == state && current_generation == generation && $2 == "true") {
          found = 1
          exit
        }
      }
      END { exit(found ? 0 : 1) }
    ' "${STATUS_FILE}"; then
      echo "[PASS] ${profile}/${state}, generation ${generation}"
      return 0
    fi
    sleep 0.2
  done
  echo "[FAIL] /runtime/status did not reach ${profile}/${state}, generation ${generation}" >&2
  return 1
}

generation_from_json() {
  sed -n 's/^[[:space:]]*"generation": \([0-9][0-9]*\),\{0,1\}$/\1/p' | tail -n 1
}

switch_with_app() {
  local profile=$1 map_id=${2:-}
  local request output generation
  request="{\"cmd\":\"runtime_switch\",\"profile\":\"${profile}\"}"
  if [[ -n "${map_id}" ]]; then
    request="{\"cmd\":\"runtime_switch\",\"profile\":\"${profile}\",\"map_id\":\"${map_id}\"}"
  fi
  local -a auth_args=()
  [[ -z "${APP_BRIDGE_TOKEN}" ]] || auth_args=(--token "${APP_BRIDGE_TOKEN}")
  output="$(python3 "${ROOT_DIR}/scripts/app_bridge_client.py" --host 127.0.0.1 \
    --timeout 15 "${auth_args[@]}" --request "${request}")"
  grep -Fq '"accepted": true' <<<"${output}"
  generation="$(generation_from_json <<<"${output}")"
  [[ -n "${generation}" ]] || { echo "missing generation: ${output}" >&2; return 1; }
  printf '%s\n' "${generation}"
}

switch_with_service() {
  local profile=$1 map_path=$2 route_file=$3
  local output generation
  output="$(timeout 15 ros2 service call /runtime/set_profile car_interfaces/srv/SetRuntimeProfile \
    "{profile: '${profile}', map_path: '${map_path}', route_file: '${route_file}', use_yolo: false}")"
  grep -Eq '^[[:space:]]*accepted:[[:space:]]+true$|accepted=True' <<<"${output}"
  generation="$(sed -n \
    -e 's/^[[:space:]]*generation:[[:space:]]*\([0-9][0-9]*\)$/\1/p' \
    -e 's/.*generation=\([0-9][0-9]*\).*/\1/p' <<<"${output}" | tail -n 1)"
  [[ -n "${generation}" ]] || { echo "missing generation: ${output}" >&2; return 1; }
  printf '%s\n' "${generation}"
}

main() {
  source_ros_environment
  prepare_logs
  trap cleanup EXIT INT TERM HUP
  start_background_args node_manager "${LOG_FILE}" ros2 launch car_bringup node_manager.launch.py \
    use_keyboard:=false use_camera:=false use_lidar_avoidance:=false initial_profile:=idle
  wait_for_node /node_manager 30 "${LOG_FILE}"
  wait_for_node /app_server 30 "${LOG_FILE}"
  timeout 30 bash -c 'until ros2 service list | grep -qx /runtime/set_profile; do sleep 1; done'
  start_status_recorder
  sleep 1

  local generation
  generation="$(switch_with_app mapping)"
  wait_for_runtime_state mapping READY "${generation}"
  generation="$(switch_with_app idle)"
  wait_for_runtime_state idle IDLE "${generation}"

  if [[ -n "${MAP_ID}" ]]; then
    generation="$(switch_with_app navigation "${MAP_ID}")"
    wait_for_runtime_state navigation READY "${generation}"
    generation="$(switch_with_app idle)"
    wait_for_runtime_state idle IDLE "${generation}"
  fi
  if [[ -n "${MAP_PATH}" ]]; then
    generation="$(switch_with_service navigation "${MAP_PATH}" '')"
    wait_for_runtime_state navigation READY "${generation}"
    generation="$(switch_with_app idle)"
    wait_for_runtime_state idle IDLE "${generation}"
  fi
  if [[ -n "${ROUTE_FILE}" ]]; then
    [[ -n "${MAP_PATH}" ]] || {
      echo 'MAP_PATH is required when ROUTE_FILE is set for mission testing' >&2
      return 2
    }
    generation="$(switch_with_service mission "${MAP_PATH}" "${ROUTE_FILE}")"
    wait_for_runtime_state mission READY "${generation}"
    generation="$(switch_with_app idle)"
    wait_for_runtime_state idle IDLE "${generation}"
  fi
  echo '[PASS] node_manager transition test completed'
}

main "$@"
