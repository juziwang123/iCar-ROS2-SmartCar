import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


class MotionController(Node):
    def __init__(self) -> None:
        super().__init__('motion_controller')
        self.declare_parameter('input_topic', '/control/cmd_vel')
        self.declare_parameter('output_topic', '/cmd_vel')
        self.declare_parameter('max_linear_speed', 0.4)
        self.declare_parameter('max_angular_speed', 1.2)

        self.max_linear_speed = float(self.get_parameter('max_linear_speed').value)
        self.max_angular_speed = float(self.get_parameter('max_angular_speed').value)
        self.publisher = self.create_publisher(Twist, str(self.get_parameter('output_topic').value), 10)
        self.create_subscription(Twist, str(self.get_parameter('input_topic').value), self._on_twist, 10)
        self.get_logger().info('Motion controller started')

    def _on_twist(self, msg: Twist) -> None:
        output = Twist()
        output.linear.x = self._clamp(msg.linear.x, self.max_linear_speed)
        output.linear.y = self._clamp(msg.linear.y, self.max_linear_speed)
        output.linear.z = self._clamp(msg.linear.z, self.max_linear_speed)
        output.angular.x = self._clamp(msg.angular.x, self.max_angular_speed)
        output.angular.y = self._clamp(msg.angular.y, self.max_angular_speed)
        output.angular.z = self._clamp(msg.angular.z, self.max_angular_speed)
        self.publisher.publish(output)

    @staticmethod
    def _clamp(value: float, limit: float) -> float:
        return max(-limit, min(limit, value))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MotionController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()