#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "Building Docker image for iCar (ROS2 Foxy)..."
docker build -t icar-ros2:latest .

echo ""
echo "Build done. Usage:"
echo "  docker-compose run --rm icar bash"
echo "  docker-compose up -d"
