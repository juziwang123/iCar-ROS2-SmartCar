import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String
import cv2
import numpy as np
from cv_bridge import CvBridge

COLOR_RANGES = {
    'red': ([0, 100, 100], [10, 255, 255]),
    'green': ([40, 40, 40], [70, 255, 255]),
    'blue': ([100, 40, 40], [140, 255, 255]),
    'yellow': ([20, 100, 100], [30, 255, 255]),
    'orange': ([10, 100, 100], [20, 255, 255]),
    'purple': ([130, 40, 40], [160, 255, 255]),
}


class ColorDetector(Node):

    def __init__(self):
        super().__init__('color_detector')
        
        self.declare_parameter('target_color', 'red')
        self.declare_parameter('image_topic', '/camera/color/image_raw')
        self.declare_parameter('min_area', 100)
        
        self.target_color = self.get_parameter('target_color').get_parameter_value().string_value
        self.image_topic = self.get_parameter('image_topic').get_parameter_value().string_value
        self.min_area = self.get_parameter('min_area').get_parameter_value().integer_value
        
        self.bridge = CvBridge()
        self.detection_pub = self.create_publisher(PoseStamped, '/target_pose', 10)
        self.result_pub = self.create_publisher(String, '/color_detection_result', 10)
        self.image_sub = self.create_subscription(
            Image, self.image_topic, self.image_callback, 10)
        
        self.get_logger().info(f'ColorDetector initialized, target color: {self.target_color}')

    def image_callback(self, msg):
        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
        except Exception as e:
            self.get_logger().error(f'Failed to convert image: {e}')
            return

        hsv = cv2.cvtColor(cv_image, cv2.COLOR_BGR2HSV)
        
        if self.target_color not in COLOR_RANGES:
            self.get_logger().error(f'Unknown color: {self.target_color}')
            return
        
        lower, upper = COLOR_RANGES[self.target_color]
        mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
        
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours:
            largest_contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest_contour)
            
            if area >= self.min_area:
                M = cv2.moments(largest_contour)
                if M['m00'] != 0:
                    cx = int(M['m10'] / M['m00'])
                    cy = int(M['m01'] / M['m00'])
                    
                    pose = PoseStamped()
                    pose.header = msg.header
                    pose.pose.position.x = float(cx)
                    pose.pose.position.y = float(cy)
                    pose.pose.position.z = float(area)
                    self.detection_pub.publish(pose)
                    
                    result_msg = String()
                    result_msg.data = f'color={self.target_color},x={cx},y={cy},area={area}'
                    self.result_pub.publish(result_msg)
                    
                    self.get_logger().debug(f'Detected {self.target_color} at ({cx}, {cy}), area: {area}')
        else:
            result_msg = String()
            result_msg.data = 'no_target'
            self.result_pub.publish(result_msg)


def main(args=None):
    rclpy.init(args=args)
    node = ColorDetector()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
