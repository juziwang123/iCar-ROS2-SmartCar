import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from geometry_msgs.msg import Twist
from std_msgs.msg import Float32
import cv2
import numpy as np
from cv_bridge import CvBridge


class LineFollower(Node):

    def __init__(self):
        super().__init__('line_follower')
        
        self.declare_parameter('image_topic', '/camera/color/image_raw')
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('image_width', 640)
        self.declare_parameter('image_height', 480)
        self.declare_parameter('kp_angular', 0.008)
        self.declare_parameter('kp_linear', 0.002)
        self.declare_parameter('max_linear_speed', 0.2)
        self.declare_parameter('max_angular_speed', 0.8)
        self.declare_parameter('roi_height_ratio', 0.3)
        self.declare_parameter('line_color', 'black')
        
        self.image_topic = self.get_parameter('image_topic').get_parameter_value().string_value
        self.cmd_vel_topic = self.get_parameter('cmd_vel_topic').get_parameter_value().string_value
        self.image_width = self.get_parameter('image_width').get_parameter_value().integer_value
        self.image_height = self.get_parameter('image_height').get_parameter_value().integer_value
        self.kp_angular = self.get_parameter('kp_angular').get_parameter_value().double_value
        self.kp_linear = self.get_parameter('kp_linear').get_parameter_value().double_value
        self.max_linear_speed = self.get_parameter('max_linear_speed').get_parameter_value().double_value
        self.max_angular_speed = self.get_parameter('max_angular_speed').get_parameter_value().double_value
        self.roi_height_ratio = self.get_parameter('roi_height_ratio').get_parameter_value().double_value
        self.line_color = self.get_parameter('line_color').get_parameter_value().string_value
        
        self.bridge = CvBridge()
        self.cmd_vel_pub = self.create_publisher(Twist, self.cmd_vel_topic, 10)
        self.offset_pub = self.create_publisher(Float32, '/line_offset', 10)
        self.image_sub = self.create_subscription(
            Image, self.image_topic, self.image_callback, 10)
        
        self.image_center_x = self.image_width / 2
        
        self.get_logger().info(f'LineFollower initialized, tracking {self.line_color} lines')

    def image_callback(self, msg):
        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
        except Exception as e:
            self.get_logger().error(f'Failed to convert image: {e}')
            return
        
        roi_height = int(self.image_height * self.roi_height_ratio)
        roi = cv_image[-roi_height:, :]
        
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        
        if self.line_color == 'black':
            _, binary = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
        else:
            _, binary = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY)
        
        kernel = np.ones((3, 3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours:
            largest_contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest_contour)
            
            if area > 50:
                M = cv2.moments(largest_contour)
                if M['m00'] != 0:
                    cx = int(M['m10'] / M['m00'])
                    cy = int(M['m01'] / M['m00'])
                    
                    error_x = cx - self.image_center_x
                    
                    angular_speed = self.kp_angular * error_x
                    angular_speed = max(-self.max_angular_speed, min(self.max_angular_speed, angular_speed))
                    
                    linear_speed = self.max_linear_speed - abs(angular_speed) * self.kp_linear
                    linear_speed = max(0.05, linear_speed)
                    
                    twist = Twist()
                    twist.linear.x = linear_speed
                    twist.angular.z = -angular_speed
                    
                    self.cmd_vel_pub.publish(twist)
                    
                    offset_msg = Float32()
                    offset_msg.data = float(error_x)
                    self.offset_pub.publish(offset_msg)
                    
                    self.get_logger().debug(f'Line at ({cx}, {cy}), error={error_x:.1f}, speed={linear_speed:.2f}, angular={angular_speed:.2f}')
                    return
        
        twist = Twist()
        twist.linear.x = 0.0
        twist.angular.z = 0.0
        self.cmd_vel_pub.publish(twist)
        
        self.get_logger().warn('Line lost, stopping')


def main(args=None):
    rclpy.init(args=args)
    node = LineFollower()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
