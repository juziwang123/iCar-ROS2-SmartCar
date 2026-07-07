FROM ros:foxy-ros-base

RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-yaml \
    ros-foxy-nav2-bringup \
    ros-foxy-slam-toolbox \
    ros-foxy-teleop-twist-keyboard \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir PyYAML

WORKDIR /ros2_ws

COPY src/car_control /ros2_ws/src/car_control
COPY src/car_bringup /ros2_ws/src/car_bringup
COPY src/car_lidar   /ros2_ws/src/car_lidar
COPY src/car_navigation /ros2_ws/src/car_navigation

RUN /bin/bash -c "source /opt/ros/foxy/setup.bash && colcon build --packages-select car_control car_bringup car_lidar car_navigation"

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
