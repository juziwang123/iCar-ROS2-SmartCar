# YOLO 本地模型部署

`car_vision` 的 YOLO 节点使用 Ultralytics YOLO，并且只加载本地模型文件，不会在运行时联网下载权重。

## 准备模型和运行时

1. 在 Jetson 上先准备与 JetPack/CUDA 匹配的 PyTorch。
2. 安装 YOLO Python 依赖：`python3 -m pip install -r src/car_vision/requirements-vision.txt`。
3. 将训练或下载的权重保存为 `src/car_vision/models/model.pt`。该目录已被 Git 忽略，模型不会被提交。
4. 重新构建并加载环境：`colcon build --packages-select car_vision && source install/setup.bash`。

若模型不在默认位置，传入绝对路径即可。推荐使用 `.pt` 权重；可使用与当前安装的 Ultralytics 兼容的本地导出格式。

## 启动

单独启动：

```bash
ros2 launch car_vision vision.launch.py \
  use_color_detector:=false use_yolo:=true \
  yolo_model_path:=/home/jetson/models/icar_best.pt \
  yolo_device:=0
```

通过总启动入口：

```bash
ros2 launch car_bringup bringup.launch.py \
  use_vision:=true use_color_detector:=false use_yolo:=true \
  vision_yolo_model_path:=/home/jetson/models/icar_best.pt \
  vision_yolo_device:=0
```

`yolo_device:=auto` 自动选择运行设备；CUDA 第一个设备可设为 `0`，CPU 可设为 `cpu`。颜色检测与 YOLO 默认都发布 `/vision/detections`，因此启用 YOLO 时应关闭 `use_color_detector`，避免两个节点交替发布不同语义的结果。

## 输出

节点在 `/vision/detections` 发布 JSON 字符串，格式与 APP 桥接兼容：

```json
{
  "detected": true,
  "model": "icar_best.pt",
  "image": {"width": 640, "height": 480},
  "detections": [
    {"label": "person", "class_id": 0, "track_id": 7, "confidence": 0.93,
     "x_min": 100.0, "y_min": 40.0, "x_max": 280.0, "y_max": 420.0,
     "center_x": 190.0, "center_y": 230.0, "width": 180.0, "height": 380.0}
  ]
}
```

模型不存在、`ultralytics` 未安装或推理失败时，同一 topic 会发布空 `detections` 和 `error` 字段，APP 可据此显示诊断信息。

## 人员安全与跟随

YOLO 节点会在人员检测框的中心区域读取 `/camera/depth/image_raw` 的中位深度。深度图必须已与彩色图对齐；没有新鲜且尺寸一致的深度图时，系统不会依据 YOLO 自动限速、急停或向目标前进。

- 人员距离小于等于 `person_slow_distance_m`（默认 1.2 m）时，`safety_mux` 将所有模式的前进速度限制在 `person_slow_max_linear_speed`（默认 0.10 m/s）。
- 人员距离连续两帧小于等于 `person_estop_distance_m`（默认 0.55 m）时，`safety_mux` 输出零速度。该视觉急停独立于人工 `/emergency_stop`，不会错误释放人工急停。
- APP 订阅 `vision` 后显示每个 `person` 的 `track_id`，发送 `{"cmd":"follow_person","track_id":7}` 即可选择人员并进入 `follow` 模式；`{"cmd":"stop_follow"}` 立即取消选择并回到手动模式。

跟随控制发布到 `/cmd_vel_follow`，仍由 `safety_mux` 仲裁。运行 YOLO 人员跟随时不要同时启用激光雷达 `tracker`，因为两者会使用同一跟随控制话题。
