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
    {"label": "person", "class_id": 0, "confidence": 0.93,
     "x_min": 100.0, "y_min": 40.0, "x_max": 280.0, "y_max": 420.0,
     "center_x": 190.0, "center_y": 230.0, "width": 180.0, "height": 380.0}
  ]
}
```

模型不存在、`ultralytics` 未安装或推理失败时，同一 topic 会发布空 `detections` 和 `error` 字段，APP 可据此显示诊断信息。
