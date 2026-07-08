import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray, Detection2D, BoundingBox2D
from std_msgs.msg import String
import cv2
import numpy as np
from cv_bridge import CvBridge
import os


class YoloDetector(Node):

    def __init__(self):
        super().__init__('yolo_detector')
        
        self.declare_parameter('image_topic', '/camera/color/image_raw')
        self.declare_parameter('model_path', 'models/yolov8n.pt')
        self.declare_parameter('model_name', 'yolov8n')
        self.declare_parameter('confidence_threshold', 0.5)
        self.declare_parameter('iou_threshold', 0.45)
        self.declare_parameter('device', 'cpu')
        self.declare_parameter('image_size', 640)
        
        self.image_topic = self.get_parameter('image_topic').get_parameter_value().string_value
        self.model_path = self.get_parameter('model_path').get_parameter_value().string_value
        self.model_name = self.get_parameter('model_name').get_parameter_value().string_value
        self.confidence_threshold = self.get_parameter('confidence_threshold').get_parameter_value().double_value
        self.iou_threshold = self.get_parameter('iou_threshold').get_parameter_value().double_value
        self.device = self.get_parameter('device').get_parameter_value().string_value
        self.image_size = self.get_parameter('image_size').get_parameter_value().integer_value
        
        self.bridge = CvBridge()
        self.detection_pub = self.create_publisher(Detection2DArray, '/detected_objects', 10)
        self.detection_info_pub = self.create_publisher(String, '/detection_info', 10)
        self.image_sub = self.create_subscription(
            Image, self.image_topic, self.image_callback, 10)
        
        self.model = None
        self.class_names = []
        self._load_model()
        
        self.get_logger().info(f'YoloDetector initialized with model: {self.model_name}')

    def _load_model(self):
        try:
            from ultralytics import YOLO
            
            full_model_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'models',
                os.path.basename(self.model_path)
            )
            
            if os.path.exists(full_model_path):
                self.model_path = full_model_path
                self.get_logger().info(f'Loading local model: {self.model_path}')
                self.model = YOLO(self.model_path)
            elif os.path.exists(self.model_path):
                self.get_logger().info(f'Loading model from path: {self.model_path}')
                self.model = YOLO(self.model_path)
            else:
                self.get_logger().info(f'Loading pretrained model: {self.model_name}')
                self.model = YOLO(self.model_name)
            
            self.model.to(self.device)
            self.model.conf = self.confidence_threshold
            self.model.iou = self.iou_threshold
            
            self.class_names = self.model.names
            self.get_logger().info(f'Model loaded successfully, classes: {list(self.class_names.values())}')
            
        except ImportError:
            self.get_logger().error('ultralytics library not installed, trying torch.hub')
            self._load_model_torch_hub()
        except Exception as e:
            self.get_logger().error(f'Failed to load YOLO model: {e}')
            self.get_logger().info('Falling back to OpenCV DNN mode')
            self._load_opencv_dnn_model()

    def _load_model_torch_hub(self):
        try:
            import torch
            
            full_model_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'models',
                os.path.basename(self.model_path)
            )
            
            if os.path.exists(full_model_path):
                self.model_path = full_model_path
            elif not os.path.exists(self.model_path):
                self.get_logger().warning(f'Model not found: {self.model_path}, using yolov5s')
                self.model_path = 'yolov5s'
            
            self.model = torch.hub.load('ultralytics/yolov5', 'custom', path=self.model_path, verbose=False)
            
            if self.device == 'cuda' and torch.cuda.is_available():
                self.model = self.model.cuda()
            else:
                self.model = self.model.cpu()
            
            self.model.conf = self.confidence_threshold
            self.model.iou = self.iou_threshold
            
            self.class_names = self.model.names
            self.get_logger().info(f'Torch hub model loaded successfully, classes: {self.class_names}')
            
        except Exception as e:
            self.get_logger().error(f'Failed to load torch hub model: {e}')
            self._load_opencv_dnn_model()

    def _load_opencv_dnn_model(self):
        try:
            onnx_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'models',
                'yolov8n.onnx'
            )
            
            if os.path.exists(onnx_path):
                self.model = cv2.dnn.readNetFromONNX(onnx_path)
            else:
                self.get_logger().error('ONNX model not found')
                self.model = None
                return
            
            self.class_names = [
                'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train',
                'truck', 'boat', 'traffic light', 'fire hydrant', 'stop sign',
                'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep',
                'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella',
                'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard',
                'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard',
                'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup', 'fork',
                'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange',
                'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair',
                'couch', 'potted plant', 'bed', 'dining table', 'toilet', 'tv',
                'laptop', 'mouse', 'remote', 'keyboard', 'cell phone', 'microwave',
                'oven', 'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase',
                'scissors', 'teddy bear', 'hair drier', 'toothbrush'
            ]
            self.get_logger().info('OpenCV DNN model loaded')
        except Exception as e:
            self.get_logger().error(f'Failed to load OpenCV DNN model: {e}')
            self.model = None

    def image_callback(self, msg):
        if self.model is None:
            return
        
        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
        except Exception as e:
            self.get_logger().error(f'Failed to convert image: {e}')
            return
        
        results = self._inference(cv_image)
        
        detection_array = Detection2DArray()
        detection_array.header = msg.header
        
        detection_info = []
        
        for result in results:
            detection = Detection2D()
            detection.header = msg.header
            
            bbox = BoundingBox2D()
            bbox.center.x = result['x_center']
            bbox.center.y = result['y_center']
            bbox.size_x = result['width']
            bbox.size_y = result['height']
            detection.bbox = bbox
            
            detection_array.detections.append(detection)
            
            detection_info.append(
                f"{result['class_name']}({result['confidence']:.2f})"
            )
        
        self.detection_pub.publish(detection_array)
        
        info_msg = String()
        info_msg.data = ','.join(detection_info) if detection_info else 'no_detections'
        self.detection_info_pub.publish(info_msg)
        
        self.get_logger().debug(f'Detected {len(results)} objects: {", ".join(detection_info)}')

    def _inference(self, image):
        results = []
        
        if hasattr(self.model, 'names') and hasattr(self.model, 'predict'):
            try:
                outputs = self.model.predict(
                    image,
                    imgsz=self.image_size,
                    conf=self.confidence_threshold,
                    iou=self.iou_threshold,
                    device=self.device,
                    verbose=False
                )
                
                for output in outputs:
                    for box in output.boxes:
                        x_min, y_min, x_max, y_max = box.xyxy[0].tolist()
                        conf = box.conf[0].item()
                        class_id = int(box.cls[0].item())
                        class_name = self.class_names[class_id]
                        
                        x_center = (x_min + x_max) / 2
                        y_center = (y_min + y_max) / 2
                        width = x_max - x_min
                        height = y_max - y_min
                        
                        results.append({
                            'x_center': x_center,
                            'y_center': y_center,
                            'width': width,
                            'height': height,
                            'confidence': conf,
                            'class_id': class_id,
                            'class_name': class_name
                        })
            except Exception as e:
                self.get_logger().error(f'YOLO inference failed: {e}')
        elif hasattr(self.model, 'names'):
            try:
                outputs = self.model(image)
                df = outputs.pandas().xyxy[0]
                
                for _, row in df.iterrows():
                    x_min = row['xmin']
                    y_min = row['ymin']
                    x_max = row['xmax']
                    y_max = row['ymax']
                    conf = row['confidence']
                    class_id = int(row['class'])
                    class_name = self.class_names[class_id]
                    
                    x_center = (x_min + x_max) / 2
                    y_center = (y_min + y_max) / 2
                    width = x_max - x_min
                    height = y_max - y_min
                    
                    results.append({
                        'x_center': x_center,
                        'y_center': y_center,
                        'width': width,
                        'height': height,
                        'confidence': conf,
                        'class_id': class_id,
                        'class_name': class_name
                    })
            except Exception as e:
                self.get_logger().error(f'YOLO inference failed: {e}')
        else:
            try:
                blob = cv2.dnn.blobFromImage(
                    image, 1/255.0, (self.image_size, self.image_size), swapRB=True, crop=False)
                self.model.setInput(blob)
                outputs = self.model.forward()
                
                height, width = image.shape[:2]
                
                for output in outputs:
                    for detection in output:
                        scores = detection[5:]
                        class_id = np.argmax(scores)
                        confidence = scores[class_id]
                        
                        if confidence > self.confidence_threshold:
                            center_x = int(detection[0] * width)
                            center_y = int(detection[1] * height)
                            w = int(detection[2] * width)
                            h = int(detection[3] * height)
                            
                            results.append({
                                'x_center': center_x,
                                'y_center': center_y,
                                'width': w,
                                'height': h,
                                'confidence': confidence,
                                'class_id': class_id,
                                'class_name': self.class_names[class_id]
                            })
            except Exception as e:
                self.get_logger().error(f'OpenCV DNN inference failed: {e}')
        
        return results


def main(args=None):
    rclpy.init(args=args)
    node = YoloDetector()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
