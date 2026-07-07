import select
import sys
import termios
import tty

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Bool
from std_msgs.msg import String


class KeyboardTeleop(Node):
    def __init__(self) -> None:
        super().__init__('keyboard_teleop')
        self.declare_parameter('linear_speed', 0.25)
        self.declare_parameter('angular_speed', 0.8)
        self.declare_parameter('publish_topic', '/cmd_vel_manual')
        self.declare_parameter('mode_topic', '/mode_select')
        self.declare_parameter('estop_topic', '/emergency_stop')

        publish_topic = self.get_parameter('publish_topic').value
        mode_topic = self.get_parameter('mode_topic').value
        estop_topic = self.get_parameter('estop_topic').value

        self.linear_speed = float(self.get_parameter('linear_speed').value)
        self.angular_speed = float(self.get_parameter('angular_speed').value)
        self.publisher = self.create_publisher(Twist, publish_topic, 10)
        self.mode_publisher = self.create_publisher(String, mode_topic, 10)
        self.estop_publisher = self.create_publisher(Bool, estop_topic, 10)
        self.timer = self.create_timer(0.05, self._poll_keyboard)

        self._settings = termios.tcgetattr(sys.stdin)
        self.get_logger().info(
            '键盘遥控已启动：w/s 前进后退，a/d 左右转，q/e 弧线，x 停止，空格急停，r 解除急停，m 手动模式。'
        )

    def destroy_node(self) -> bool:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._settings)
        return super().destroy_node()

    def _poll_keyboard(self) -> None:
        key = self._read_key()
        if key is None:
            return

        if key == 'm':
            self._publish_mode('manual')
            return
        if key == 'n':
            self._publish_mode('nav')
            return
        if key == 'v':
            self._publish_mode('vision')
            return
        if key == 'f':
            self._publish_mode('follow')
            return
        if key == ' ':
            self.estop_publisher.publish(Bool(data=True))
            self._publish_twist(0.0, 0.0)
            return
        if key == 'r':
            self.estop_publisher.publish(Bool(data=False))
            return

        linear = 0.0
        angular = 0.0
        if key == 'w':
            linear = self.linear_speed
        elif key == 's':
            linear = -self.linear_speed
        elif key == 'a':
            angular = self.angular_speed
        elif key == 'd':
            angular = -self.angular_speed
        elif key == 'q':
            linear = self.linear_speed
            angular = self.angular_speed
        elif key == 'e':
            linear = self.linear_speed
            angular = -self.angular_speed
        elif key == 'x':
            linear = 0.0
            angular = 0.0
        else:
            return

        self._publish_twist(linear, angular)

    def _publish_mode(self, mode: str) -> None:
        self.mode_publisher.publish(String(data=mode))
        self.get_logger().info(f'已切换模式：{mode}')

    def _publish_twist(self, linear: float, angular: float) -> None:
        msg = Twist()
        msg.linear.x = linear
        msg.angular.z = angular
        self.publisher.publish(msg)

    def _read_key(self) -> str | None:
        tty.setraw(sys.stdin.fileno())
        ready, _, _ = select.select([sys.stdin], [], [], 0.0)
        key = sys.stdin.read(1) if ready else None
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._settings)
        return key


def main(args=None) -> None:
    rclpy.init(args=args)
    if not sys.stdin.isatty():
        print('keyboard_teleop 需要在交互式终端中运行。', file=sys.stderr)
        rclpy.shutdown()
        return
    node = KeyboardTeleop()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
