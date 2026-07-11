# APP TCP 桥接协议（v1）

`car_app_bridge` 在 TCP `8765` 端口提供小车的受控访问接口。协议是 **JSON Lines**：每一行是一条 UTF-8 JSON 对象，服务端也以一行 JSON 响应或推送事件。它不开放任意 ROS topic，以确保 APP 仍然经过 `safety_mux`、速度上限和急停链路。

## 启动与安全

```bash
ros2 launch car_bringup bringup.launch.py use_app_bridge:=true
```

默认监听全部网卡。部署到非隔离网络时，必须将 `src/car_app_bridge/config/app_bridge.yaml` 的 `auth_token` 设为随机、非空值，并限制防火墙访问来源。客户端连接后先收到 `hello`；配置令牌时，先发送：

```json
{"id":"auth-1","cmd":"auth","token":"<auth_token>"}
```

每个正常响应都有相同外层结构：`{"type":"response","ok":true,"cmd":"...","id":"...","data":{...}}`。失败时 `ok` 为 `false` 并带有 `error`。APP 应以 `id` 对应请求和响应，不应依赖响应到达顺序。

## 指令

| `cmd` | 请求数据 | 小车接口 |
| --- | --- | --- |
| `capabilities` | 无 | 查询协议版本、功能、模式、遥测通道、速度限制；APP 应用它构建兼容界面。 |
| `ping` / `status` | 无 | 连通性检查 / 当前模式、原始急停、实际生效急停、雷达、视觉、输出速度、导航状态。 |
| `move` | `linear`, `angular` | 手动速度，发布到 `/cmd_vel_manual`，经过安全仲裁；超过 YAML 上限会被拒绝。 |
| `mode` | `value`: `manual`、`nav`、`vision`、`follow` | 发布 `/mode_select`。 |
| `estop` | `active`: 布尔值 | 发布 `/emergency_stop`。`false` 释放急停。 |
| `nav_goal` | `x`, `y`, 可选 `yaw`、`frame_id` | 发布 `/goal_pose`；若 Nav2 action server 已就绪，也发送 `NavigateToPose`。 |
| `nav_cancel` | 无 | 取消由 APP 桥接提交且已接受的导航目标。 |
| `follow_person` | `track_id`，可选 `activate` | 选择 YOLO 事件中对应的人员 ID；默认切换到 `follow` 模式。 |
| `stop_follow` | 无 | 清除选中人员；若当前为跟随模式，则切回手动模式。 |
| `subscribe` / `unsubscribe` | `channels` 字符串数组 | 订阅或取消订阅遥测。有效通道是 `status`、`lidar`、`vision`、`navigation`。 |

示例：

```json
{"id":"sub-1","cmd":"subscribe","channels":["status","lidar","vision","navigation"]}
{"id":"move-1","cmd":"move","linear":0.15,"angular":0.0}
{"id":"goal-1","cmd":"nav_goal","x":1.2,"y":-0.4,"yaw":1.57}
{"id":"follow-1","cmd":"follow_person","track_id":7}
```

订阅后，服务端会主动发送如 `{"type":"event","channel":"lidar","data":{...}}` 的事件。雷达事件包含避障覆盖和告警状态；视觉事件转发 `/vision/detections` 的结构化检测结果；`status` 中的 `command` 是安全仲裁后的 `/control/cmd_vel`，不是 APP 请求的原始速度。`estop_active` 是 APP/键盘急停话题的原始状态，`effective_estop_active` 是控制仲裁实际执行的停车状态，包含人员近距离停车。

YOLO 人员事件中的 `track_id` 是本次相机跟踪会话内的 ID，APP 应显示它并将其传给 `follow_person`。距离安全状态在 `status.person_safety` 中：仅当深度图与彩色图对齐且新鲜时才会触发人员减速或停车。

## 兼容与扩展

旧的文本指令（`forward`、`back`、`left`、`right`、`stop`、`mode manual`、`estop off`）仍可使用；启用 `auth_token` 后仅允许 JSON 认证和指令。

新增小车功能时，应在 `AppServer._dispatch()` 添加一个明确命名的命令、在 `_capabilities()` 中声明它、通过固定 ROS 接口实现，并为状态创建一个遥测通道或并入 `status`。不要让 APP 直接指定 topic、消息类型或任意参数：这会绕开控制仲裁和速度/权限校验。相机实时视频应使用专门的 WebRTC/MJPEG 视频服务；本 TCP 控制端口只承载控制与轻量状态，避免图像流阻塞急停和操控指令。
