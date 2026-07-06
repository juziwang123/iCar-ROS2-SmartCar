# 基于 iCar 智能小车的 ROS2 多传感器巡检与自主导航系统

> 北交大 2026 暑期实训项目组
>
> 项目周期：2026.07.06 – 2026.07.15

---

## 一、项目概述

### 1.1 项目目标

基于 **Yahboom iCar 智能小车**（Jetson Orin Nano），利用 ROS2 实现以下核心功能：

1. **远程连接与控制** — NoMachine 远程桌面 + 键盘/APP 遥控小车
2. **激光雷达感知** — 雷达避障、目标跟随、区域警卫
3. **SLAM 建图** — 激光雷达扫描建图，保存场地地图
4. **自主导航** — DWA/TEB 路径规划，多目标点自动巡航
5. **视觉识别与追踪** — 深度相机 + OpenCV/YOLO 实现目标检测与追踪
6. **APP 上位机控制** — 手机 APP 遥控小车，显示实时画面

### 1.2 硬件平台

| 组件 | 型号 |
|------|------|
| 主控 | Jetson Orin Nano |
| 底盘 | AT32 控制板 + 麦克纳姆轮 |
| 激光雷达 | 思岚 A1（RPLIDAR） |
| 深度相机 | AstraProPlus（RGB-D） |
| 环境感知 | 温湿度、IMU 等传感器 |

### 1.3 软件环境

| 环境 | 系统 | ROS2 版本 | 用途 |
|------|------|-----------|------|
| 本地开发 | Windows 11 + WSL2 Ubuntu 22.04 | Humble | 代码编写、仿真测试 |
| 实车运行 | Jetson Ubuntu 20.04 + Docker | Foxy（小车预置） | 实车部署与运行 |

> **重要**：Foxy 和 Humble 不要混在同一个工作空间。实车以小车预置 Docker/Foxy 环境为准；本地学习和仿真以 Humble 为准。本仓库代码在 Humble 下开发，部署到小车时需适配。

---

## 二、快速开始

### 2.1 本地开发环境搭建（WSL Ubuntu 22.04 + ROS2 Humble）

参考 ROS2 Humble 官方安装文档与课程资料，核心步骤如下：

```bash
# 1. 设置 locale
sudo apt update && sudo apt install locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8

# 2. 添加 ROS2 源
sudo apt install software-properties-common curl -y
sudo add-apt-repository universe
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
  http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | \
  sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# 3. 安装 ROS2 Humble
sudo apt update && sudo apt upgrade -y
sudo apt install ros-humble-desktop ros-dev-tools -y
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc

# 4. 创建工作空间
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws && colcon build
echo "source ~/ros2_ws/install/setup.bash" >> ~/.bashrc

# 5. 克隆本项目
cd ~/ros2_ws/src
git clone git@github.com:juziwang123/iCar-ROS2-SmartCar.git .
cd ~/ros2_ws && colcon build
```

### 2.2 仿真环境安装

```bash
cd ~/ros2_ws/src
git clone https://github.com/6-robot/wpr_simulation2.git
# 国内镜像: git clone https://gitee.com/s-robot/wpr_simulation2.git
cd wpr_simulation2/scripts/
./install_for_humble.sh
cd ~/ros2_ws && colcon build
```

### 2.3 小车连接

```bash
# 1. 小车连接热点 ohcar（密码: 88888888）
# 2. 获取小车实际 IP 后 SSH 登录
ssh jetson@<小车实际IP>
# 密码: yahboom

# 3. 小车上安装 NoMachine（ARM64 版）
wget https://download.nomachine.com/download/8.14/Arm/nomachine_8.14.2_1_arm64.deb
sudo dpkg -i nomachine_*.deb

# 4. Windows 用 NoMachine 客户端连接小车桌面
```

---

## 三、项目规划目录结构

以下目录树描述的是本项目的目标形态，用于指导后续功能包实现和文档组织；当前仓库仍处于脚手架与文档先行阶段，部分文件尚未创建。

```
ros2_ws/
├── src/                              # 所有 ROS2 功能包（本仓库核心代码）
│   ├── car_bringup/                  # 启动与配置
│   │   ├── launch/
│   │   │   └── bringup.launch.py         # 一键启动所有基础节点
│   │   ├── config/
│   │   │   └── params.yaml               # 全局参数配置
│   │   ├── car_bringup/
│   │   │   └── __init__.py
│   │   ├── setup.py
│   │   └── package.xml
│   │
│   ├── car_control/                  # 底盘运动控制
│   │   ├── launch/
│   │   │   └── control.launch.py
│   │   ├── car_control/
│   │   │   ├── __init__.py
│   │   │   ├── motion_controller.py      # 封装运动接口（前进/后退/平移/旋转/停止）
│   │   │   └── keyboard_teleop.py        # 键盘遥控节点
│   │   ├── setup.py
│   │   └── package.xml
│   │
│   ├── car_lidar/                    # 激光雷达感知
│   │   ├── launch/
│   │   │   └── lidar.launch.py
│   │   ├── car_lidar/
│   │   │   ├── __init__.py
│   │   │   ├── avoidance.py              # 雷达避障：前方障碍物停止/绕行
│   │   │   ├── tracker.py                # 雷达跟随：保持固定距离跟踪目标
│   │   │   └── warning.py                # 雷达警卫：检测入侵范围并告警
│   │   ├── setup.py
│   │   └── package.xml
│   │
│   ├── car_vision/                   # 视觉识别与目标追踪
│   │   ├── launch/
│   │   │   └── vision.launch.py
│   │   ├── car_vision/
│   │   │   ├── __init__.py
│   │   │   ├── color_detector.py         # HSV 颜色检测
│   │   │   ├── color_tracker.py          # 颜色追踪 + 底盘联动
│   │   │   └── yolo_detector.py          # YOLO 目标检测（进阶）
│   │   ├── models/                       # 训练好的 YOLO 模型
│   │   ├── setup.py
│   │   └── package.xml
│   │
│   ├── car_navigation/               # SLAM 建图与自主导航
│   │   ├── launch/
│   │   │   ├── mapping.launch.py         # 建图模式
│   │   │   ├── navigation.launch.py      # 导航模式
│   │   │   └── patrol.launch.py          # 多点巡航
│   │   ├── car_navigation/
│   │   │   ├── __init__.py
│   │   │   ├── waypoint_patrol.py        # 多点巡航节点
│   │   │   └── goal_publisher.py         # 发布导航目标点
│   │   ├── maps/                         # 保存的地图文件
│   │   │   ├── lab_map.pgm
│   │   │   └── lab_map.yaml
│   │   ├── config/
│   │   │   ├── nav2_params.yaml
│   │   │   └── dwa_params.yaml
│   │   ├── setup.py
│   │   └── package.xml
│   │
│   └── car_app_bridge/               # APP 上位机通信桥接
│       ├── launch/
│       │   └── app_bridge.launch.py
│       ├── car_app_bridge/
│       │   ├── __init__.py
│       │   └── app_server.py             # APP 指令 → ROS2 topic 转换
│       ├── setup.py
│       └── package.xml
│
├── docs/                             # 项目文档
│   ├── 需求分析报告.md
│   ├── 项目开发报告.md
│   ├── 设计文档.md
│   ├── 测试报告.md
│   ├── 使用手册.md
│   ├── 代码质量保证方案.md
│   ├── 提交规范与交付清单.md
│   ├── 项目分工与任务清单.md
│   ├── 拓展功能实施方案.md
│   └── 日报/                             # 每日开发记录
│       ├── 7月6日_日报.md
│       └── ...
│
├── scripts/                          # 工具脚本
│   ├── install_deps.sh                   # 一键安装所有依赖
│   └── deploy_to_car.sh                  # scp 部署代码到小车
│
├── tests/                            # 测试脚本
│   ├── test_basic_motion.py              # 底盘运动测试
│   ├── test_lidar_avoidance.py           # 雷达避障逻辑测试
│   └── test_vision_tracker.py            # 视觉追踪测试
│
├── .gitignore                        # Git 忽略规则
└── README.md                         # 本文件
```

---

## 四、ROS2 通信架构

### 4.1 核心 Topic 一览

| Topic | 消息类型 | 方向 | 说明 |
|-------|----------|------|------|
| `/cmd_vel` | `geometry_msgs/Twist` | 发布 → 底盘 | 控制小车线速度和角速度 |
| `/scan` | `sensor_msgs/LaserScan` | 雷达 → 订阅 | 激光雷达距离数据 |
| `/camera/color/image_raw` | `sensor_msgs/Image` | 相机 → 订阅 | RGB 彩色图像 |
| `/camera/depth/image_raw` | `sensor_msgs/Image` | 相机 → 订阅 | 深度图像 |
| `/map` | `nav_msgs/OccupancyGrid` | SLAM → 订阅 | 占据栅格地图 |
| `/odom` | `nav_msgs/Odometry` | 底盘 → 订阅 | 里程计数据 |
| `/tf` | `tf2_msgs/TFMessage` | 多节点 → 订阅 | 坐标系变换 |
| `/goal_pose` | `geometry_msgs/PoseStamped` | 发布 → Nav2 | 导航目标点位姿 |
| `/target_pose` | `geometry_msgs/PoseStamped` | 视觉模块发布 | 检测到的目标位置 |

### 4.2 模块数据流

```
                    ┌──────────────────────────────┐
                    │        car_app_bridge          │
                    │   (APP/键盘 → /cmd_vel)        │
                    └──────────────┬─────────────────┘
                                   │ /cmd_vel
                    ┌──────────────▼─────────────────┐
                    │         car_control             │
                    │   运动接口封装 → 底盘驱动        │
                    └──────────────▲─────────────────┘
                                   │ /cmd_vel（修改后）
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
┌─────────▼────────┐  ┌────────────▼───────────┐  ┌────────▼─────────┐
│    car_lidar     │  │      car_vision         │  │  car_navigation  │
│  /scan 数据处理  │  │  /camera 图像处理       │  │  SLAM + Nav2     │
│  避障/跟随/警卫  │  │  颜色追踪/YOLO检测      │  │  多点巡航        │
└──────────────────┘  └─────────────────────────┘  └──────────────────┘
```

### 4.3 控制逻辑优先级

```
急停指令（最高优先级）
    ↓
雷达避障（安全优先：前方 < 0.5m 强制停止/转向）
    ↓
视觉追踪（目标跟随请求）
    ↓
导航目标点（自主巡航）
    ↓
手动遥控（APP/键盘，最低优先级，可被上面覆盖）
```

---

## 五、开发流程

### 5.1 日常开发循环

```bash
# 1. 写代码
cd ~/ros2_ws/src/car_xxx/car_xxx/
# 编辑 .py 文件...

# 2. 编译
cd ~/ros2_ws
colcon build --packages-select car_xxx

# 3. 加载环境
source install/setup.bash

# 4. 运行测试
ros2 run car_xxx node_name

# 5. 提交代码
git add -A && git commit -m "描述做了什么" && git push
```

### 5.2 部署到小车

```bash
# 方式一：scp 传输源码
scp -r ~/ros2_ws/src/car_xxx jetson@<小车实际IP>:~/ros2_ws/src/

# 方式二：小车 git pull
ssh jetson@<小车实际IP>
cd ~/ros2_ws/src && git pull

# 在小车上编译
ssh jetson@<小车实际IP>
cd ~/ros2_ws && colcon build
```

### 5.3 分布式测试（WSL + 小车同网）

```bash
# 两端设置相同的 ROS_DOMAIN_ID
# WSL:
export ROS_DOMAIN_ID=42

# 小车:
export ROS_DOMAIN_ID=42

# 此时两边的 topic 可以互相发现，仿真节点和实车节点可以混跑
```

---

## 六、小车常用命令速查

### 6.1 厂家预置节点

```bash
# 底盘驱动（必须先启动）
ros2 run icar_bringup Mcnamu_driver_X3

# 激光雷达
ros2 launch sllidar_ros2 sllidar_launch.py

# 深度相机
ros2 launch astra_camera astra.launch.xml

# 雷达避障/跟随/警卫
ros2 run icar_laser laser_Avoidance_a1_X3
ros2 run icar_laser laser_Tracker_a1_X3
ros2 run icar_laser laser_Warning_a1_X3

# 颜色检测/追踪
ros2 run icar_astra colorHSV
ros2 run icar_astra colorTracker

# 键盘控制
ros2 run yahboomcar_ctrl yahboom_keyboard
```

### 6.2 SLAM 建图流程

```bash
# 1. 启动建图
ros2 launch yahboomcar_nav map_gmapping_launch.py

# 2. 显示地图（RViz）
ros2 launch yahboomcar_nav display_map_launch.py

# 3. 键盘遥控小车扫描场地
ros2 run yahboomcar_ctrl yahboom_keyboard

# 4. 保存地图
ros2 launch yahboomcar_nav save_map_launch.py
```

### 6.3 自主导航流程

```bash
# 1. 启动导航基础节点
ros2 launch yahboomcar_nav laser_bringup_launch.py

# 2. 启动导航显示
ros2 launch yahboomcar_nav display_nav_launch.py

# 3. 启动路径规划（二选一）
ros2 launch yahboomcar_nav navigation_dwa_launch.py   # DWA 局部规划
ros2 launch yahboomcar_nav navigation_teb_launch.py   # TEB 局部规划

# 4. 在 RViz 中设置初始位姿 + 目标点
```

---

## 七、Git 工作流

### 7.1 分支策略

```
main           ← 稳定版本（答辩用）
  └── develop  ← 开发分支，每日合并
        ├── feature/car_control    ← 控制负责人
        ├── feature/car_lidar      ← 雷达负责人
        ├── feature/car_vision     ← 视觉负责人
        ├── feature/car_nav        ← 导航负责人
        └── feature/car_app        ← APP 负责人
```

### 7.2 提交规范

```
feat(car_control): 添加键盘遥控节点
fix(car_lidar): 修复避障阈值计算错误
docs: 更新 README 安装步骤
test(car_vision): 添加颜色检测单元测试
```

---

## 八、时间计划

| 日期 | 任务 | 里程碑 |
|------|------|--------|
| 7/06 | 环境搭建、远程连接小车、仓库初始化 | 小车可远程连接 |
| 7/07 | 工作空间搭建、仿真跑通、底盘控制测试 | 底盘可遥控 |
| 7/08 | 雷达驱动、避障/跟随/警卫 | 雷达感知完成 |
| 7/09 | 相机启动、OpenCV 颜色追踪、YOLO 探索 | 视觉模块初步 |
| 7/10 | SLAM 建图、保存地图、中期 PPT 准备 | 建图完成 |
| 7/11 | **中期检查** | 展示四项基础功能 |
| 7/12 | 自主导航 DWA/TEB、多点巡航 | 导航完成 |
| 7/13 | 视觉检测联动、APP 控制展示 | 视觉+APP 完成 |
| 7/14 | 系统联调、录制演示视频、整理文档 | 全部文档就绪 |
| 7/15 | **最终答辩** | 全功能演示 |

---

## 九、关键注意事项

1. **不要提交 `build/` `install/` `log/`** — 已在 `.gitignore` 中排除
2. **小车厂家驱动不用放入本仓库** — 小车 Jetson 上预置了，本仓库只放自己写的包
3. **ROS2 版本隔离** — 小车用 Foxy（Ubuntu 20.04），WSL 用 Humble（22.04），API 基本兼容但不要混 workspace
4. **硬件安全** — 底盘测试务必先悬空四轮，确认方向正确后再落地；速度先调低
5. **每日提交日报** — 放在 `docs/日报/` 目录下，每人每天一份
6. **小车热点** — WiFi 名称 `ohcar`，密码 `88888888`

---

## 十、参考资料

| 资料 | 路径/链接 |
|------|-----------|
| ROS2 安装与架构笔记 | `docs/第2章_ROS2安装与系统架构_笔记.md` |
| 智能小车使用手册 | 随车附带 PDF |
| ROS2 Humble 官方文档 | https://docs.ros.org/en/humble/ |
| wpr_simulation2 仿真 | https://github.com/6-robot/wpr_simulation2 |
| NoMachine 下载 | https://www.nomachine.com/download |
