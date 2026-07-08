import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped, Twist
from std_msgs.msg import String
import math


class ColorTracker(Node):

    def __init__(self):
        super().__init__('color_tracker')
        
        self.declare_parameter('target_pose_topic', '/target_pose')
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('image_width', 640)
        self.declare_parameter('image_height', 480)
        self.declare_parameter('kp_angular', 0.005)
        self.declare_parameter('kp_linear', 0.001)
        self.declare_parameter('max_linear_speed', 0.3)
        self.declare_parameter('max_angular_speed', 0.5)
        self.declare_parameter('target_area_min', 5000)
        self.declare_parameter('target_area_max', 20000)
        
        self.target_pose_topic = self.get_parameter('target_pose_topic').get_parameter_value().string_value
        self.cmd_vel_topic = self.get_parameter('cmd_vel_topic').get_parameter_value().string_value
        self.image_width = self.get_parameter('image_width').get_parameter_value().integer_value
        self.image_height = self.get_parameter('image_height').get_parameter_value().integer_value
        self.kp_angular = self.get_parameter('kp_angular').get_parameter_value().double_value
        self.kp_linear = self.get_parameter('kp_linear').get_parameter_value().double_value
        self.max_linear_speed = self.get_parameter('max_linear_speed').get_parameter_value().double_value
        self.max_angular_speed = self.get_parameter('max_angular_speed').get_parameter_value().double_value
        self.target_area_min = self.get_parameter('target_area_min').get_parameter_value().integer_value
        self.target_area_max = self.get_parameter('target_area_max').get_parameter_value().integer_value
        
        self.image_center_x = self.image_width / 2
        self.image_center_y = self.image_height / 2
        
        self.cmd_vel_pub = self.create_publisher(Twist, self.cmd_vel_topic, 10)
        self.target_pose_sub = self.create_subscription(
            PoseStamped, self.target_pose_topic, self.target_pose_callback, 10)
        self.detection_result_sub = self.create_subscription(
            String, '/color_detection_result', self.detection_result_callback, 10)
        
        self.target_found = False
        
        self.get_logger().info('ColorTracker initialized')

    def target_pose_callback(self, msg):
        target_x = msg.pose.position.x
        target_y = msg.pose.position.y
        target_area = msg.pose.position.z
        
        error_x = target_x - self.image_center_x
        
        angular_speed = self.kp_angular * error_x
        angular_speed = max(-self.max_angular_speed, min(self.max_angular_speed, angular_speed))
        
        area_error = target_area - (self.target_area_min + self.target_area_max) / 2
        linear_speed = self.kp_linear * area_error
        linear_speed = max(-self.max_linear_speed, min(self.max_linear_speed, linear_speed))
        
        if target_area < self.target_area_min:
            linear_speed = min(linear_speed, self.max_linear_speed)
            linear_speed = max(0.1, linear_speed)
        elif target_area > self.target_area_max:
            linear_speed = max(linear_speed, -self.max_linear_speed)
            linear_speed = min(-0.1, linear_speed)
        
        twist = Twist()
        twist.linear.x = linear_speed
        twist.angular.z = -angular_speed
        
        self.cmd_vel_pub.publish(twist)
        
        self.get_logger().debug(f'Tracking: error_x={error_x:.1f}, linear={linear_speed:.2f}, angular={angular_speed:.2f}')

    def detection_result_callback(self, msg):
        if msg.data == 'no_target':
            if self.target_found:
                self.get_logger().info('Target lost, stopping')
                twist = Twist()
                twist.linear.x = 0.0
                twist.angular.z = 0.0
                self.cmd_vel_pub.publish(twist)
                self.target_found = False
        else:
            self.target_found = True


def main(args=None):
    rclpy.init(args=args)
    node = ColorTracker()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
