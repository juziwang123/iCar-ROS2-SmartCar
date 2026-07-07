# ROS2 框架开发与使用完全教程

> 适用版本：ROS2 Humble (Ubuntu 22.04) / Jazzy (Ubuntu 24.04)  
> 更新日期：2025年7月

---

## 目录

1. [ROS2 概述与架构](#1-ros2-概述与架构)
2. [版本选择与安装](#2-版本选择与安装)
3. [核心概念：节点、话题、服务与动作](#3-核心概念节点话题服务与动作)
4. [工作空间与包管理](#4-工作空间与包管理)
5. [自定义消息接口](#5-自定义消息接口)
6. [Launch 启动文件](#6-launch-启动文件)
7. [参数系统](#7-参数系统)
8. [TF2 坐标变换](#8-tf2-坐标变换)
9. [URDF/XACRO 机器人建模](#9-urdfxacro-机器人建模)
10. [Gazebo 仿真](#10-gazebo-仿真)
11. [Nav2 导航与 SLAM](#11-nav2-导航与-slam)
12. [QoS 服务质量配置](#12-qos-服务质量配置)
13. [rosbag2 数据记录与回放](#13-rosbag2-数据记录与回放)
14. [调试工具：CLI、rqt 与 RViz2](#14-调试工具cli-rqt-与-rviz2)
15. [高级主题](#15-高级主题)
16. [最佳实践与常见陷阱](#16-最佳实践与常见陷阱)
17. [参考资源](#17-参考资源)

---

## 1. ROS2 概述与架构

### 1.1 什么是 ROS2？

ROS2（Robot Operating System 2）是一个用于机器人应用开发的**开源中间件框架**。它不是传统意义上的操作系统，而是提供了一套完整的开发工具、库和约定，使开发者能够构建复杂且稳健的机器人系统。

### 1.2 ROS2 与 ROS1 的主要区别

| 特性 | ROS1 | ROS2 |
|------|------|------|
| **通信中间件** | 自定义 TCP/UDP 协议 | DDS (Data Distribution Service) |
| **操作系统支持** | 仅 Linux (Ubuntu) | Linux / Windows / macOS |
| **实时性** | 不支持 | 支持实时控制 |
| **多机器人** | 需要额外配置 | 原生支持（通过 DDS） |
| **节点生命周期** | 无 | 托管节点生命周期管理 |
| **编译系统** | catkin_make | colcon |
| **Python 版本** | Python 2 | Python 3 |

### 1.3 系统架构

```
┌──────────────────────────────────────────────────┐
│                   用户应用程序                      │
│              (Python / C++ 节点)                   │
├──────────────────────────────────────────────────┤
│          rclpy (Python)     rclcpp (C++)           │
│          客户端库            客户端库                │
├──────────────────────────────────────────────────┤
│               rcl (C 通用客户端库)                   │
├──────────────────────────────────────────────────┤
│               rmw (ROS Middleware)                 │
│           DDS 抽象层 (多种实现可选)                  │
├──────────────────────────────────────────────────┤
│            DDS (数据分发服务)                        │
│   Fast DDS / Cyclone DDS / Connext DDS ...        │
├──────────────────────────────────────────────────┤
│            操作系统 (Linux/Windows/macOS)           │
└──────────────────────────────────────────────────┘
```

关键概念：
- **DDS（Data Distribution Service）**：ROS2 的通信核心，提供自动发现、发布/订阅、QoS 策略等能力
- **RMW（ROS Middleware）**：DDS 实现的抽象层，允许切换不同的 DDS 实现
- **Graph**：ROS2 网络中所有节点及其通信关系的统称

### 1.4 推荐的 DDS 实现

| DDS 实现 | 特点 | 推荐场景 |
|----------|------|----------|
| **Fast DDS** | 默认实现，由 eProsima 维护 | 通用场景 |
| **Cyclone DDS** | Eclipse 维护，性能优秀 | 高性能场景、多机器人 |
| **Connext DDS** | RTI 商业产品 | 工业级实时系统 |

---

## 2. 版本选择与安装

### 2.1 发行版对照表

| ROS2 发行版 | 状态 | Ubuntu 版本 | Python | 支持截止 |
|-------------|------|-------------|--------|----------|
| **Foxy** | EOL ❌ | 20.04 | 3.8 | 2023 |
| **Galactic** | EOL ❌ | 20.04 | 3.8 | 2024 |
| **Humble** | **LTS ✅** | **22.04** | 3.10 | **2027** |
| **Iron** | EOL ❌ | 22.04 | 3.10 | 2024 |
| **Jazzy** | **LTS ✅** | **24.04** | 3.12 | **2029** |
| **Rolling** | 滚动更新 | 24.04 | 3.12 | 持续 |

> **推荐选择**：新项目用 **Jazzy** (Ubuntu 24.04)，需要成熟生态的用 **Humble** (Ubuntu 22.04)。**不要使用 Iron（已 EOL）。**

### 2.2 二进制安装（以 Jazzy 为例）

#### 步骤 1：设置语言环境

```bash
sudo apt update && sudo apt install -y locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8
```

#### 步骤 2：启用 Universe 仓库并添加 ROS2 apt 源

```bash
sudo apt install -y software-properties-common
sudo add-apt-repository universe

sudo apt update && sudo apt install -y curl gnupg lsb-release
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
| sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
```

#### 步骤 3：安装 ROS2 桌面版

```bash
sudo apt update
sudo apt install -y ros-jazzy-desktop   # Jazzy 完整桌面版
# 或 ros-humble-desktop                 # Humble 完整桌面版
```

安装选项说明：

| 元包名称 | 内容 |
|----------|------|
| `ros-<distro>-ros-core` | 最小安装：通信库 + CLI |
| `ros-<distro>-ros-base` | + 常用依赖，无 GUI |
| `ros-<distro>-desktop` | + RViz2、demo 包（推荐） |
| `ros-<distro>-desktop-full` | + Gazebo 仿真（完整） |

#### 步骤 4：安装开发工具

```bash
sudo apt install -y \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-vcstool \
    python3-argcomplete \
    build-essential \
    git
```

#### 步骤 5：初始化 rosdep

```bash
sudo rosdep init
rosdep update
```

#### 步骤 6：设置环境变量

```bash
# 添加到 ~/.bashrc
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

### 2.3 验证安装

```bash
# 终端 1：启动发布者
ros2 run demo_nodes_cpp talker

# 终端 2：启动订阅者
ros2 run demo_nodes_py listener
```

如果看到 `[INFO] [...] I heard: [Hello World: N]` 则安装成功。

验证有用的命令：

```bash
ros2 topic list       # 显示活跃话题
ros2 node list        # 显示运行中的节点
ros2 --version        # 显示发行版版本
```

### 2.4 Docker 安装（备选方案）

如果不想直接安装到系统中，可以使用 Docker：

```bash
# 拉取官方镜像
docker pull osrf/ros:jazzy-desktop

# 运行容器
docker run -it --rm \
    -v /tmp/.X11-unix:/tmp/.X11-unix:ro \
    -e DISPLAY=$DISPLAY \
    osrf/ros:jazzy-desktop bash
```

| 镜像标签 | 内容 |
|----------|------|
| `osrf/ros:jazzy-ros-core` | 最小安装 |
| `osrf/ros:jazzy-ros-base` | + 常用依赖 |
| `osrf/ros:jazzy-desktop` | + RViz2、demo |
| `osrf/ros:jazzy-desktop-full` | + Gazebo |

---

## 3. 核心概念：节点、话题、服务与动作

ROS2 的核心通信模式有三种：**话题（Topics）**、**服务（Services）**和**动作（Actions）**。

### 3.1 节点（Node）

**节点**是 ROS2 计算图的基本单元。每个节点应完成单一逻辑功能。

```python
# Python 最小节点
import rclpy
from rclpy.node import Node

class MyNode(Node):
    def __init__(self):
        super().__init__('my_node_name')
        self.get_logger().info('Hello from Python node!')

def main(args=None):
    rclpy.init(args=args)
    node = MyNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
```

```cpp
// C++ 最小节点
#include <rclcpp/rclcpp.hpp>

class MyNode : public rclcpp::Node {
public:
    MyNode() : Node("my_node_name") {
        RCLCPP_INFO(this->get_logger(), "Hello from C++ node!");
    }
};

int main(int argc, char **argv) {
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<MyNode>());
    rclcpp::shutdown();
    return 0;
}
```

| API | Python (`rclpy`) | C++ (`rclcpp`) |
|-----|------------------|-----------------|
| 节点基类 | `rclpy.node.Node` | `rclcpp::Node` |
| 日志信息 | `self.get_logger().info()` | `RCLCPP_INFO(get_logger(), ...)` |
| 日志警告 | `self.get_logger().warn()` | `RCLCPP_WARN(get_logger(), ...)` |
| 日志错误 | `self.get_logger().error()` | `RCLCPP_ERROR(get_logger(), ...)` |
| 运行节点 | `rclpy.spin(node)` | `rclcpp::spin(node_ptr)` |
| 创建定时器 | `self.create_timer(period, callback)` | `this->create_wall_timer(duration, callback)` |

### 3.2 话题（Topics）—— 发布/订阅模型

话题用于**单向、连续的数据流**通信。适用场景：传感器数据、速度指令、状态信息。

| 特性 | 描述 |
|------|------|
| 模型 | 发布/订阅（一对多） |
| 方向 | 单向，流式传输 |
| 数据定义 | `.msg` 文件 |
| 通信模式 | 异步（发布者发送后不等待） |

#### Python 发布者

```python
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

class PublisherNode(Node):
    def __init__(self):
        super().__init__('publisher_node')
        # 创建发布者：话题名、消息类型、队列深度
        self.publisher = self.create_publisher(String, '/robot_news', 10)
        # 创建定时器：每 0.5 秒发布一次
        self.timer = self.create_timer(0.5, self.timer_callback)
        self.count = 0

    def timer_callback(self):
        msg = String()
        msg.data = f'Hello from Python! Count: {self.count}'
        self.publisher.publish(msg)
        self.get_logger().info(f'Publishing: "{msg.data}"')
        self.count += 1

def main(args=None):
    rclpy.init(args=args)
    node = PublisherNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
```

#### Python 订阅者

```python
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

class SubscriberNode(Node):
    def __init__(self):
        super().__init__('subscriber_node')
        # 创建订阅者：话题名、消息类型、回调函数、队列深度
        self.subscription = self.create_subscription(
            String, '/robot_news', self.listener_callback, 10)

    def listener_callback(self, msg):
        self.get_logger().info(f'I heard: "{msg.data}"')

def main(args=None):
    rclpy.init(args=args)
    node = SubscriberNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
```

#### C++ 发布者

```cpp
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>

class PublisherNode : public rclcpp::Node {
public:
    PublisherNode() : Node("publisher_node"), count_(0) {
        publisher_ = this->create_publisher<std_msgs::msg::String>("/robot_news", 10);
        timer_ = this->create_wall_timer(
            std::chrono::milliseconds(500),
            std::bind(&PublisherNode::timer_callback, this));
    }

private:
    void timer_callback() {
        auto msg = std_msgs::msg::String();
        msg.data = "Hello from C++! Count: " + std::to_string(count_++);
        RCLCPP_INFO(this->get_logger(), "Publishing: '%s'", msg.data.c_str());
        publisher_->publish(msg);
    }

    rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
    rclcpp::TimerBase::SharedPtr timer_;
    size_t count_;
};
```

#### C++ 订阅者

```cpp
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>

class SubscriberNode : public rclcpp::Node {
public:
    SubscriberNode() : Node("subscriber_node") {
        subscription_ = this->create_subscription<std_msgs::msg::String>(
            "/robot_news", 10,
            std::bind(&SubscriberNode::topic_callback, this, std::placeholders::_1));
    }

private:
    void topic_callback(const std_msgs::msg::String &msg) {
        RCLCPP_INFO(this->get_logger(), "I heard: '%s'", msg.data.c_str());
    }

    rclcpp::Subscription<std_msgs::msg::String>::SharedPtr subscription_;
};
```

### 3.3 服务（Services）—— 请求/响应模型

服务用于**同步的请求-响应**通信。适用场景：快速计算、配置查询、布尔状态检查。

| 特性 | 描述 |
|------|------|
| 模型 | 客户端/服务器（一对一） |
| 方向 | 双向，单次请求-响应 |
| 数据定义 | `.srv` 文件（用 `---` 分隔请求与响应） |
| 适用场景 | 快速计算、配置查询 |

#### 服务定义示例 (`.srv`)

```yaml
# AddTwoInts.srv
int32 a
int32 b
---
int32 sum
```

#### Python 服务端

```python
from example_interfaces.srv import AddTwoInts

class AddTwoIntsServer(Node):
    def __init__(self):
        super().__init__('add_two_ints_server')
        self.srv = self.create_service(AddTwoInts, 'add_two_ints', self.add_two_ints_callback)

    def add_two_ints_callback(self, request, response):
        response.sum = request.a + request.b
        self.get_logger().info(f'Incoming request\na: {request.a} b: {request.b}')
        return response
```

#### Python 客户端

```python
from example_interfaces.srv import AddTwoInts

class AddTwoIntsClient(Node):
    def __init__(self):
        super().__init__('add_two_ints_client')
        self.cli = self.create_client(AddTwoInts, 'add_two_ints')
        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting...')
        self.req = AddTwoInts.Request()

    def send_request(self, a, b):
        self.req.a = a
        self.req.b = b
        self.future = self.cli.call_async(self.req)
        rclpy.spin_until_future_complete(self, self.future)
        return self.future.result()
```

#### C++ 服务端

```cpp
#include <example_interfaces/srv/add_two_ints.hpp>

class AddTwoIntsServer : public rclcpp::Node {
public:
    AddTwoIntsServer() : Node("add_two_ints_server") {
        service_ = this->create_service<example_interfaces::srv::AddTwoInts>(
            "add_two_ints",
            std::bind(&AddTwoIntsServer::handle_service, this,
                      std::placeholders::_1, std::placeholders::_2));
    }

private:
    void handle_service(
        const std::shared_ptr<example_interfaces::srv::AddTwoInts::Request> request,
        std::shared_ptr<example_interfaces::srv::AddTwoInts::Response> response)
    {
        response->sum = request->a + request->b;
        RCLCPP_INFO(get_logger(), "Incoming request: %ld + %ld = %ld",
                    request->a, request->b, response->sum);
    }

    rclcpp::Service<example_interfaces::srv::AddTwoInts>::SharedPtr service_;
};
```

### 3.4 动作（Actions）—— 长时间运行任务

动作用于**可抢占的长时间运行任务**，包含三个子接口：

| 子接口 | 类型 | 用途 |
|--------|------|------|
| **Goal（目标）** | 服务 | 发起任务 |
| **Feedback（反馈）**| 话题 | 周期性进度更新 |
| **Result（结果）** | 服务 | 完成时的最终结果 |

| 特性 | 描述 |
|------|------|
| 模型 | 动作客户端/服务器 |
| 可取消 | ✅ 是 |
| 数据定义 | `.action` 文件（用 `---` 分隔三个部分） |
| 适用场景 | 导航、机械臂移动、数据处理任务 |

#### 动作定义示例 (`.action`)

```yaml
# Fibonacci.action
int32 order          # 目标：请求
---
int32[] partial_sequence  # 反馈：进度
---
int32[] sequence     # 结果：最终输出
```

#### Python 动作服务端

```python
import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, GoalResponse, CancelResponse
from example_interfaces.action import Fibonacci

class FibonacciActionServer(Node):
    def __init__(self):
        super().__init__('fibonacci_action_server')
        self.action_server = ActionServer(
            self,
            Fibonacci,
            'fibonacci',
            execute_callback=self.execute_callback,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback
        )

    def goal_callback(self, goal_request):
        self.get_logger().info(f'Received goal request: {goal_request.order}')
        return GoalResponse.ACCEPT  # 或 GoalResponse.REJECT

    def cancel_callback(self, goal_handle):
        self.get_logger().info('Received cancel request')
        return CancelResponse.ACCEPT  # 或 CancelResponse.REJECT

    async def execute_callback(self, goal_handle):
        order = goal_handle.request.order
        feedback_msg = Fibonacci.Feedback()
        sequence = [0, 1]

        for i in range(1, order):
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                self.get_logger().info('Goal canceled')
                return Fibonacci.Result()

            sequence.append(sequence[i] + sequence[i-1])
            feedback_msg.partial_sequence = sequence
            goal_handle.publish_feedback(feedback_msg)
            await asyncio.sleep(1.0)

        goal_handle.succeed()
        result = Fibonacci.Result()
        result.sequence = sequence
        return result
```

### 3.5 通信方式选择指南

| 通信方式 | 适用场景 | 示例 |
|----------|----------|------|
| **Topic（话题）** | 连续数据流；一对多；发后即忘 | 传感器数据、速度指令、状态广播 |
| **Service（服务）** | 短请求/响应；需要直接答案 | 传感器校准、获取某个字段值 |
| **Action（动作）** | 长时间任务；需要反馈和取消 | 导航到目标点、机械臂抓取 |

> **黄金法则**：能用 Topic 就用 Topic；不行用 Service；都不行用 Action。

---

## 4. 工作空间与包管理

### 4.1 工作空间结构

```
~/ros2_ws/
├── src/              ← 你的包源代码放这里
│   ├── my_package/
│   └── another_package/
├── build/            ← colcon 编译中间文件（可 .gitignore）
├── install/          ← 编译产物（可 .gitignore）
└── log/              ← 编译日志（可 .gitignore）
```

### 4.2 创建工作空间

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws
colcon build   # 初始化工作空间结构
```

### 4.3 创建包

```bash
cd ~/ros2_ws/src

# C++ 包（带节点）
ros2 pkg create --build-type ament_cmake \
    --node-name my_node \
    --dependencies rclcpp std_msgs \
    my_cpp_package

# Python 包（带节点）
ros2 pkg create --build-type ament_python \
    --node-name my_node \
    --dependencies rclpy std_msgs \
    my_python_package

# 纯消息接口包
ros2 pkg create --build-type ament_cmake \
    --dependencies builtin_interfaces \
    my_interfaces
```

### 4.4 包结构

#### C++ 包

```
my_cpp_package/
├── CMakeLists.txt          # 编译配置（必需）
├── package.xml             # 包元数据（必需）
├── include/
│   └── my_cpp_package/     # 头文件
│       └── my_node.hpp
├── src/                    # 源文件
│   └── my_node.cpp
├── launch/                 # 启动文件
│   └── my_launch.py
└── config/                 # 配置文件
    └── params.yaml
```

**最小 `CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.8)
project(my_cpp_package)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)

add_executable(my_node src/my_node.cpp)
target_include_directories(my_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
ament_target_dependencies(my_node rclcpp std_msgs)

install(TARGETS my_node
  DESTINATION lib/${PROJECT_NAME})

# 安装启动文件和配置
install(DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME})

ament_package()
```

#### Python 包

```
my_python_package/
├── setup.py                # 安装配置（必需）
├── setup.cfg               # （必需）
├── package.xml             # 包元数据（必需）
├── resource/
│   └── my_python_package   # 标记文件（空）
├── test/
│   └── test_*.py
├── launch/
│   └── my_launch.py
├── config/
│   └── params.yaml
└── my_python_package/      # Python 模块
    ├── __init__.py
    └── my_node.py
```

**最小 `setup.py`：**

```python
from setuptools import find_packages, setup

package_name = 'my_python_package'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # 安装启动文件
        ('share/' + package_name + '/launch',
            glob('launch/*.launch.py')),
        # 安装配置文件
        ('share/' + package_name + '/config',
            glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='your_name',
    maintainer_email='your_email@example.com',
    description='Description of my package',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'my_node = my_python_package.my_node:main',
        ],
    },
)
```

**最小 `package.xml`：**

```xml
<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd"
    schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>my_package</name>
  <version>0.0.0</version>
  <description>My ROS2 package</description>
  <maintainer email="me@example.com">my_name</maintainer>
  <license>Apache-2.0</license>

  <buildtool_depend>ament_cmake</buildtool_depend>
  <!-- 或对 Python 包使用 ament_python -->

  <!-- 依赖项 -->
  <depend>rclcpp</depend>
  <depend>std_msgs</depend>

  <test_depend>ament_lint_auto</test_depend>
  <test_depend>ament_lint_common</test_depend>

  <export>
    <build_type>ament_cmake</build_type>
    <!-- 或 ament_python -->
  </export>
</package>
```

### 4.5 编译包

```bash
cd ~/ros2_ws
source /opt/ros/jazzy/setup.bash   # 先 source underlay！

# 编译所有包
colcon build

# 仅编译指定包
colcon build --packages-select my_package

# 编译指定包及其依赖
colcon build --packages-up-to my_package

# 符号链接安装（Python 编辑后不需重新编译，推荐开发时使用）
colcon build --symlink-install

# Release 模式编译（C++ 必须）
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release

# 跳过测试
colcon build --cmake-args -DBUILD_TESTING=0
```

### 4.6 常用 colcon 命令

| 命令 | 用途 |
|------|------|
| `colcon build` | 编译所有包 |
| `colcon build --packages-select <pkg>` | 编译单个包 |
| `colcon build --packages-up-to <pkg>` | 编译包及其依赖 |
| `colcon build --symlink-install` | 符号链接安装（开发推荐） |
| `colcon test` | 运行测试 |
| `colcon test --packages-select <pkg>` | 运行指定包的测试 |
| `colcon list` | 列出所有包 |
| `colcon graph` | 显示依赖图 |

### 4.7 Source 环境

```bash
# source 工作空间
source ~/ros2_ws/install/setup.bash

# 添加到 ~/.bashrc
echo "source ~/ros2_ws/install/setup.bash" >> ~/.bashrc
```

### 4.8 运行节点

```bash
# 运行包中的可执行文件
ros2 run my_package my_node

# 带参数运行
ros2 run my_package my_node --ros-args -p param_name:=value

# 重新映射话题名
ros2 run my_package my_node --ros-args -r /old_topic:=/new_topic
```

### 4.9 管理多个发行版

如果你需要在 Humble 和 Jazzy 之间切换：

```bash
# 添加到 ~/.bashrc
# 不要自动 source！改用函数手动切换
function ros2-jazzy() {
    source /opt/ros/jazzy/setup.bash
    [ -f ~/ros2_ws/install/setup.bash ] && source ~/ros2_ws/install/setup.bash
    export ROS_DOMAIN_ID=42
    echo "ROS 2 Jazzy activated, DOMAIN=42"
}

function ros2-humble() {
    source /opt/ros/humble/setup.bash
    [ -f ~/humble_ws/install/setup.bash ] && source ~/humble_ws/install/setup.bash
    export ROS_DOMAIN_ID=42
    echo "ROS 2 Humble activated, DOMAIN=42"
}
```

---

## 5. 自定义消息接口

### 5.1 接口类型

| 文件类型 | 用途 | 分隔符 |
|----------|------|--------|
| `.msg` | 话题的消息定义 | 无 |
| `.srv` | 服务的请求+响应定义 | `---`（一次） |
| `.action` | 动作的目标+反馈+结果定义 | `---`（两次） |

### 5.2 创建自定义接口包

```bash
cd ~/ros2_ws/src
ros2 pkg create --build-type ament_cmake custom_interfaces

cd custom_interfaces
mkdir msg srv action
```

### 5.3 定义消息 (`.msg`)

```yaml
# custom_interfaces/msg/RobotStatus.msg
string name
float64 x
float64 y
float64 theta
string status    # "idle", "moving", "error"
int32 battery_level
```

### 5.4 定义服务 (`.srv`)

```yaml
# custom_interfaces/srv/SetRobotMode.srv
string mode     # "manual", "auto", "emergency"
---
bool success
string message
```

### 5.5 定义动作 (`.action`)

```yaml
# custom_interfaces/action/NavigateTo.action
geometry_msgs/PoseStamped target_pose
float32 max_speed
---
float32 distance_remaining
float32 estimated_time_remaining
---
bool success
string message
```

### 5.6 配置 CMakeLists.txt

```cmake
cmake_minimum_required(VERSION 3.8)
project(custom_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(geometry_msgs REQUIRED)   # 如果用了 geometry_msgs

# 生成消息接口
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/RobotStatus.msg"
  "srv/SetRobotMode.srv"
  "action/NavigateTo.action"
  DEPENDENCIES builtin_interfaces geometry_msgs
)

ament_package()
```

### 5.7 配置 package.xml

```xml
<?xml version="1.0"?>
<package format="3">
  <name>custom_interfaces</name>
  <version>0.0.0</version>
  <description>Custom ROS2 interfaces</description>
  <maintainer email="me@example.com">my_name</maintainer>
  <license>Apache-2.0</license>

  <buildtool_depend>ament_cmake</buildtool_depend>

  <!-- 接口生成依赖 -->
  <build_depend>rosidl_default_generators</build_depend>
  <exec_depend>rosidl_default_runtime</exec_depend>

  <!-- 消息定义中引用的其他消息 -->
  <depend>builtin_interfaces</depend>
  <depend>geometry_msgs</depend>

  <member_of_group>rosidl_interface_packages</member_of_group>

  <export>
    <build_type>ament_cmake</build_type>
  </export>
</package>
```

### 5.8 编译和使用自定义接口

```bash
# 编译
cd ~/ros2_ws
colcon build --packages-select custom_interfaces
source install/setup.bash

# 查看生成的接口
ros2 interface show custom_interfaces/msg/RobotStatus
ros2 interface show custom_interfaces/srv/SetRobotMode
ros2 interface show custom_interfaces/action/NavigateTo

# 在 Python 中使用
from custom_interfaces.msg import RobotStatus
from custom_interfaces.srv import SetRobotMode
from custom_interfaces.action import NavigateTo
```

### 5.9 常用内置消息类型

| ROS2 类型 | C++ 对应 | Python 对应 |
|-----------|----------|-------------|
| `bool` | `bool` | `builtins.bool` |
| `int8` / `int16` / `int32` / `int64` | `int8_t` / `int16_t` / `int32_t` / `int64_t` | `builtins.int` |
| `uint8` / `uint16` / `uint32` / `uint64` | `uint8_t` / ... | `builtins.int` |
| `float32` / `float64` | `float` / `double` | `builtins.float` |
| `string` | `std::string` | `builtins.str` |
| `byte[]` | `std::vector<uint8_t>` | `bytes` |
| `Header` (`std_msgs`) | `std_msgs::msg::Header` | `std_msgs.msg.Header` |
| `Time` / `Duration` (`builtin_interfaces`) | `builtin_interfaces::msg::Time` | `builtin_interfaces.msg.Time` |

---

## 6. Launch 启动文件

ROS2 支持三种格式的启动文件：**Python**、**XML** 和 **YAML**。

### 6.1 格式选择

| 格式 | 适用场景 | 局限性 |
|------|----------|--------|
| **XML** | 简单配置、ROS1 习惯、可读性高 | 无事件处理、无条件逻辑 |
| **YAML** | 深度嵌套配置简洁 | 同 XML |
| **Python** | 复杂逻辑、条件判断、事件处理、动态配置 | 更冗长、需要 Python 知识 |

> **建议**：简单场景用 XML/YAML，复杂场景用 Python。

### 6.2 XML 启动文件

```xml
<!-- my_launch.xml -->
<launch>
    <!-- 声明参数 -->
    <arg name="background_r" default="0" />
    <arg name="background_g" default="0" />
    <arg name="background_b" default="255" />

    <!-- 启动节点 -->
    <node pkg="turtlesim" exec="turtlesim_node" name="sim" namespace="turtlesim1">
        <param name="background_r" value="$(var background_r)" />
        <param name="background_g" value="$(var background_g)" />
        <param name="background_b" value="$(var background_b)" />
    </node>

    <!-- 从 YAML 文件加载参数 -->
    <node pkg="my_pkg" exec="my_node" name="my_node" output="screen">
        <param from="$(find-pkg-share my_pkg)/config/params.yaml" />
        <!-- 重映射话题 -->
        <remap from="/cmd_vel" to="/turtle1/cmd_vel" />
    </node>
</launch>
```

### 6.3 Python 启动文件

```python
# my_launch.py
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, GroupAction
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node, PushRosNamespace
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    # 声明启动参数
    use_sim_time = LaunchConfiguration('use_sim_time', default='false')
    robot_name = LaunchConfiguration('robot_name', default='my_robot')

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='false',
                              description='Use simulation (Gazebo) clock if true'),
        DeclareLaunchArgument('robot_name', default_value='my_robot',
                              description='Name of the robot'),

        # 带命名空间的节点组
        GroupAction([
            PushRosNamespace(robot_name),
            Node(
                package='my_package',
                executable='robot_driver',
                name='driver',
                parameters=[{
                    'use_sim_time': use_sim_time,
                }],
                output='screen',
                # 重映射
                remappings=[('/cmd_vel', '/diff_drive/cmd_vel')],
            ),
            Node(
                package='my_package',
                executable='lidar_processor',
                name='lidar',
                parameters=[PathJoinSubstitution([
                    get_package_share_directory('my_package'),
                    'config', 'lidar.yaml'
                ])],
            ),
        ]),

        # 条件启动
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            condition=UnlessCondition(LaunchConfiguration('headless')),
            arguments=['-d', PathJoinSubstitution([
                get_package_share_directory('my_package'),
                'rviz', 'config.rviz'
            ])],
        ),

        # 包含其他启动文件
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                PathJoinSubstitution([
                    get_package_share_directory('my_package'),
                    'launch', 'sensors.launch.py'
                ])
            ]),
            launch_arguments={'use_sim_time': use_sim_time}.items(),
        ),
    ])
```

### 6.4 YAML 启动文件

```yaml
# my_launch.yaml
launch:
  - arg:
      name: "background_r"
      default: "0"

  - node:
      pkg: "turtlesim"
      exec: "turtlesim_node"
      name: "sim"
      namespace: "turtlesim1"
      param:
        - name: "background_r"
          value: "$(var background_r)"

  - node:
      pkg: "my_pkg"
      exec: "my_node"
      name: "my_node"
      param:
        - from: "$(find-pkg-share my_pkg)/config/params.yaml"
      remap:
        - from: "/cmd_vel"
          to: "/turtle1/cmd_vel"
```

### 6.5 运行启动文件

```bash
# 从包中启动
ros2 launch <package_name> <launch_file>

# 带参数启动
ros2 launch my_package my_launch.py use_sim_time:=true

# 查看可用参数
ros2 launch my_package my_launch.py --show-args

# 调试模式
ros2 launch my_package my_launch.py --debug

# 直接路径启动（开发时方便）
ros2 launch path/to/my_launch.py
```

### 6.6 常用替换表达式 (Substitutions)

| 表达式 | XML/YAML 语法 | Python 等效 |
|--------|---------------|-------------|
| 包共享目录 | `$(find-pkg-share pkg)` | `FindPackageShare('pkg')` |
| 启动参数 | `$(var arg_name)` | `LaunchConfiguration('arg_name')` |
| 环境变量 | `$(env VAR)` | `EnvironmentVariable('VAR')` |
| Python 表达式 | `$(eval 'expr')` | N/A（直接用 Python） |
| 命令输出 | `$(command 'cmd')` | `Command('cmd')` |
| 路径拼接 | N/A | `PathJoinSubstitution([...])` |

### 6.7 YAML 参数文件

```yaml
# config/robot_params.yaml
/**:
  ros__parameters:
    # 全局参数（应用于所有节点）
    use_sim_time: false

/my_node_name:
  ros__parameters:
    # 节点特定参数
    publish_period: 0.5
    linear_speed_max: 1.0
    angular_speed_max: 2.0
    sensor_frame: "laser_link"
    enabled_features: ["odometry", "lidar"]

/another_node:
  ros__parameters:
    debug_mode: false
    log_level: "info"
```

---

## 7. 参数系统

### 7.1 参数声明与获取

#### Python

```python
class MyParamNode(Node):
    def __init__(self):
        super().__init__('my_param_node')

        # 声明参数（带默认值）
        self.declare_parameter('my_int', 42)
        self.declare_parameter('my_float', 3.14)
        self.declare_parameter('my_string', 'hello')
        self.declare_parameter('my_bool', True)
        self.declare_parameter('my_array', [1, 2, 3])

        # 获取参数（方法一）
        my_int = self.get_parameter('my_int').get_parameter_value().integer_value

        # 获取参数（方法二：声明并获取一步到位）
        my_int = self.declare_parameter('my_int', 42).value

        # 允许未声明参数（开发调试用）
        # node = Node('my_node', allow_undeclared_parameters=True)
```

#### C++

```cpp
class MyParamNode : public rclcpp::Node {
public:
    MyParamNode() : Node("my_param_node") {
        // 声明参数
        this->declare_parameter<int>("my_int", 42);
        this->declare_parameter<double>("my_float", 3.14);
        this->declare_parameter<std::string>("my_string", "hello");

        // 获取参数
        int my_int = this->get_parameter("my_int").as_int();
        double my_float = this->get_parameter("my_float").as_double();
        std::string my_string = this->get_parameter("my_string").as_string();
    }
};
```

### 7.2 参数描述符（带约束）

```cpp
// C++ — 定义参数约束
auto descriptor = rcl_interfaces::msg::ParameterDescriptor{};
descriptor.description = "Maximum linear velocity in m/s";

auto float_range = rcl_interfaces::msg::FloatingPointRange{};
float_range.from_value = 0.0;
float_range.to_value = 5.0;
float_range.step = 0.1;
descriptor.floating_point_range.push_back(float_range);

this->declare_parameter<double>("max_linear_vel", 1.0, descriptor);
```

### 7.3 参数回调（运行时动态更新）

#### Python

```python
from rclpy.parameter import Parameter

class MyNode(Node):
    def __init__(self):
        super().__init__('my_node')
        self.declare_parameter('speed', 0.5)
        self.speed_ = self.get_parameter('speed').value

        # 注册参数变化后的回调（Post-set callback）
        self.add_post_set_parameters_callback(self.parameters_callback)

    def parameters_callback(self, params):
        for param in params:
            if param.name == 'speed':
                self.speed_ = param.value
                self.get_logger().info(f'Speed updated to: {self.speed_}')
        return SetParametersResult(successful=True)
```

#### C++

```cpp
#include "rclcpp/rclcpp.hpp"

class MyNode : public rclcpp::Node {
public:
    MyNode() : Node("my_node") {
        this->declare_parameter("speed", 0.5);

        // Post-set callback
        param_callback_handle_ = this->add_post_set_parameters_callback(
            std::bind(&MyNode::parametersCallback, this, std::placeholders::_1));
    }

private:
    rcl_interfaces::msg::SetParametersResult parametersCallback(
        const std::vector<rclcpp::Parameter> &parameters)
    {
        rcl_interfaces::msg::SetParametersResult result;
        result.successful = true;
        for (const auto &param : parameters) {
            if (param.get_name() == "speed") {
                speed_ = param.as_double();
                RCLCPP_INFO(get_logger(), "Speed updated to: %.2f", speed_);
            }
        }
        return result;
    }

    rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr
        param_callback_handle_;
    double speed_;
};
```

### 7.4 参数 CLI 命令

```bash
# 列出节点的所有参数
ros2 param list

# 获取参数值
ros2 param get /my_node my_int

# 设置参数（运行时动态修改）
ros2 param set /my_node my_int 100

# 导出参数到文件
ros2 param dump /my_node > params.yaml

# 从文件加载参数
ros2 param load /my_node params.yaml

# 运行时通过命令行传递参数
ros2 run my_pkg my_node --ros-args -p speed:=2.0

# 运行时加载参数文件
ros2 run my_pkg my_node --ros-args --params-file config/params.yaml
```

### 7.5 三种参数回调对比

| 回调类型 | 注册方法 | 用途 |
|----------|----------|------|
| **Pre-set** | `add_pre_set_parameters_callback()` | 在参数设置前修改/添加/删除参数 |
| **On-set** | `add_on_set_parameters_callback()` | 检查参数变更并明确批准/拒绝 |
| **Post-set** | `add_post_set_parameters_callback()` | 参数成功变更后修改节点状态 |

---

## 8. TF2 坐标变换

TF2 是 ROS2 中用于跟踪**多个坐标系随时间变化**的变换库。

### 8.1 核心概念

| 概念 | 描述 |
|------|------|
| **TransformBroadcaster** | 发布动态变换到 `/tf` 话题 |
| **StaticTransformBroadcaster** | 发布固定变换到 `/tf_static` 话题 |
| **TransformListener + Buffer** | 接收并缓存所有 TF 数据，支持查询任意两帧之间的变换 |
| **lookupTransform()** | 查询两个坐标系之间的变换 |
| **TF Tree** | 所有坐标系组成的树状关系图 |

### 8.2 典型坐标框架链

```
map → odom → base_footprint → base_link → sensor_link
                                           → camera_link
                                           → laser_link
```

### 8.3 Python TF2 广播器

```python
import rclpy
from rclpy.node import Node
from tf2_ros import TransformBroadcaster
from geometry_msgs.msg import TransformStamped
import math

class TFBroadcaster(Node):
    def __init__(self):
        super().__init__('tf_broadcaster')
        self.tf_broadcaster = TransformBroadcaster(self)
        self.timer = self.create_timer(0.1, self.broadcast_timer_callback)  # 10Hz
        self.angle = 0.0

    def broadcast_timer_callback(self):
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = 'world'
        t.child_frame_id = 'moving_frame'

        # 设置位姿
        t.transform.translation.x = math.cos(self.angle)
        t.transform.translation.y = math.sin(self.angle)
        t.transform.translation.z = 0.0
        t.transform.rotation.x = 0.0
        t.transform.rotation.y = 0.0
        t.transform.rotation.z = 0.0
        t.transform.rotation.w = 1.0

        self.tf_broadcaster.sendTransform(t)
        self.angle += 0.01
```

### 8.4 Python TF2 监听器

```python
from tf2_ros.buffer import Buffer
from tf2_ros.transform_listener import TransformListener

class TFListener(Node):
    def __init__(self):
        super().__init__('tf_listener')

        # 创建 Buffer 和 Listener
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.timer = self.create_timer(0.1, self.get_transform)

    def get_transform(self):
        try:
            # 查询 source_frame 到 target_frame 的变换
            # lookup_transform(target_frame, source_frame, time)
            trans = self.tf_buffer.lookup_transform(
                'world',             # 目标帧
                'moving_frame',       # 源帧
                rclpy.time.Time()     # 使用最新可用时间
            )
            self.get_logger().info(
                f'Translation: ({trans.transform.translation.x:.2f}, '
                f'{trans.transform.translation.y:.2f})')
        except Exception as e:
            self.get_logger().warn(f'Could not transform: {e}')
```

### 8.5 C++ TF2 广播器

```cpp
#include <tf2_ros/transform_broadcaster.h>
#include <geometry_msgs/msg/transform_stamped.hpp>

class TFBroadcaster : public rclcpp::Node {
public:
    TFBroadcaster() : Node("tf_broadcaster") {
        tf_broadcaster_ = std::make_shared<tf2_ros::TransformBroadcaster>(this);
        timer_ = this->create_wall_timer(
            std::chrono::milliseconds(100),
            std::bind(&TFBroadcaster::broadcast_callback, this));
    }

private:
    void broadcast_callback() {
        geometry_msgs::msg::TransformStamped t;
        t.header.stamp = this->now();
        t.header.frame_id = "world";
        t.child_frame_id = "moving_frame";

        t.transform.translation.x = 1.0;
        t.transform.translation.y = 0.0;
        t.transform.translation.z = 0.0;
        t.transform.rotation.w = 1.0;

        tf_broadcaster_->sendTransform(t);
    }

    std::shared_ptr<tf2_ros::TransformBroadcaster> tf_broadcaster_;
    rclcpp::TimerBase::SharedPtr timer_;
};
```

### 8.6 静态 TF 广播器

```python
from tf2_ros import StaticTransformBroadcaster

class StaticTFBroadcaster(Node):
    def __init__(self):
        super().__init__('static_tf_broadcaster')
        self.static_broadcaster = StaticTransformBroadcaster(self)

        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = 'base_link'
        t.child_frame_id = 'laser_link'
        t.transform.translation.x = 0.2
        t.transform.translation.z = 0.1
        t.transform.rotation.w = 1.0

        self.static_broadcaster.sendTransform(t)
```

### 8.7 TF2 调试工具

```bash
# 查看两个坐标系之间的变换
ros2 run tf2_ros tf2_echo world moving_frame

# 生成 TF 树的 PDF 图
ros2 run tf2_tools view_frames

# 监控 TF 话题
ros2 topic echo /tf
ros2 topic echo /tf_static

# 以特定频率发布静态变换（命令行）
ros2 run tf2_ros static_transform_publisher \
    1.0 0.0 0.0 0.0 0.0 0.0 1.0 \
    world camera_link
# 参数: x y z qx qy qz qw parent_frame child_frame
```

---

## 9. URDF/XACRO 机器人建模

### 9.1 URDF vs XACRO

| 特性 | URDF | XACRO |
|------|------|-------|
| 格式 | 纯 XML | XML + 宏语言 |
| 可重用性 | 低（复制粘贴） | 高（宏、变量、包含） |
| 可维护性 | 差（大模型极长） | 好（模块化） |
| 最终使用 | 直接加载 | 先编译为 URDF 再加载 |

> **建议**：总是使用 XACRO 编写模型，运行前编译为 URDF。

### 9.2 机器人描述包结构

```
my_robot_description/
├── CMakeLists.txt
├── package.xml
├── urdf/
│   ├── my_robot.urdf.xacro       ← 主 XACRO 文件
│   ├── common_properties.xacro   ← 共享宏和属性
│   ├── sensors.xacro             ← 传感器定义
│   └── materials.xacro           ← 颜色和材质
├── meshes/                        ← 3D 模型文件 (.stl, .dae)
├── launch/
│   ├── display.launch.py         ← RViz 可视化
│   └── gazebo.launch.py          ← Gazebo 仿真
├── rviz/
│   └── urdf_config.rviz          ← RViz 配置
└── config/
    └── controllers.yaml          ← 控制器配置
```

### 9.3 XACRO 基础语法

```xml
<?xml version="1.0"?>
<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="my_robot">

    <!-- 属性（变量） -->
    <xacro:property name="base_length" value="0.5" />
    <xacro:property name="base_width" value="0.3" />
    <xacro:property name="base_height" value="0.1" />
    <xacro:property name="wheel_radius" value="0.05" />
    <xacro:property name="PI" value="3.14159265359" />

    <!-- 宏定义（可重用组件） -->
    <xacro:macro name="wheel" params="prefix xyz parent">
        <joint name="${prefix}_wheel_joint" type="continuous">
            <origin xyz="${xyz}" rpy="0 ${PI/2} 0" />
            <parent link="${parent}" />
            <child link="${prefix}_wheel" />
            <axis xyz="0 0 1" />
        </joint>

        <link name="${prefix}_wheel">
            <visual>
                <geometry>
                    <cylinder radius="${wheel_radius}" length="0.02" />
                </geometry>
                <material name="black" />
            </visual>
            <collision>
                <geometry>
                    <cylinder radius="${wheel_radius}" length="0.02" />
                </geometry>
            </collision>
            <inertial>
                <mass value="0.1" />
                <inertia ixx="0.0001" iyy="0.0001" izz="0.0001"
                         ixy="0" ixz="0" iyz="0" />
            </inertial>
        </link>
    </xacro:macro>

    <!-- 使用宏 -->
    <xacro:wheel prefix="left" xyz="0 ${base_width/2} 0" parent="base_link" />
    <xacro:wheel prefix="right" xyz="0 ${-base_width/2} 0" parent="base_link" />

</robot>
```

### 9.4 URDF 链接结构

每个 `<link>` 需要三个元素：

```xml
<link name="base_link">
    <!-- 视觉：RViz 中显示的 -->
    <visual>
        <origin xyz="0 0 0" rpy="0 0 0" />
        <geometry>
            <box size="0.5 0.3 0.1" />
        </geometry>
        <material name="blue">
            <color rgba="0 0 0.8 1" />
        </material>
    </visual>

    <!-- 碰撞：Gazebo 物理计算用（可以比 visual 简化） -->
    <collision>
        <origin xyz="0 0 0" rpy="0 0 0" />
        <geometry>
            <box size="0.5 0.3 0.1" />
        </geometry>
    </collision>

    <!-- 惯性：质量和惯量矩阵（Gazebo 动力学仿真必需！） -->
    <inertial>
        <origin xyz="0 0 0" rpy="0 0 0" />
        <mass value="5.0" />
        <!-- 长方体惯量公式：ixx = m/12*(h²+d²) -->
        <inertia
            ixx="0.0417" ixy="0.0" ixz="0.0"
            iyy="0.1083" iyz="0.0"
            izz="0.1417" />
    </inertial>
</link>
```

### 9.5 关节类型

| 类型 | 描述 | 示例 |
|------|------|------|
| `fixed` | 固定连接 | 传感器安装 |
| `revolute` | 旋转关节（有角度限制） | 机械臂关节 |
| `continuous` | 连续旋转（无限制） | 车轮 |
| `prismatic` | 线性关节（滑动） | 升降台 |
| `floating` | 6 自由度浮动 | 无人机机身 |
| `planar` | 平面运动 | 移动机器人在平面上 |

### 9.6 RViz 可视化启动文件

```python
# launch/display.launch.py
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, Command
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    pkg_share = get_package_share_directory('my_robot_description')
    xacro_file = os.path.join(pkg_share, 'urdf', 'my_robot.urdf.xacro')

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('gui', default_value='true',
                              description='Launch joint_state_publisher_gui'),

        # 使用 robot_state_publisher 发布 robot_description
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            parameters=[{
                'robot_description': Command(['xacro ', xacro_file]),
                'use_sim_time': LaunchConfiguration('use_sim_time'),
            }],
        ),

        # Joint State Publisher（可选 GUI）
        Node(
            package='joint_state_publisher_gui',
            executable='joint_state_publisher_gui',
            condition=IfCondition(LaunchConfiguration('gui')),
        ),

        # RViz2
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            arguments=['-d', os.path.join(pkg_share, 'rviz', 'urdf_config.rviz')],
        ),
    ])
```

```bash
# 启动可视化
ros2 launch my_robot_description display.launch.py
```

### 9.7 关键注意事项

1. **务必设置惯性**：没有 `<inertial>`，Gazebo 无法仿真，会崩溃
2. **碰撞简化**：`<collision>` 几何体可比 `<visual>` 简化，提高物理计算性能
3. **网格路径**：使用 `package://my_pkg/meshes/file.stl` 定位 3D 文件
4. **XACRO 需编译**：通过 `Command(['xacro', urdf_path])` 在启动时转换

---

## 10. Gazebo 仿真

### 10.1 Gazebo Classic vs Gazebo Sim (Harmonic)

| 特性 | Gazebo Classic (v11) | Gazebo Sim (Harmonic) |
|------|---------------------|----------------------|
| 命令 | `gazebo` | `gz sim` |
| 默认配对 | ROS2 Humble | ROS2 Jazzy |
| SDF 版本 | 1.6 | 1.11 |
| 状态 | **已弃用** | **当前推荐** |
| ROS 桥接 | `gazebo_ros_pkgs` | `ros_gz_bridge` |

### 10.2 Gazebo 插件配置（XACRO 中）

```xml
<!-- 差速驱动插件 -->
<gazebo>
    <plugin name="diff_drive" filename="libgazebo_ros_diff_drive.so">
        <left_joint>left_wheel_joint</left_joint>
        <right_joint>right_wheel_joint</right_joint>
        <wheel_separation>0.3</wheel_separation>
        <wheel_diameter>0.1</wheel_diameter>
        <max_wheel_torque>20.0</max_wheel_torque>
        <max_wheel_acceleration>10.0</max_wheel_acceleration>
        <command_topic>cmd_vel</command_topic>
    </plugin>
</gazebo>

<!-- 激光雷达传感器插件 -->
<gazebo reference="laser_link">
    <sensor name="laser" type="ray">
        <pose>0 0 0 0 0 0</pose>
        <ray>
            <scan>
                <horizontal>
                    <samples>360</samples>
                    <resolution>1</resolution>
                    <min_angle>-1.57</min_angle>
                    <max_angle>1.57</max_angle>
                </horizontal>
            </scan>
            <range>
                <min>0.1</min>
                <max>12.0</max>
            </range>
        </ray>
        <plugin name="laser_controller" filename="libgazebo_ros_ray_sensor.so">
            <ros>
                <namespace>/robot</namespace>
                <remapping>~/out:=scan</remapping>
            </ros>
            <output_type>sensor_msgs/LaserScan</output_type>
        </plugin>
    </sensor>
</gazebo>
```

### 10.3 Gazebo 启动文件

```python
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, ExecuteProcess, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.substitutions import Command, FindExecutable, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():
    pkg_share = FindPackageShare('my_robot_description')

    return LaunchDescription([
        # 启动 Gazebo 世界
        ExecuteProcess(
            cmd=['gazebo', '--verbose', '-s', 'libgazebo_ros_factory.so'],
            output='screen',
        ),

        # 生成并发布 robot_description
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            parameters=[{
                'robot_description': Command([
                    FindExecutable(name='xacro'), ' ',
                    PathJoinSubstitution([pkg_share, 'urdf', 'my_robot.urdf.xacro'])
                ]),
            }],
        ),

        # 在 Gazebo 中生成机器人
        Node(
            package='gazebo_ros',
            executable='spawn_entity.py',
            arguments=['-entity', 'my_robot',
                       '-topic', 'robot_description',
                       '-x', '0.0', '-y', '0.0', '-z', '0.1'],
            output='screen',
        ),
    ])
```

### 10.4 Gazebo Sim (Harmonic) + ROS2 Jazzy 桥接

对于现代 Gazebo Sim（Harmonic），使用 `ros_gz_bridge` 进行 ROS2 ↔ GZ 消息传递：

```yaml
# config/gz_bridge.yaml
# ROS2 话题 → GZ 话题
- ros_topic: "/cmd_vel"
  gz_topic: "/model/my_robot/cmd_vel"
  ros_type_name: "geometry_msgs/msg/Twist"
  gz_type_name: "gz.msgs.Twist"
  direction: ROS_TO_GZ

# GZ 话题 → ROS2 话题
- ros_topic: "/scan"
  gz_topic: "/world/default/model/my_robot/link/laser_link/sensor/laser/scan"
  ros_type_name: "sensor_msgs/msg/LaserScan"
  gz_type_name: "gz.msgs.LaserScan"
  direction: GZ_TO_ROS

- ros_topic: "/odom"
  gz_topic: "/model/my_robot/odometry"
  ros_type_name: "nav_msgs/msg/Odometry"
  gz_type_name: "gz.msgs.Odometry"
  direction: GZ_TO_ROS
```

```bash
# 启动桥接
ros2 run ros_gz_bridge parameter_bridge --ros-args \
    -p config_file:=config/gz_bridge.yaml
```

---

## 11. Nav2 导航与 SLAM

### 11.1 安装

```bash
# Jazzy
sudo apt install ros-jazzy-navigation2 ros-jazzy-nav2-bringup \
    ros-jazzy-slam-toolbox ros-jazzy-nav2-amcl \
    ros-jazzy-nav2-map-server

# Humble
sudo apt install ros-humble-navigation2 ros-humble-nav2-bringup \
    ros-humble-slam-toolbox ros-humble-nav2-amcl \
    ros-humble-nav2-map-server
```

### 11.2 Nav2 架构

```
┌────────────────────────────────────────────┐
│              BT Navigator                    │
│        (行为树导航协调器)                      │
├────────────────────────────────────────────┤
│  ┌─────────────┐  ┌────────────────────┐   │
│  │Planner Server│  │  Controller Server  │   │
│  │  (全局规划器)  │  │    (局部控制器)      │   │
│  └─────────────┘  └────────────────────┘   │
├────────────────────────────────────────────┤
│  ┌─────────────┐  ┌────────────────────┐   │
│  │  Map Server  │  │       AMCL          │   │
│  │  (地图服务器)  │  │     (定位模块)       │   │
│  └─────────────┘  └────────────────────┘   │
├────────────────────────────────────────────┤
│           Recovery Behaviors                │
│    (恢复行为：旋转/后退/清除代价地图)           │
└────────────────────────────────────────────┘
```

| 组件 | 作用 |
|------|------|
| **Map Server** | 加载并提供占用栅格地图 |
| **AMCL** | 自适应蒙特卡洛定位：在已知地图上估计位姿 |
| **Planner Server** | 全局路径规划（NavFn、Smac Planner） |
| **Controller Server** | 局部路径跟随 + 避障（DWB、MPPI） |
| **BT Navigator** | 行为树编排导航任务 |
| **Recovery Behaviors** | 被困时的恢复策略（旋转、后退、清除代价地图） |
| **Smoother Server** | 路径平滑优化 |
| **Waypoint Follower** | 航点导航 |

### 11.3 SLAM 建图工作流

```bash
# 步骤 1：启动仿真环境（机器人 + 世界）
ros2 launch my_robot_description gazebo.launch.py

# 步骤 2：启动 SLAM Toolbox（在线异步建图）
ros2 launch slam_toolbox online_async_launch.py \
    slam_params_file:=src/my_robot_description/config/mapper_params_online_async.yaml \
    use_sim_time:=true

# 步骤 3：手动遥控机器人探索环境
ros2 run teleop_twist_keyboard teleop_twist_keyboard

# 步骤 4（可选）：在 RViz2 中观察建图过程
rviz2

# 步骤 5：保存地图
ros2 run nav2_map_server map_saver_cli -f ~/my_map
# 生成 my_map.pgm（图像）和 my_map.yaml（配置）
```

### 11.4 自主导航工作流

```bash
# 使用保存的地图启动 Nav2
ros2 launch nav2_bringup bringup_launch.py \
    map:=/home/user/my_map.yaml \
    use_sim_time:=true

# 在 RViz2 中操作：
# 1. 点击 "2D Pose Estimate" 设置机器人初始位置
# 2. 点击 "Nav2 Goal" 发送导航目标点
# 3. 观察机器人自动规划路径并到达目标
```

### 11.5 关键参数配置

```yaml
# navigator_params.yaml
bt_navigator:
  ros__parameters:
    global_frame: map
    robot_base_frame: base_link
    transform_tolerance: 0.5
    use_sim_time: true

# controller_server 参数
controller_server:
  ros__parameters:
    controller_frequency: 20.0
    min_x_velocity_threshold: 0.001
    min_theta_velocity_threshold: 0.001
    # DWB 控制器插件
    FollowPath:
      plugin: "dwb_core::DWBLocalPlanner"
      max_vel_x: 0.5
      min_vel_x: -0.1
      max_vel_theta: 1.0
      min_vel_theta: -1.0

# planner_server 参数
planner_server:
  ros__parameters:
    planner_plugins: ["GridBased"]
    GridBased:
      plugin: "nav2_navfn_planner/NavfnPlanner"
      tolerance: 0.5
```

---

## 12. QoS 服务质量配置

### 12.1 QoS 策略

| 策略 | 选项 | 描述 |
|------|------|------|
| **Reliability（可靠性）** | `reliable` | 保证送达（类似 TCP），会重试 |
| | `best_effort` | 尽力而为（类似 UDP），可能丢失 |
| **Durability（持久性）** | `volatile` | 不保存旧消息 |
| | `transient_local` | 保存最近消息，迟到订阅者可收到 |
| **History（历史）** | `keep_last` + `depth` | 仅保留最近 N 条消息 |
| | `keep_all` | 保留所有消息 |
| **Liveliness（活跃性）** | `automatic` | 自动 |
| | `manual_by_topic` | 手动确认 |

### 12.2 兼容性矩阵

#### Reliability

| 发布者 | 订阅者 | 兼容？ |
|--------|--------|--------|
| Best Effort | Best Effort | ✅ |
| Best Effort | Reliable | ❌ |
| Reliable | Best Effort | ✅ |
| Reliable | Reliable | ✅ |

#### Durability

| 发布者 | 订阅者 | 兼容？ |
|--------|--------|--------|
| Volatile | Volatile | ✅ |
| Volatile | Transient Local | ❌ |
| Transient Local | Volatile | ✅ |
| Transient Local | Transient Local | ✅（含历史消息） |

### 12.3 预定义 QoS Profile

| Profile | Reliability | Durability | Depth | 适用场景 |
|---------|-------------|------------|-------|----------|
| **Default** | Reliable | Volatile | 10 | 通用 |
| **Sensor Data** | Best Effort | Volatile | 5 | 传感器高频数据 |
| **Parameters** | Reliable | Volatile | 1000 | 参数事件 |
| **Services** | Reliable | Volatile | - | 服务通信 |
| **System Default** | 取决于 RMW | 取决于 RMW | - | - |

### 12.4 配置示例

#### C++

```cpp
// 可靠 + 瞬态本地（类似 ROS1 latching）
auto qos = rclcpp::QoS(10)
    .reliable()
    .transient_local();

// 传感器数据预设（Best Effort）
auto qos = rclcpp::SensorDataQoS();

// 自定义
auto qos = rclcpp::QoS(rclcpp::KeepLast(5))
    .best_effort()
    .durability_volatile();

// 用于发布者
publisher_ = this->create_publisher<MsgType>("/topic", qos);
// 用于订阅者
subscription_ = this->create_subscription<MsgType>("/topic", qos, callback);
```

#### Python

```python
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

# 自定义 QoS
qos = QoSProfile(
    depth=10,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST
)

# 传感器数据 QoS（Best Effort）
from rclpy.qos import qos_profile_sensor_data

# 使用
self.publisher = self.create_publisher(MsgType, '/topic', qos)
self.subscription = self.create_subscription(MsgType, '/topic', callback, qos)
```

### 12.5 关键建议

1. **地图类话题**必须使用 `TRANSIENT_LOCAL`，否则迟到订阅者收不到地图
2. **传感器数据**（LaserScan、Camera）通常使用 `BEST_EFFORT`，丢几帧不影响
3. **QoS 不匹配会导致静默通信失败**——用 `ros2 topic info /topic -v` 检查

---

## 13. rosbag2 数据记录与回放

### 13.1 录制数据

```bash
# 录制单个话题
ros2 bag record /topic_name

# 录制多个话题
ros2 bag record -o my_bag /topic1 /topic2 /topic3

# 录制所有话题
ros2 bag record -a

# 压缩录制
ros2 bag record -a --compression-mode file --compression-format zstd

# 按大小分割（100MB）
ros2 bag record -a -b 100000000

# 按时间分割（3600秒）
ros2 bag record -a -d 3600

# 快照模式（内存环形缓冲，触发时写入磁盘）
ros2 bag record --snapshot-mode --max-cache-size 100000
# 触发写入：ros2 service call /rosbag2_recorder/snapshot ...
```

### 13.2 查看 Bag 信息

```bash
ros2 bag info <bag_directory>
ros2 bag info my_bag
```

输出：
```
Files:             my_bag.db3
Bag size:          2.5 MB
Storage id:        sqlite3
Duration:          60.0s
Start:             Jul  7 2025 10:00:00.000
End:               Jul  7 2025 10:01:00.000
Messages:          6000
Topic information:
  Topic: /scan | Type: sensor_msgs/msg/LaserScan | Count: 600 | ...
  Topic: /odom | Type: nav_msgs/msg/Odometry      | Count: 600 | ...
```

### 13.3 回放数据

```bash
# 基本回放
ros2 bag play <bag_directory>

# 倍速回放
ros2 bag play my_bag --rate 2.0    # 2倍速
ros2 bag play my_bag --rate 0.5    # 半速

# 循环回放
ros2 bag play my_bag --loop

# 筛选话题回放
ros2 bag play my_bag --topics /topic1 /topic2
ros2 bag play my_bag --exclude-topics /topic3
ros2 bag play my_bag --regex "/sensor/.*"

# 多个 bag 文件同步回放
ros2 bag play -i bag1 -i bag2 -i bag3
```

### 13.4 回放时键盘控制

| 按键 | 动作 |
|------|------|
| `SPACE` | 暂停 / 继续 |
| `→` | 播放下一帧 |
| `↑` | 加速 10% |
| `↓` | 减速 10% |

### 13.5 其他操作

```bash
# 转换格式（sqlite3 → MCAP）
ros2 bag convert -i input_bag -o output_bag --storage-options ...
# 注意：MCAP 是新版推荐的格式，支持更好的压缩和跨平台

# 重建索引（bag 损坏时）
ros2 bag reindex <bag_directory>
```

### 13.6 Python API 录制

```python
import rclpy
from rclpy.node import Node
from rclpy.serialization import serialize_message
from std_msgs.msg import String
import rosbag2_py

class BagRecorderNode(Node):
    def __init__(self):
        super().__init__('bag_recorder')

        # 创建 writer
        self.writer = rosbag2_py.SequentialWriter()
        storage_options = rosbag2_py._storage.StorageOptions(
            uri='my_recorded_bag',
            storage_id='mcap')
        converter_options = rosbag2_py._storage.ConverterOptions('', '')
        self.writer.open(storage_options, converter_options)

        # 注册话题
        topic_info = rosbag2_py._storage.TopicMetadata(
            name='chatter',
            type='std_msgs/msg/String',
            serialization_format='cdr')
        self.writer.create_topic(topic_info)

        # 订阅 + 写入
        self.subscription = self.create_subscription(
            String, 'chatter', self.callback, 10)

    def callback(self, msg):
        self.writer.write(
            'chatter',
            serialize_message(msg),
            self.get_clock().now().nanoseconds)

    def __del__(self):
        del self.writer   # 确保正确关闭
```

---

## 14. 调试工具：CLI、rqt 与 RViz2

### 14.1 命令行工具速查表

#### 节点

| 命令 | 用途 |
|------|------|
| `ros2 node list` | 列出所有运行的节点 |
| `ros2 node info /node_name` | 查看节点信息（话题、服务、动作） |

#### 话题

| 命令 | 用途 |
|------|------|
| `ros2 topic list` | 列出所有活跃话题 |
| `ros2 topic list -t` | 列出话题及消息类型 |
| `ros2 topic echo /topic` | 实时查看话题消息 |
| `ros2 topic info /topic` | 话题详细信息 |
| `ros2 topic info /topic -v` | 详细信息（含 QoS） |
| `ros2 topic hz /topic` | 测量发布频率 (Hz) |
| `ros2 topic bw /topic` | 测量带宽 |
| `ros2 topic type /topic` | 显示话题消息类型 |
| `ros2 topic find <msg_type>` | 查找使用指定类型的的话题 |
| `ros2 topic pub /topic <type> "{data}"` | 发布消息（加 `--once` 单次） |

#### 服务

| 命令 | 用途 |
|------|------|
| `ros2 service list` | 列出所有活跃服务 |
| `ros2 service type /service` | 显示服务类型 |
| `ros2 service info /service` | 服务详细信息 |
| `ros2 service call /service <type> "{data}"` | 调用服务 |

#### 参数

| 命令 | 用途 |
|------|------|
| `ros2 param list` | 列出所有节点的参数 |
| `ros2 param get /node param_name` | 获取参数值 |
| `ros2 param set /node param_name value` | 动态设置参数 |
| `ros2 param dump /node > file.yaml` | 导出参数 |
| `ros2 param load /node file.yaml` | 加载参数 |

#### 动作

| 命令 | 用途 |
|------|------|
| `ros2 action list` | 列出所有活跃动作 |
| `ros2 action list -t` | 列出动作及类型 |
| `ros2 action info /action` | 动作详细信息 |
| `ros2 action send_goal /action <type> "{data}"` | 发送动作目标（加 `--feedback` 查看反馈） |

#### 系统

| 命令 | 用途 |
|------|------|
| `ros2 doctor` | 运行系统诊断 |
| `ros2 interface show <type>` | 查看接口定义 |
| `ros2 interface list` | 列出所有可用接口 |
| `ros2 pkg list` | 列出所有已安装的包 |
| `ros2 pkg executables <pkg>` | 列出包中的可执行文件 |
| `ros2 lifecycle list` | 列出托管（生命周期）节点 |
| `ros2 lifecycle get /node` | 获取生命周期状态 |

### 14.2 rqt 工具集

| 插件 | 启动命令 | 用途 |
|------|----------|------|
| **rqt_graph** | `rqt_graph` | 可视化节点→话题→节点连接图 |
| **rqt_console** | `ros2 run rqt_console rqt_console` | 查看和过滤日志 |
| **rqt_plot** | `rqt_plot` | 实时 2D 时序图 |
| **rqt_topic** | `rqt` → Plugins → Topic Monitor | 监控带宽、频率 |
| **rqt_pub** | `rqt` → Plugins → Message Publisher | GUI 消息发布 |
| **rqt_reconfigure** | `ros2 run rqt_reconfigure rqt_reconfigure` | 动态参数调节 |
| **rqt_image_view** | `ros2 run rqt_image_view rqt_image_view` | 查看摄像头图像 |
| **rqt_bag** | `rqt` → Plugins → Logging | GUI 录制/回放 bag |

### 14.3 RViz2 可视化

```bash
# 启动 RViz2
rviz2

# 加载保存的配置
rviz2 -d my_config.rviz
```

#### 常用显示类型

| Display 类型 | 典型话题 | 显示内容 |
|-------------|----------|----------|
| **RobotModel** | `/robot_description` | URDF/Xacro 机器人模型 |
| **TF** | （自动检测） | 坐标系轴 |
| **LaserScan** | `/scan` | 2D 激光雷达扫描 |
| **PointCloud2** | `/points` | 3D 点云 |
| **Map** | `/map` | 占用栅格地图 |
| **Image** | `/camera/image_raw` | 摄像头图像 |
| **Path** | `/plan` | 规划路径 |
| **Odometry** | `/odom` | 里程计轨迹 |
| **Marker/MarkerArray** | `/visualization_marker*` | 自定义可视化标记 |

#### Global Options 推荐设置

| 设置 | 推荐值 |
|------|--------|
| **Fixed Frame** | `map`（无地图时用 `odom`） |
| **Frame Rate** | 30 |

### 14.4 调试工作流

```bash
# 标准调试流程
1. ros2 topic list                       # 预期的话题是否存在？
2. ros2 topic info /topic -v             # 发布者/订阅者/类型/QoS 是否正确？
3. ros2 topic echo /topic                # 数据是否在流动？
4. ros2 topic hz /topic                  # 频率是否正常？
5. rqt_graph                             # 可视化连接拓扑
6. rviz2                                 # 可视化数据
7. ros2 doctor                           # 系统健康检查
```

### 14.5 常见问题排查

| 问题 | 检查方法 |
|------|----------|
| **话题无数据** | `ros2 topic echo /topic` — 确认发布者已启动 |
| **QoS 不匹配** | `ros2 topic info /topic -v` — 传感器数据常需 `BEST_EFFORT` |
| **RViz2 缺少 TF 帧** | `ros2 run tf2_tools view_frames` — 检查 TF 树完整性 |
| **节点互发现不到** | `echo $ROS_DOMAIN_ID` — 多机之间必须一致 |
| **看不到地图** | 地图话题 QoS 必须为 `TRANSIENT_LOCAL`；检查 `map→odom→base_link` TF 链 |
| **生命周期节点未激活** | `ros2 lifecycle list` → `ros2 lifecycle set /node configure` → `activate` |
| **命名空间问题** | `ros2 topic list` 检查话题是否带命名空间前缀 |

---

## 15. 高级主题

### 15.1 生命周期节点（Lifecycle Nodes）

生命周期节点是 ROS2 的托管节点，具有内置状态机，支持受控的**启动、停止和错误处理**。

#### 状态机

```
                    ┌──────────┐
                    │  Start   │
                    └────┬─────┘
                         ↓
              ┌──────────────────┐
              │   unconfigured   │
              └────────┬─────────┘
                       ↓  on_configure()
              ┌──────────────────┐
              │     inactive     │
              └────────┬─────────┘
                       ↓  on_activate()
              ┌──────────────────┐
           ┌──│      active      │──┐
           │  └────────┬─────────┘  │
           │           ↓            ↓
           │  on_deactivate()  on_shutdown()
           │           ↓            ↓
           │  ┌──────────────────┐ ┌──────────┐
           │  │     inactive     │ │ finalize │
           │  └────────┬─────────┘ └──────────┘
           │           ↓
           │  on_cleanup()
           │           ↓
           │  ┌──────────────────┐
           └─→│   unconfigured   │
              └──────────────────┘
```

#### 关键回调

每个 `LifecycleNode` 重写以下回调：

```cpp
CallbackReturn on_configure(const State & prev_state);   // 创建发布者/定时器
CallbackReturn on_activate(const State & prev_state);     // 启动发布
CallbackReturn on_deactivate(const State & prev_state);   // 停止发布
CallbackReturn on_cleanup(const State & prev_state);      // 销毁发布者/定时器
CallbackReturn on_shutdown(const State & prev_state);     // 最终化
CallbackReturn on_error(const State & prev_state);        // 错误处理
```

#### CLI 命令

```bash
ros2 lifecycle get /lc_node          # 获取当前状态
ros2 lifecycle set /lc_node configure # 触发状态转换
ros2 lifecycle list /lc_node          # 列出可用转换
ros2 lifecycle list /lc_node -a       # 显示完整状态机
```

#### 典型使用流程

```bash
# 启动节点（unconfigured 状态）
ros2 run my_pkg my_lifecycle_node

# 配置节点（创建通信资源）
ros2 lifecycle set /my_node configure

# 激活节点（开始发布/处理）
ros2 lifecycle set /my_node activate

# 暂停节点
ros2 lifecycle set /my_node deactivate

# 清理节点
ros2 lifecycle set /my_node cleanup

# 关闭节点
ros2 lifecycle set /my_node shutdown
```

### 15.2 节点组合（Composition）

组合允许在**同一进程中运行多个节点**，通过**零拷贝（Intra-Process Communication）** 共享内存来传递消息，大幅减少延迟和序列化开销。

#### 组合方式

```bash
# A. 手动组合（代码中直接实例化）
ros2 run composition manual_composition

# B. 动态加载组合（运行时加载共享库）
ros2 run composition dlopen_composition \
    `ros2 pkg prefix composition`/lib/libtalker_component.so

# C. 启动动作组合（推荐）
ros2 launch composition composition_demo_launch.py
```

#### Python 组合节点定义

```python
import rclpy
from rclpy.node import Node
from rclcpp_components import NodeFactory, register_node

# 注意：Python 组合节点需要继承 Node 并注册为 component
# 实际工程中，C++ 更适合组合场景（更好的零拷贝支持）
```

#### C++ 组合节点定义

```cpp
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_components/register_node_macro.hpp>

namespace my_namespace {

class MyComponent : public rclcpp::Node {
public:
    explicit MyComponent(const rclcpp::NodeOptions &options)
        : Node("my_component", options) {
        // 节点逻辑
    }
};

} // namespace my_namespace

// 注册为组件
RCLCPP_COMPONENTS_REGISTER_NODE(my_namespace::MyComponent)
```

#### 在启动文件中使用组合

```python
from launch_ros.actions import LoadComposableNodes, ComposableNodeContainer
from launch_ros.descriptions import ComposableNode

# 创建组合容器
container = ComposableNodeContainer(
    name='my_container',
    namespace='',
    package='rclcpp_components',
    executable='component_container',
    composable_node_descriptions=[
        ComposableNode(
            package='my_package',
            plugin='my_namespace::SensorDriver',
            name='sensor_driver',
            extra_arguments=[{'use_intra_process_comms': True}],
        ),
        ComposableNode(
            package='my_package',
            plugin='my_namespace::DataProcessor',
            name='data_processor',
            extra_arguments=[{'use_intra_process_comms': True}],
        ),
    ],
    output='screen',
)
```

#### 验证组合

```bash
ros2 component list   # 显示容器中的节点
```

### 15.3 进程内通信 (Intra-Process Communication)

当多个节点在**同一进程**中运行时（通过组合），ROS2 可以使用**零拷贝**消息传递：

```python
# 在 ComposableNode 中启用 IPC
ComposableNode(
    ...,
    extra_arguments=[{'use_intra_process_comms': True}]
)
```

### 15.4 RMW（ROS Middleware）切换

```bash
# 临时切换 DDS 实现
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
ros2 run my_pkg my_node

# 安装不同的 RMW
sudo apt install ros-jazzy-rmw-cyclonedds-cpp
sudo apt install ros-jazzy-rmw-fastrtps-cpp   # 默认
```

### 15.5 ROS_DOMAIN_ID

`ROS_DOMAIN_ID` 用于**隔离不同 ROS2 网络**，防止通信干扰：

```bash
# 设置为 0-101 之间的值（默认 0）
export ROS_DOMAIN_ID=42

# 不同 DOMAIN_ID 的节点互不可见
# 同一台机器上不同组的节点应使用不同的 DOMAIN_ID
```

### 15.6 多机通信

ROS2 通过 DDS 原生支持多机通信：

```bash
# 所有机器必须：
# 1. 使用相同的 ROS_DOMAIN_ID
# 2. 在同一个网络中（或配置 DDS 发现）
# 3. 运行兼容的 ROS2 发行版

# 检查通信
# 机器 A
ros2 run demo_nodes_cpp talker

# 机器 B
ros2 run demo_nodes_py listener
# 如果能看到消息，说明多机通信正常
```

---

## 16. 最佳实践与常见陷阱

### 16.1 最佳实践

#### 项目组织
1. **每个节点一个文件**，每个节点实现一个单一逻辑功能
2. **接口定义独立成包**：`.msg`、`.srv`、`.action` 放在独立的 `_interfaces` 包中
3. **机器人描述独立成包**：URDF/XACRO 放在 `_description` 包中
4. **分离启动和配置**：启动文件在 `launch/`，参数在 `config/`

#### 编码规范
1. **显式生命周期的节点**应处理 `configure` → `activate` → `deactivate` 流程
2. **大消息使用唯一指针**发布（`std::unique_ptr`），避免不必要的拷贝
3. **回调函数保持快速**，耗时操作放入独立线程
4. **合理使用定时器频率**：传感器处理 10-100Hz，控制 20-50Hz，状态发布 1-10Hz
5. **日志使用合适的级别**：INFO（正常运行）、WARN（可恢复问题）、ERROR（严重问题）、DEBUG（调试信息）

#### 通信设计
1. **优先使用 Topic**，其次是 Service，最后才用 Action
2. **为每种通信场景选择正确的 QoS**：传感器用 BEST_EFFORT，地图用 TRANSIENT_LOCAL
3. **使用命名空间**隔离多机器人的话题
4. **避免话题名硬编码**：使用参数和 remapping 使其可配置

### 16.2 常见陷阱

| 陷阱 | 症状 | 解决方法 |
|------|------|----------|
| **混用不同发行版** | CMake/ABI 错误 | 每个终端只用一种发行版 |
| **Source 顺序错误** | "package not found" | 先 source underlay，再 source overlay |
| **QoS 不匹配** | 话题静默无通信 | `ros2 topic info /topic -v` 检查 |
| **忘记 DOMAIN_ID** | 可见同事的幽灵话题 | 设置非零值 |
| **忘记 Inertia** | Gazebo 崩溃 | 所有 link 必须设 `<inertial>` |
| **忘记 source 工作空间** | `ros2 run` 找不到包 | source install/setup.bash |
| **`--symlink-install` 对 C++ 无效** | C++ 修改后不生效 | C++ 仍需 `colcon build` |
| **用 Debug 编译** | 性能差 5-20 倍 | 加 `-DCMAKE_BUILD_TYPE=Release` |
| **Python 包忘记 install 启动文件** | launch 找不到 | 在 setup.py data_files 中注册 |
| **topic hz 极低或为 0** | 发布者未运行或阻塞 | 检查发布者日志、网络连接 |

### 16.3 常用环境变量

| 变量 | 用途 | 示例值 |
|------|------|--------|
| `ROS_DOMAIN_ID` | 网络隔离 ID | `42` |
| `RMW_IMPLEMENTATION` | DDS 实现选择 | `rmw_cyclonedds_cpp` |
| `ROS_LOCALHOST_ONLY` | 仅本地通信 | `1` |
| `RCUTILS_COLORIZED_OUTPUT` | 彩色日志 | `1` |
| `RCUTILS_CONSOLE_OUTPUT_FORMAT` | 日志格式 | `[{severity}] [{time}] [{name}]: {message}` |

### 16.4 `.gitignore` 推荐

```gitignore
# ROS2 工作空间
build/
install/
log/

# Python
__pycache__/
*.pyc

# IDE
.vscode/
.idea/

# colcon test
coverage/
```

---

## 17. 参考资源

### 17.1 官方文档

| 资源 | 链接 |
|------|------|
| **ROS2 官方文档 (Jazzy)** | https://docs.ros.org/en/jazzy/index.html |
| **ROS2 官方教程** | https://docs.ros.org/en/jazzy/Tutorials.html |
| **ROS2 安装指南** | https://docs.ros.org/en/jazzy/Installation.html |
| **Nav2 导航文档** | https://navigation.ros.org/ |
| **SLAM Toolbox** | https://github.com/SteveMacenski/slam_toolbox |
| **Gazebo Sim 文档** | https://gazebosim.org/docs |
| **rosbag2 文档** | https://github.com/ros2/rosbag2 |

### 17.2 推荐书籍（2025-2026）

| 书名 | 特点 |
|------|------|
| *ROS2 from Scratch* (Packt, 2025) | 从零开始，实践导向 |
| *Building Robots with ROS 2* (古月居, 2026) | ROS2 Jazzy + Gazebo，中文 |
| *A Concise Introduction to Robot Programming with ROS2* (2025) | C++ & Python，覆盖 Behavior Trees/Nav2 |
| *ROS2 Projects with AI* (2025) | ROS2 + OpenCV + 深度学习 |

### 17.3 在线社区

| 资源 | 链接 |
|------|------|
| **ROS Answers** | https://answers.ros.org/ |
| **ROS Discourse** | https://discourse.ros.org/ |
| **ROS 2 GitHub** | https://github.com/ros2 |
| **古月居社区** | https://www.guyuehome.com/ |

### 17.4 推荐学习路线

```
第1周：安装 + 核心概念
  ├── 安装 ROS2 Jazzy/Humble
  ├── 理解节点、话题、服务、动作
  ├── 运行 turtlesim 和 demo 节点
  └── 使用 CLI 工具探索系统

第2周：编写代码
  ├── 创建第一个包和节点
  ├── 编写发布者/订阅者（Python + C++）
  ├── 编写服务端/客户端
  └── 编写动作服务器/客户端

第3周：启动与配置
  ├── 使用 Launch 文件管理多节点
  ├── 参数声明、加载和动态更新
  ├── rqt_graph + rqt_console 调试
  └── rosbag2 录制与回放

第4周：建模与仿真
  ├── 使用 URDF/XACRO 建立机器人模型
  ├── RViz2 可视化
  ├── Gazebo 仿真与传感器插件
  └── TF2 坐标变换

第5周：导航与SLAM
  ├── SLAM Toolbox 建图
  ├── Nav2 自主导航
  ├── AMCL 定位
  └── 自定义导航行为

第6周：高级主题
  ├── 生命周期节点
  ├── 节点组合与 IPC
  ├── 自定义消息接口
  ├── QoS 策略调优
  └── 多机器人系统
```

---

> **保持学习，动手实践，构建你的机器人系统！** 🤖
