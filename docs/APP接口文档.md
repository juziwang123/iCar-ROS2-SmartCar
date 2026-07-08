# 手机 APP 接口文档

## 1. 概述

| 项目 | 说明 |
|------|------|
| 后端 | Flask + Flask-SocketIO，部署在小车 Docker 容器 |
| 通信方式 | HTTP REST API（控制指令）+ WebSocket（实时状态推送） |
| 端口 | 5000 |
| 访问地址 | `http://<小车IP>:5000` |

## 2. HTTP 接口

### 2.1 获取系统状态

```
GET /api/state
```

**响应：**

```json
{
  "mode": "manual",
  "estop": false,
  "linear_x": 0.0,
  "angular_z": 0.0,
  "running_nodes": ["/safety_mux", "/motion_controller"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| mode | string | manual / nav / vision / follow |
| estop | bool | 急停状态 |
| linear_x | float | 当前线速度 m/s |
| angular_z | float | 当前角速度 rad/s |
| running_nodes | list | 正在运行的节点名 |

### 2.2 发送控制指令

```
POST /api/cmd
Content-Type: application/json
```

**请求体（按 type 区分）：**

#### 运动控制

```json
{"type": "move", "linear": 0.2, "angular": 0.0}
```

| 字段 | 类型 | 范围 | 说明 |
|------|------|------|------|
| linear | float | -0.5 ~ 0.5 | 线速度 m/s |
| angular | float | -1.0 ~ 1.0 | 角速度 rad/s |

#### 停车

```json
{"type": "stop"}
```

#### 模式切换

```json
{"type": "mode", "mode": "nav"}
```

mode 可选值：`manual` / `nav` / `vision` / `follow`

#### 急停

```json
{"type": "estop", "active": true}
```

**所有请求响应：**

```json
{"ok": true}
```

### 2.3 进程管理——启动节点

```
POST /api/process/start
Content-Type: application/json
```

```json
{"function": "mapping"}
```

function 可选值及对应命令：

| function | 实际命令 | 说明 |
|----------|---------|------|
| mapping | ros2 launch yahboomcar_nav map_gmapping_launch.py | 启动建图 |
| mapping_display | ros2 launch yahboomcar_nav display_map_launch.py | 显示地图 |
| save_map | ros2 launch yahboomcar_nav save_map_launch.py | 保存地图 |
| nav_bringup | ros2 launch yahboomcar_nav laser_bringup_launch.py | 导航基础 |
| nav_display | ros2 launch yahboomcar_nav display_nav_launch.py | 导航显示 |
| nav_dwa | ros2 launch yahboomcar_nav navigation_dwa_launch.py | DWA 导航 |
| nav_teb | ros2 launch yahboomcar_nav navigation_teb_launch.py | TEB 导航 |
| avoidance | ros2 run icar_laser laser_Avoidance_a1_X3 | 雷达避障 |
| tracker | ros2 run icar_laser laser_Tracker_a1_X3 | 雷达跟随 |
| guard | ros2 run icar_laser laser_Warning_a1_X3 | 雷达警卫 |
| camera | ros2 launch astra_camera astra.launch.xml | 启动相机 |
| color_detect | ros2 run icar_astra colorHSV | HSV 识别 |
| color_track | ros2 run icar_astra colorTracker | 颜色追踪 |
| chassis | ros2 run icar_bringup Mcnamu_driver_X3 | 底盘驱动 |
| lidar | ros2 launch sllidar_ros2 sllidar_launch.py | 雷达驱动 |

**响应：**

```json
{"ok": true, "pid": 12345}
```

### 2.4 进程管理——停止节点

```
POST /api/process/stop
Content-Type: application/json
```

```json
{"function": "mapping"}
```

**响应：**

```json
{"ok": true}
```

## 3. WebSocket 接口

### 3.1 连接

```
ws://<小车IP>:5000/socket.io/
```

### 3.2 手机 → 服务器（事件名：cmd）

消息格式与 HTTP `POST /api/cmd` 完全一致：

```json
{"type": "move", "linear": 0.2, "angular": 0.0}
{"type": "stop"}
{"type": "mode", "mode": "nav"}
{"type": "estop", "active": true}
```

### 3.3 服务器 → 手机（事件名：state）

每 0.2 秒自动推送：

```json
{
  "mode": "manual",
  "estop": false,
  "linear_x": 0.15,
  "angular_z": 0.0
}
```

## 4. ROS2 话题映射

APP 后端作为 ROS2 节点，对接以下话题：

| 话题 | 消息类型 | 方向 | 请求触发方式 |
|------|---------|------|-------------|
| /cmd_vel_manual | Twist | 发布 | move/stop 指令 |
| /mode_select | String | 发布 | mode 指令 |
| /emergency_stop | Bool | 发布 | estop 指令 |
| /goal_pose | PoseStamped | 发布 | 导航目标点 |
| /odom | Odometry | 订阅 | 实时速度显示 |

## 5. 错误处理

| 场景 | HTTP 状态码 | 响应 |
|------|-----------|------|
| 正常 | 200 | `{"ok": true}` |
| 未知 type | 400 | `{"ok": false, "error": "unknown type: xxx"}` |
| 缺失必填字段 | 400 | `{"ok": false, "error": "missing field: linear"}` |
| 进程启失败 | 500 | `{"ok": false, "error": "process start failed: ..."}` |

## 6. 安全约束

| 规则 | 说明 |
|------|------|
| 速度上限 | linear 不超过 0.5 m/s，angular 不超过 1.0 rad/s |
| 急停优先 | estop=true 时忽略所有 move 指令 |
| 串行控制 | 同一 function 不允许重复启动 |
| 超时停车 | WebSocket 断开 3 秒后自动停车 |
