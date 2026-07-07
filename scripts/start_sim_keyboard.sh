#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SIM_WORLD="$ROOT_DIR/install/wpr_simulation2/share/wpr_simulation2/worlds/wpb_simple.world"
LOG_DIR="$ROOT_DIR/.run_logs"

cd "$ROOT_DIR"
set +u
source /opt/ros/humble/setup.bash
source install/setup.bash
set -u

mkdir -p "$LOG_DIR"

if [[ ! -t 0 ]]; then
  echo "This script must be run from an interactive terminal." >&2
  exit 1
fi

stop_existing_stack() {
  pkill -f "/opt/ros/humble/bin/ros2 launch wpr_simulation2 wpb_simple.launch.py" 2>/dev/null || true
  pkill -f "/opt/ros/humble/bin/ros2 launch car_bringup bringup.launch.py" 2>/dev/null || true
  pkill -f "$ROOT_DIR/install/car_control/lib/car_control/keyboard_teleop" 2>/dev/null || true
  pkill -f "gzserver $SIM_WORLD" 2>/dev/null || true
  pkill -f "gzclient --gui-client-plugin=libgazebo_ros_eol_gui.so" 2>/dev/null || true
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  stop_existing_stack

  exit "$exit_code"
}

wait_for_service() {
  local service_name=$1
  local timeout_sec=$2
  local start_time
  start_time=$(date +%s)

  while true; do
    if ros2 service list 2>/dev/null | grep -qx "$service_name"; then
      return 0
    fi

    if (( $(date +%s) - start_time >= timeout_sec )); then
      return 1
    fi

    sleep 1
  done
}

wait_for_node() {
  local node_name=$1
  local timeout_sec=$2
  local start_time
  start_time=$(date +%s)

  while true; do
    if ros2 node list 2>/dev/null | grep -qx "$node_name"; then
      return 0
    fi

    if (( $(date +%s) - start_time >= timeout_sec )); then
      return 1
    fi

    sleep 1
  done
}

trap cleanup EXIT INT TERM

stop_existing_stack

sleep 2

setsid ros2 launch wpr_simulation2 wpb_simple.launch.py >"$LOG_DIR/sim.log" 2>&1 &

if ! wait_for_service /spawn_entity 20; then
  echo "Simulation failed to expose /spawn_entity. See $LOG_DIR/sim.log" >&2
  exit 1
fi

setsid ros2 launch car_bringup bringup.launch.py \
  use_keyboard:=false \
  use_mapping:=false \
  use_navigation:=false \
  use_patrol:=false \
  use_lidar_avoidance:=false \
  use_lidar_tracker:=false >"$LOG_DIR/bringup.log" 2>&1 &

if ! wait_for_node /safety_mux 15; then
  echo "Bringup failed to start /safety_mux. See $LOG_DIR/bringup.log" >&2
  exit 1
fi

echo "Simulation and control stack are running."
echo "Keyboard control keys: w/s/a/d move, q/e arc, x stop, m manual, space estop, r reset."
echo "Simulation log: $LOG_DIR/sim.log"
echo "Bringup log: $LOG_DIR/bringup.log"

ros2 run car_control keyboard_teleop \
  --ros-args \
  --params-file install/car_bringup/share/car_bringup/config/params.yaml