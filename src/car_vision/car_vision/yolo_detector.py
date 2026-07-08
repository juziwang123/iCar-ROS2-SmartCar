"""YOLOv8 目标检测节点。

订阅小车相机图像，运行 YOLOv8 推理，发布检测结果和控制指令。
"""

import json
from typing import List

import rclpy
from cv_bridge import CvBridge
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String


class YoloDetector(Node):
    def __init__(self) -> None:
        super().__init__("yolo_detector")

        self.declare_parameter("image_topic", "/camera/color/image_raw")
        self.declare_parameter("detections_topic", "/detections")
        self.declare_parameter("cmd_topic", "/cmd_vel_vision")
        self.declare_parameter("model", "yolov8n.pt")
        self.declare_parameter("confidence", 0.5)
        self.declare_parameter("device", "cpu")
        self.declare_parameter("publish_control", True)
        self.declare_parameter("stop_classes", [0, 11])  # person, stop sign
        self.declare_parameter("stop_distance", 200)  # pixels, approx distance

        self.confidence = float(self.get_parameter("confidence").value)
        self.stop_classes = self.get_parameter("stop_classes").get_parameter_value().integer_array_value
        self.stop_distance = int(self.get_parameter("stop_distance").value)
        self.publish_control = bool(self.get_parameter("publish_control").value)

        # ROS 接口
        self.bridge = CvBridge()
        self.det_pub = self.create_publisher(
            String, str(self.get_parameter("detections_topic").value), 10
        )
        self.cmd_pub = self.create_publisher(
            Twist, str(self.get_parameter("cmd_topic").value), 10
        )
        self.create_subscription(
            Image,
            str(self.get_parameter("image_topic").value),
            self._on_image,
            10,
        )

        # 加载 YOLO 模型
        from ultralytics import YOLO

        model_name = str(self.get_parameter("model").value)
        device = str(self.get_parameter("device").value)
        self.get_logger().info(f"Loading YOLO model: {model_name} on {device}")
        self.model = YOLO(model_name)
        self.model.to(device)
        self.get_logger().info("YOLO detector ready")

    def _on_image(self, msg: Image) -> None:
        """接收相机图像，运行 YOLO 推理。"""
        try:
            frame = self.bridge.img_to_cv2(msg, desired_encoding="bgr8")
        except Exception:
            return

        results = self.model(frame, verbose=False, conf=self.confidence)

        detections = []
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                xyxy = box.xyxy[0].tolist()
                detections.append(
                    {
                        "class": int(cls_id),
                        "name": self.model.names.get(cls_id, str(cls_id)),
                        "confidence": round(conf, 3),
                        "bbox": [round(v, 1) for v in xyxy],
                    }
                )

        # 发布检测结果 JSON
        if detections:
            self.det_pub.publish(String(data=json.dumps(detections)))

        # 根据检测结果决策
        if self.publish_control:
            twist = self._decide_action(detections, msg.width)
            self.cmd_pub.publish(twist)

    def _decide_action(self, detections: List[dict], image_width: int) -> Twist:
        """根据检测结果计算控制指令。"""
        twist = Twist()
        should_stop = False

        for det in detections:
            if int(det["class"]) in self.stop_classes:
                x1, _, x2, _ = det["bbox"]
                center_x = (x1 + x2) / 2.0
                # 目标在画面中间且足够大（近），停车
                if abs(center_x - image_width / 2.0) < image_width * 0.3:
                    width = x2 - x1
                    if width > self.stop_distance:
                        should_stop = True
                        self.get_logger().info(
                            f"Stop: {det['name']} (confidence: {det['confidence']})"
                        )
                        break

        if should_stop:
            twist.linear.x = 0.0
            twist.angular.z = 0.0
        # 没有需要停车的目标时，不发控制指令（零值表示不介入）

        return twist


def main(args=None) -> None:
    rclpy.init(args=args)
    node = YoloDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
