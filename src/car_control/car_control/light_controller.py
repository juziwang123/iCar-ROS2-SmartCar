import math
import threading
from typing import Optional

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Bool, Int32


class LightController(Node):
    """
    灯光控制节点
    - 开机状态：灯光常亮
    - 转弯状态：对应方向灯闪烁
    - 急停状态：所有灯快速闪烁
    
    支持两种控制方式：
    1. 通过 ROS2 话题发送灯光命令（适合仿真和测试）
    2. 通过 GPIO 直接控制（实车部署）
    """

    # 灯光模式定义
    MODE_OFF = 0
    MODE_CONSTANT = 1  # 常亮
    MODE_BLINK_SLOW = 2  # 慢闪 (500ms)
    MODE_BLINK_FAST = 3  # 快闪 (200ms)
    MODE_TURN_LEFT = 4  # 左转闪烁
    MODE_TURN_RIGHT = 5  # 右转闪烁

    def __init__(self) -> None:
        super().__init__('light_controller')
        
        # 参数声明
        self.declare_parameter('cmd_vel_topic', '/control/cmd_vel')
        self.declare_parameter('estop_topic', '/emergency_stop')
        self.declare_parameter('light_control_topic', '/car/light_control')
        self.declare_parameter('enable_gpio_control', False)
        self.declare_parameter('front_left_gpio', 17)
        self.declare_parameter('front_right_gpio', 27)
        self.declare_parameter('rear_left_gpio', 22)
        self.declare_parameter('rear_right_gpio', 23)
        self.declare_parameter('brake_gpio', 24)
        self.declare_parameter('turn_threshold', 0.3)  # rad/s，转向角速度阈值
        self.declare_parameter('blink_slow_interval', 0.5)  # 秒
        self.declare_parameter('blink_fast_interval', 0.2)  # 秒

        # 获取参数
        self.cmd_vel_topic = str(self.get_parameter('cmd_vel_topic').value)
        self.estop_topic = str(self.get_parameter('estop_topic').value)
        self.light_control_topic = str(self.get_parameter('light_control_topic').value)
        self.enable_gpio = bool(self.get_parameter('enable_gpio_control').value)
        self.front_left_gpio = int(self.get_parameter('front_left_gpio').value)
        self.front_right_gpio = int(self.get_parameter('front_right_gpio').value)
        self.rear_left_gpio = int(self.get_parameter('rear_left_gpio').value)
        self.rear_right_gpio = int(self.get_parameter('rear_right_gpio').value)
        self.brake_gpio = int(self.get_parameter('brake_gpio').value)
        self.turn_threshold = float(self.get_parameter('turn_threshold').value)
        self.blink_slow_interval = float(self.get_parameter('blink_slow_interval').value)
        self.blink_fast_interval = float(self.get_parameter('blink_fast_interval').value)

        # GPIO 初始化
        self.gpio_initialized = False
        self.gpio_lib = None
        if self.enable_gpio:
            try:
                import RPi.GPIO as GPIO
                self.gpio_lib = GPIO
                self._init_gpio()
                self.gpio_initialized = True
            except ImportError:
                self.get_logger().warn(
                    'RPi.GPIO not available, falling back to ROS2 topic-based control'
                )
            except Exception as e:
                self.get_logger().warn(f'GPIO initialization failed: {e}')

        # 状态变量
        self.current_mode = self.MODE_CONSTANT
        self.blink_state = False  # 闪烁时的开关状态
        self.blink_timer: Optional[threading.Timer] = None
        self.last_twist: Optional[Twist] = None
        self.is_emergency_stop = False

        # 发布者和订阅者
        self.light_pub = self.create_publisher(Int32, self.light_control_topic, 10)
        self.create_subscription(Twist, self.cmd_vel_topic, self._on_twist, 10)
        self.create_subscription(Bool, self.estop_topic, self._on_estop, 10)

        # 主控制循环定时器 (10Hz)
        self.control_timer = self.create_timer(0.1, self._update_lights)

        self.get_logger().info('Light controller started')
        self.get_logger().info(f'GPIO control enabled: {self.gpio_initialized}')

    def _init_gpio(self) -> None:
        """初始化 GPIO"""
        if not self.gpio_lib:
            return
        
        self.gpio_lib.setmode(self.gpio_lib.BCM)
        self.gpio_lib.setwarnings(False)
        
        pins = [
            self.front_left_gpio,
            self.front_right_gpio,
            self.rear_left_gpio,
            self.rear_right_gpio,
            self.brake_gpio,
        ]
        
        for pin in pins:
            try:
                self.gpio_lib.setup(pin, self.gpio_lib.OUT)
                self.gpio_lib.output(pin, self.gpio_lib.LOW)
            except Exception as e:
                self.get_logger().warn(f'Failed to setup GPIO pin {pin}: {e}')

    def _on_twist(self, msg: Twist) -> None:
        """接收速度命令"""
        self.last_twist = msg

    def _on_estop(self, msg: Bool) -> None:
        """接收急停信号"""
        self.is_emergency_stop = msg.data

    def _update_lights(self) -> None:
        """更新灯光状态"""
        # 急停优先级最高
        if self.is_emergency_stop:
            self._set_light_mode(self.MODE_BLINK_FAST)
            return

        # 如果没有接收到速度命令，默认常亮
        if self.last_twist is None:
            self._set_light_mode(self.MODE_CONSTANT)
            return

        # 根据角速度判断转向
        angular_z = self.last_twist.angular.z
        
        if abs(angular_z) > self.turn_threshold:
            if angular_z > 0:
                # 左转
                self._set_light_mode(self.MODE_TURN_LEFT)
            else:
                # 右转
                self._set_light_mode(self.MODE_TURN_RIGHT)
        else:
            # 直行或静止
            self._set_light_mode(self.MODE_CONSTANT)

    def _set_light_mode(self, mode: int) -> None:
        """设置灯光模式"""
        if self.current_mode == mode:
            return  # 模式未改变，不做处理

        self.current_mode = mode
        
        # 停止之前的闪烁定时器
        if self.blink_timer:
            self.blink_timer.cancel()
            self.blink_timer = None

        # 发布灯光模式
        self.light_pub.publish(Int32(data=mode))
        
        # 根据模式处理
        if mode == self.MODE_OFF:
            self._set_all_lights(False)
        elif mode == self.MODE_CONSTANT:
            self._set_all_lights(True)
            self.get_logger().debug('Light mode: CONSTANT (all on)')
        elif mode == self.MODE_BLINK_SLOW:
            self._start_blink(self.blink_slow_interval)
            self.get_logger().debug(f'Light mode: BLINK_SLOW ({self.blink_slow_interval}s)')
        elif mode == self.MODE_BLINK_FAST:
            self._start_blink(self.blink_fast_interval)
            self.get_logger().debug(f'Light mode: BLINK_FAST ({self.blink_fast_interval}s)')
        elif mode == self.MODE_TURN_LEFT:
            self._start_blink_directional('left')
            self.get_logger().debug('Light mode: TURN_LEFT')
        elif mode == self.MODE_TURN_RIGHT:
            self._start_blink_directional('right')
            self.get_logger().debug('Light mode: TURN_RIGHT')

    def _set_all_lights(self, state: bool) -> None:
        """设置所有灯的开关状态"""
        if self.gpio_initialized:
            gpio_value = self.gpio_lib.HIGH if state else self.gpio_lib.LOW
            pins = [
                self.front_left_gpio,
                self.front_right_gpio,
                self.rear_left_gpio,
                self.rear_right_gpio,
            ]
            for pin in pins:
                try:
                    self.gpio_lib.output(pin, gpio_value)
                except Exception as e:
                    self.get_logger().warn(f'Failed to set GPIO pin {pin}: {e}')

    def _start_blink(self, interval: float) -> None:
        """启动全部灯光闪烁"""
        self.blink_state = True
        self._set_all_lights(True)
        self._schedule_blink_toggle(interval)

    def _start_blink_directional(self, direction: str) -> None:
        """启动方向指示灯闪烁"""
        self.blink_state = True
        
        # 先点亮对应方向的灯
        if direction == 'left':
            self._set_directional_lights('left', True)
        else:
            self._set_directional_lights('right', True)
        
        # 后亮相反方向的灯（低优先级）
        if direction == 'left':
            self._set_directional_lights('right', False)
        else:
            self._set_directional_lights('left', False)
        
        self._schedule_blink_toggle(self.blink_slow_interval)

    def _set_directional_lights(self, direction: str, state: bool) -> None:
        """设置方向灯"""
        if not self.gpio_initialized:
            return

        gpio_value = self.gpio_lib.HIGH if state else self.gpio_lib.LOW
        
        if direction == 'left':
            pins = [self.front_left_gpio, self.rear_left_gpio]
        else:
            pins = [self.front_right_gpio, self.rear_right_gpio]
        
        for pin in pins:
            try:
                self.gpio_lib.output(pin, gpio_value)
            except Exception as e:
                self.get_logger().warn(f'Failed to set GPIO pin {pin}: {e}')

    def _schedule_blink_toggle(self, interval: float) -> None:
        """安排下一次闪烁切换"""
        def toggle():
            self.blink_state = not self.blink_state
            
            # 检查是否应该继续闪烁
            if self.current_mode == self.MODE_BLINK_FAST:
                self._set_all_lights(self.blink_state)
                self._schedule_blink_toggle(interval)
            elif self.current_mode in (self.MODE_BLINK_SLOW, self.MODE_TURN_LEFT, self.MODE_TURN_RIGHT):
                if self.current_mode in (self.MODE_TURN_LEFT, self.MODE_TURN_RIGHT):
                    # 方向灯闪烁逻辑
                    direction = 'left' if self.current_mode == self.MODE_TURN_LEFT else 'right'
                    self._set_directional_lights(direction, self.blink_state)
                else:
                    self._set_all_lights(self.blink_state)
                self._schedule_blink_toggle(interval)

        self.blink_timer = threading.Timer(interval, toggle)
        self.blink_timer.daemon = True
        self.blink_timer.start()

    def destroy_node(self) -> bool:
        """清理资源"""
        if self.blink_timer:
            self.blink_timer.cancel()
        
        if self.gpio_initialized and self.gpio_lib:
            try:
                self.gpio_lib.cleanup()
            except Exception as e:
                self.get_logger().warn(f'GPIO cleanup failed: {e}')
        
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = LightController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
