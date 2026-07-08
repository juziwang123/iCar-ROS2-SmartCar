import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String, Float32
import cv2
import numpy as np
from cv_bridge import CvBridge


class DefectDetector(Node):

    def __init__(self):
        super().__init__('defect_detector')
        
        self.declare_parameter('image_topic', '/camera/color/image_raw')
        self.declare_parameter('min_defect_area', 100)
        self.declare_parameter('canny_threshold1', 50)
        self.declare_parameter('canny_threshold2', 150)
        self.declare_parameter('gaussian_kernel_size', 5)
        
        self.image_topic = self.get_parameter('image_topic').get_parameter_value().string_value
        self.min_defect_area = self.get_parameter('min_defect_area').get_parameter_value().integer_value
        self.canny_threshold1 = self.get_parameter('canny_threshold1').get_parameter_value().integer_value
        self.canny_threshold2 = self.get_parameter('canny_threshold2').get_parameter_value().integer_value
        self.gaussian_kernel_size = self.get_parameter('gaussian_kernel_size').get_parameter_value().integer_value
        
        self.bridge = CvBridge()
        self.defect_pub = self.create_publisher(String, '/defect_detection', 10)
        self.defect_count_pub = self.create_publisher(Float32, '/defect_count', 10)
        self.image_sub = self.create_subscription(
            Image, self.image_topic, self.image_callback, 10)
        
        self.get_logger().info('DefectDetector initialized')

    def image_callback(self, msg):
        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
        except Exception as e:
            self.get_logger().error(f'Failed to convert image: {e}')
            return
        
        gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
        
        blurred = cv2.GaussianBlur(gray, (self.gaussian_kernel_size, self.gaussian_kernel_size), 0)
        
        edges = cv2.Canny(blurred, self.canny_threshold1, self.canny_threshold2)
        
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=2)
        
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        defects = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= self.min_defect_area:
                M = cv2.moments(contour)
                if M['m00'] != 0:
                    cx = int(M['m10'] / M['m00'])
                    cy = int(M['m01'] / M['m00'])
                    
                    defects.append({
                        'x': cx,
                        'y': cy,
                        'area': area
                    })
        
        defect_count = len(defects)
        
        if defects:
            defect_info = []
            for i, defect in enumerate(defects):
                defect_info.append(f'defect{i}=(x={defect["x"]},y={defect["y"]},area={defect["area"]})')
            
            defect_msg = String()
            defect_msg.data = f'defects={defect_count},' + ','.join(defect_info)
            self.defect_pub.publish(defect_msg)
            
            count_msg = Float32()
            count_msg.data = float(defect_count)
            self.defect_count_pub.publish(count_msg)
            
            self.get_logger().debug(f'Detected {defect_count} defects')
        else:
            defect_msg = String()
            defect_msg.data = 'no_defects'
            self.defect_pub.publish(defect_msg)


def main(args=None):
    rclpy.init(args=args)
    node = DefectDetector()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
