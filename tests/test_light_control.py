#!/usr/bin/env python3
"""
灯光控制测试脚本
演示所有灯光模式和转向灯功能
"""

import rclpy
import time
from geometry_msgs.msg import Twist
from std_msgs.msg import Bool, Int32
from rclpy.node import Node


class LightTester(Node):
    def __init__(self):
        super().__init__('light_tester')
        self.cmd_vel_pub = self.create_publisher(Twist, '/control/cmd_vel', 10)
        self.estop_pub = self.create_publisher(Bool, '/emergency_stop', 10)
        self.light_sub = self.create_subscription(
            Int32,
            '/car/light_control',
            self._on_light_mode,
            10
        )
        self.current_light_mode = None

    def _on_light_mode(self, msg):
        mode_names = {
            0: 'OFF',
            1: 'CONSTANT',
            2: 'BLINK_SLOW',
            3: 'BLINK_FAST',
            4: 'TURN_LEFT',
            5: 'TURN_RIGHT'
        }
        self.current_light_mode = mode_names.get(msg.data, 'UNKNOWN')
        self.get_logger().info(f'Light mode changed: {self.current_light_mode}')

    def test_light_modes(self):
        self.get_logger().info('=== 灯光控制测试开始 ===')
        
        # 测试1：启动后常亮
        self.get_logger().info('\n[测试1] 启动 - 灯光常亮')
        self.get_logger().info('期望模式: CONSTANT')
        time.sleep(2)
        
        # 测试2：直线行驶 - 灯光常亮
        self.get_logger().info('\n[测试2] 直线行驶 - 灯光常亮')
        twist = Twist()
        twist.linear.x = 0.2
        self.cmd_vel_pub.publish(twist)
        self.get_logger().info('发送: 线速度 0.2 m/s')
        self.get_logger().info('期望模式: CONSTANT')
        time.sleep(2)
        
        # 测试3：左转 - 左转指示灯闪烁
        self.get_logger().info('\n[测试3] 左转 - 左转指示灯闪烁 (500ms)')
        twist.linear.x = 0.2
        twist.angular.z = 0.5  # 左转
        self.cmd_vel_pub.publish(twist)
        self.get_logger().info('发送: 线速度 0.2 m/s, 角速度 0.5 rad/s (左转)')
        self.get_logger().info('期望模式: TURN_LEFT')
        time.sleep(4)
        
        # 测试4：右转 - 右转指示灯闪烁
        self.get_logger().info('\n[测试4] 右转 - 右转指示灯闪烁 (500ms)')
        twist.linear.x = 0.2
        twist.angular.z = -0.5  # 右转
        self.cmd_vel_pub.publish(twist)
        self.get_logger().info('发送: 线速度 0.2 m/s, 角速度 -0.5 rad/s (右转)')
        self.get_logger().info('期望模式: TURN_RIGHT')
        time.sleep(4)
        
        # 测试5：静止 - 灯光常亮
        self.get_logger().info('\n[测试5] 停车 - 灯光常亮')
        twist.linear.x = 0.0
        twist.angular.z = 0.0
        self.cmd_vel_pub.publish(twist)
        self.get_logger().info('发送: 线速度 0.0, 角速度 0.0')
        self.get_logger().info('期望模式: CONSTANT')
        time.sleep(2)
        
        # 测试6：急停 - 所有灯快速闪烁
        self.get_logger().info('\n[测试6] 急停 - 所有灯快速闪烁 (200ms)')
        estop_msg = Bool()
        estop_msg.data = True
        self.estop_pub.publish(estop_msg)
        self.get_logger().info('发送: 急停信号 = True')
        self.get_logger().info('期望模式: BLINK_FAST (红灯报警)')
        time.sleep(4)
        
        # 解除急停
        self.get_logger().info('\n[测试7] 解除急停 - 返回常亮')
        estop_msg.data = False
        self.estop_pub.publish(estop_msg)
        self.get_logger().info('发送: 急停信号 = False')
        self.get_logger().info('期望模式: CONSTANT')
        time.sleep(2)
        
        self.get_logger().info('\n=== 灯光控制测试完成 ===')


def main(args=None):
    rclpy.init(args=args)
    tester = LightTester()
    
    # 等待订阅连接
    time.sleep(1)
    
    try:
        tester.test_light_modes()
    except KeyboardInterrupt:
        pass
    finally:
        tester.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
