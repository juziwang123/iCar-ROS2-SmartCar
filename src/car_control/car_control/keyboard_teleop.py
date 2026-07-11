import select
import sys
import termios
import tty
from typing import Optional

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Bool
from std_msgs.msg import String


HELP_TEXT = """
iCar keyboard teleop
--------------------
w / s  : forward / backward
a / d  : turn left / turn right
q / e  : forward arc left / forward arc right
x      : stop
space  : emergency stop
r      : release emergency stop
m      : manual mode
Ctrl-C : quit
"""


class KeyboardTeleop(Node):
    def __init__(self) -> None:
        super().__init__('keyboard_teleop')
        self.declare_parameter('linear_speed', 0.25)
        self.declare_parameter('angular_speed', 0.8)
        self.declare_parameter('publish_topic', '/cmd_vel_manual')
        self.declare_parameter('direct_cmd_vel', False)
        self.declare_parameter('mode_topic', '/mode_select')
        self.declare_parameter('estop_topic', '/emergency_stop')
        self.declare_parameter('idle_stop_cycles', 4)

        publish_topic = str(self.get_parameter('publish_topic').value).strip()
        if publish_topic == '/cmd_vel':
            self.get_logger().error(
                'publish_topic=/cmd_vel is unsafe and ignored; using /cmd_vel_manual instead'
            )
            publish_topic = '/cmd_vel_manual'
        if bool(self.get_parameter('direct_cmd_vel').value):
            self.get_logger().error(
                'direct_cmd_vel is unsafe and ignored; keyboard commands stay behind safety_mux'
            )

        self.linear_speed = float(self.get_parameter('linear_speed').value)
        self.angular_speed = float(self.get_parameter('angular_speed').value)
        self.idle_stop_cycles = int(self.get_parameter('idle_stop_cycles').value)

        self.publisher = self.create_publisher(Twist, publish_topic, 10)
        self.mode_publisher = self.create_publisher(
            String,
            str(self.get_parameter('mode_topic').value),
            10,
        )
        self.estop_publisher = self.create_publisher(
            Bool,
            str(self.get_parameter('estop_topic').value),
            10,
        )

        self.settings = termios.tcgetattr(sys.stdin)
        self.get_logger().info(f'Keyboard teleop publishing to {publish_topic}')

    def restore_terminal(self) -> None:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.settings)

    def get_key(self) -> str:
        tty.setraw(sys.stdin.fileno())
        ready, _, _ = select.select([sys.stdin], [], [], 0.1)
        key = sys.stdin.read(1) if ready else ''
        self.restore_terminal()
        return key

    def publish_mode(self, mode: str) -> None:
        self.mode_publisher.publish(String(data=mode))
        self.get_logger().info(f'Mode switched to {mode}')

    def publish_twist(self, linear: float, angular: float) -> None:
        msg = Twist()
        msg.linear.x = linear
        msg.angular.z = angular
        self.publisher.publish(msg)

    def stop(self) -> None:
        self.publish_twist(0.0, 0.0)


def main(args=None) -> None:
    rclpy.init(args=args)
    if not sys.stdin.isatty():
        print('keyboard_teleop requires an interactive terminal.', file=sys.stderr)
        rclpy.shutdown()
        return

    node = KeyboardTeleop()
    linear = 0.0
    angular = 0.0
    idle_count = 0

    try:
        print(HELP_TEXT)
        node.publish_mode('manual')

        while rclpy.ok():
            key = node.get_key()

            if key == '\x03':
                break
            if key == 'm':
                node.publish_mode('manual')
                idle_count = 0
                continue
            if key == ' ':
                linear = 0.0
                angular = 0.0
                node.estop_publisher.publish(Bool(data=True))
                node.stop()
                idle_count = 0
                continue
            if key == 'r':
                node.estop_publisher.publish(Bool(data=False))
                node.publish_mode('manual')
                idle_count = 0
                continue

            if key == 'w':
                linear = node.linear_speed
                angular = 0.0
                idle_count = 0
            elif key == 's':
                linear = -node.linear_speed
                angular = 0.0
                idle_count = 0
            elif key == 'a':
                linear = 0.0
                angular = node.angular_speed
                idle_count = 0
            elif key == 'd':
                linear = 0.0
                angular = -node.angular_speed
                idle_count = 0
            elif key == 'q':
                linear = node.linear_speed
                angular = node.angular_speed
                idle_count = 0
            elif key == 'e':
                linear = node.linear_speed
                angular = -node.angular_speed
                idle_count = 0
            elif key == 'x':
                linear = 0.0
                angular = 0.0
                idle_count = 0
            else:
                idle_count += 1
                if idle_count > node.idle_stop_cycles:
                    linear = 0.0
                    angular = 0.0

            node.publish_twist(linear, angular)
            rclpy.spin_once(node, timeout_sec=0.0)
    except Exception as exc:
        print(exc)
    finally:
        node.stop()
        node.restore_terminal()
        node.destroy_node()
        rclpy.shutdown()
