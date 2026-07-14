#!/usr/bin/env bash
# Start the iCar APP/ROS runtime on the Jetson host.
# Run on the Jetson host: bash scripts/start_app_runtime_on_jetson.sh

set -euo pipefail

CONTAINER_NAME="icar-smartcar"
IMAGE="icar/ros-foxy:1.0.2"
HOST_PROJECT="/home/jetson/temp/icar_ros2_ws/icar_ws/src/iCar-ROS2-SmartCar"
CONTAINER_PROJECT="/root/icar_ros2_ws/temp/icar_ros2_ws/icar_ws/src/iCar-ROS2-SmartCar"

for device in /dev/myserial /dev/rplidar /dev/astradepth /dev/astrauvc /dev/video0 /dev/input; do
  if [[ ! -e "$device" ]]; then
    echo "Missing required device: $device" >&2
    echo "Check the cable and udev device aliases before starting." >&2
    exit 1
  fi
done

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Missing Docker image: $IMAGE" >&2
  exit 1
fi

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "$CONTAINER_NAME is already running."
  exit 0
fi

# Remove only an older stopped instance of this project container.  This does
# not affect the vendor containers; do not run both stacks simultaneously.
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  docker rm "$CONTAINER_NAME" >/dev/null
fi

docker run -d --name "$CONTAINER_NAME" --net=host \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v /home/jetson/temp:/root/icar_ros2_ws/temp \
  -v /home/jetson/rosboard:/root/rosboard \
  -v /home/jetson/maps:/root/maps \
  --device=/dev/astradepth \
  --device=/dev/astrauvc \
  --device=/dev/video0 \
  --device=/dev/myserial:/dev/myserial \
  --device=/dev/rplidar:/dev/rplidar \
  --device=/dev/input \
  "$IMAGE" bash -lc "
    source /opt/ros/foxy/setup.bash
    source /root/icar_ros2_ws/software/library_ws/install/setup.bash
    source /root/icar_ros2_ws/icar_ws/install/setup.bash
    cd '$CONTAINER_PROJECT'
    source install/setup.bash
    exec ros2 launch car_bringup node_manager.launch.py
  "

echo "Started $CONTAINER_NAME. APP Bridge: 192.168.43.22:8765"
