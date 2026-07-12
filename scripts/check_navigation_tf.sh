#!/usr/bin/env bash

# Diagnose the TF links Nav2/AMCL require without commanding vehicle motion.
# Run after the vendor base stack is already running.

set -euo pipefail

# shellcheck source=scripts/common_real_car.sh
source "$(cd "$(dirname "$0")" && pwd)/common_real_car.sh"

TF_TIMEOUT="${TF_TIMEOUT:-8}"

check_transform() {
  local target=$1
  local source=$2
  local output
  output=$(timeout "${TF_TIMEOUT}" ros2 run tf2_ros tf2_echo "${target}" "${source}" 2>&1 || true)
  if grep -Eq 'Translation:|At time ' <<<"${output}"; then
    echo "[PASS] TF ${target} -> ${source} 可用"
    return 0
  fi
  echo "[FAIL] TF ${target} -> ${source} 不可用或时间戳不匹配" >&2
  printf '%s\n' "${output}" >&2
  return 1
}

main() {
  source_ros_environment
  local failures=0
  check_transform odom base_footprint || failures=$((failures + 1))
  check_transform base_footprint laser || failures=$((failures + 1))
  if (( failures > 0 )); then
    echo "请确认仅有一个节点发布 odom -> base_footprint，并检查 /scan 的 header.stamp 与 /tf 时间一致。" >&2
  fi
  return "${failures}"
}

main "$@"
