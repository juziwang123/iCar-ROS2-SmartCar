# AI 边缘推理（YOLO 目标检测）设计文档

## 1. 设计目标

在小车 Orin Nano 上部署 YOLOv8 实时目标检测，识别图像中的人、车、障碍物等，检测结果直接反馈到控制链，实现"看到什么做什么"的智能行为。

## 2. 技术选型

| 项目 | 选择 | 理由 |
|------|------|------|
| 检测模型 | YOLOv8n（nano） | 模型仅 6MB，CPU 可跑 30+ FPS，Orin Nano 上用 TensorRT 可达 100+ FPS |
| 推理框架 | ultralytics | `pip install ultralytics` 一行安装，Python API 极简 |
| 图像来源 | `/camera/color/image_raw` | 小车深度相机的 RGB 流 |
| 输出 | `/detections` (自定义) + `/cmd_vel_vision` (Twist) | 检测结果 + 控制指令，都走 ROS2 话题 |

## 3. 系统架构

```
┌─────────────┐     /image_raw     ┌──────────────────┐    /detections     ┌──────────┐
│ Astra 相机   │ ─────────────────►│  yolo_detector    │────────────────►│ 可视化/日志 │
│ (小车自带)   │                    │                   │                  └──────────┘
└─────────────┘                    │  YOLOv8 推理      │
                                   │  ┌─────────────┐  │
                                   │  │ 检测人/车/   │  │   /cmd_vel_vision
                                   │  │ 障碍物/标志  │──┼────────────────► safety_mux
                                   │  └─────────────┘  │
                                   └──────────────────┘
```

## 4. 检测目标类别（YOLOv8 COCO 80 类中选取）

| 类别 | 作用 |
|------|------|
| person (0) | 检测行人 → 减速/停车 |
| car (2) | 检测车辆 → 避让 |
| stop sign (11) | 检测停车标志 → 自动停车 |
| traffic light (9) | 检测红绿灯 → 信号响应 |
| chair (56) / couch (57) | 检测障碍物类型 |
| fire hydrant (10) | 模拟消防巡检任务 |

## 5. 控制逻辑

| 检测结果 | 小车行为 |
|---------|---------|
| 前方有 person，距离 < 1m | 减速到 0.05 m/s，停下来 |
| 前方有 stop sign | 完全停车 3 秒后继续 |
| 视野内无目标 | 不发布控制指令，让导航/手动接管 |
| 检测到指定目标（如 fire hydrant） | 记录位置坐标，发出提示 |

## 6. 节点代码结构 (yolo_detector.py)

```python
class YoloDetector(Node):
    def __init__(self):
        self.model = YOLO("yolov8n.pt")          # 加载 nano 模型
        self.sub = self.create_subscription(
            Image, "/camera/color/image_raw",     # 订阅相机话题
            self.on_image, 10
        )
        self.det_pub = self.create_publisher(     # 发布检测结果
            DetectionArray, "/detections", 10
        )
        self.cmd_pub = self.create_publisher(     # 发布控制指令
            Twist, "/cmd_vel_vision", 10
        )

    def on_image(self, msg: Image):
        # 1. ROS Image → numpy array
        frame = self._ros_to_cv(msg)
        # 2. YOLO 推理
        results = self.model(frame, verbose=False)
        # 3. 分析检测结果 → 控制决策
        twist = self._decide_action(results)
        # 4. 发布
        self.cmd_pub.publish(twist)
```

## 7. 部署步骤

```bash
# 1. 进入小车 Docker
d

# 2. 安装 YOLO
pip3 install ultralytics

# 3. 拷贝我们的节点
# （从开发机 scp 或 git clone）

# 4. 启动
ros2 run car_vision yolo_detector --ros-args -p model:=yolov8n.pt
```

## 8. Jetson GPU 加速（进阶）

如果 Docker 能访问 GPU，安装 TensorRT 加速版：

```bash
pip3 install ultralytics
# YOLOv8 会自动检测 TensorRT 并使用
```

CPU 推理：YOLOv8n 约 30 FPS → 够用  
GPU 推理：TensorRT 优化后 100+ FPS → 实时无压力

## 9. 接入控制链

检测节点的 `/cmd_vel_vision` 直接对接 `safety_mux` 的 `vision_topic`：

```
yolo_detector ──→ /cmd_vel_vision ──→ safety_mux ──→ 底盘
                                   ──→（vision 模式下优先）
```

模式切换到 `vision` 时，YOLO 的决策成为小车的主要控制信号。
