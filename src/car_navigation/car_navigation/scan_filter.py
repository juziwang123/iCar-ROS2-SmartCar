import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan


class ScanFilter(Node):
    def __init__(self) -> None:
        super().__init__('scan_filter')
        self.declare_parameter('input_topic', '/scan')
        self.declare_parameter('output_topic', '/downsampled_scan')
        self.declare_parameter('multiple', 2)

        self.multiple = max(1, int(self.get_parameter('multiple').value))
        self.publisher = self.create_publisher(
            LaserScan,
            str(self.get_parameter('output_topic').value),
            10,
        )
        self.create_subscription(
            LaserScan,
            str(self.get_parameter('input_topic').value),
            self._on_scan,
            10,
        )
        self.get_logger().info(
            f'Scan filter started: every {self.multiple} point(s)'
        )

    def _on_scan(self, msg: LaserScan) -> None:
        filtered = LaserScan()
        filtered.header = msg.header
        filtered.angle_min = msg.angle_min
        filtered.angle_max = msg.angle_max
        filtered.angle_increment = msg.angle_increment * self.multiple
        filtered.time_increment = msg.time_increment * self.multiple
        filtered.scan_time = msg.scan_time
        filtered.range_min = msg.range_min
        filtered.range_max = msg.range_max
        filtered.ranges = list(msg.ranges[::self.multiple])
        if msg.intensities:
            filtered.intensities = list(msg.intensities[::self.multiple])
        self.publisher.publish(filtered)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ScanFilter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
