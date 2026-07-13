# APP 车端桥接协议（v3）

`car_app_bridge` 是车端的受控接口层。APP 不属于本仓库的交付范围；APP 只需按本文通过 TCP JSON Lines 调用接口、订阅状态并渲染界面。APP 不得直接发布 ROS topic，也不得直接访问底盘、`/cmd_vel` 或 Nav2 action。

## 1. 连接与报文

- 默认监听：`0.0.0.0:8765`，参数见 [app_bridge.yaml](../src/car_app_bridge/config/app_bridge.yaml)。
- 编码：UTF-8；每行一个完整 JSON 对象，以 `\n` 结束；单行最大 8192 字节。
- 服务端连接后先发送：`{"type":"hello","protocol_version":3,"authentication_required":false}`。
- 请求格式：`{"id":"客户端请求 ID","cmd":"命令名", ...}`。`id` 可选，但 APP 应始终填写并按它关联异步响应。
- 成功响应：`{"type":"response","ok":true,"cmd":"...","id":"...","data":{...}}`。
- 失败响应：`{"type":"response","ok":false,"cmd":"...","id":"...","error":"可读错误信息"}`。
- 主动遥测：`{"type":"event","channel":"...","data":{...}}`。同一 TCP 连接上的响应与事件可交错到达。

设置了非空 `auth_token` 时，除 `auth` 外的 JSON 请求都会被拒绝：

```json
{"id":"auth-1","cmd":"auth","token":"<auth_token>"}
```

生产部署必须设置随机且非空的 `auth_token`，并使用防火墙限制可访问该端口的网段；此 TCP 协议不应直接暴露到互联网。

## 2. 能力查询与遥测

APP 首次连接应调用 `capabilities`，以服务端返回的版本、命令、模式、遥测通道和速度限制为准。当前支持的遥测通道如下：

| 通道 | 内容 | 建议用途 |
| --- | --- | --- |
| `status` | 当前模式、急停、雷达/人身安全、控制输出、导航、位姿、任务、控制租约摘要 | 总览页与安全状态 |
| `lidar` | 避障覆盖、告警状态 | 障碍提示 |
| `vision` | `/vision/detections` 的结构化结果 | 视觉巡检/跟随结果 |
| `navigation` | 直接导航目标的接收、完成、失败状态 | 单点导航页 |
| `pose` | AMCL 位姿、协方差摘要 | 地图上的小车位置 |
| `mission` | 巡检任务进度 | 任务详情页 |
| `inspection` | 单项视觉巡检结论、置信度、人工复核和证据路径 | 任务详情页与人工复核入口 |
| `event` | 巡检状态转换和业务事件 | 任务事件流/审计 |
| `control_lease` | 手动控制租约的持有和失效 | 遥控控制权提示 |
| `runtime` | 运行态状态：`active_profile`、`requested_profile`、`state`、`generation`、`ready`、`message` | 运行态切换跟踪与就绪确认 |

`status` 通道的快照通过嵌套对象 `runtime` 提供运行态摘要，例如
`data.runtime.active_profile`、`data.runtime.state` 和 `data.runtime.ready`。订阅独立的
`runtime` 通道时，这些字段直接位于事件的 `data` 中。

订阅示例：

```json
{"id":"sub-1","cmd":"subscribe","channels":["status","pose","mission","event","control_lease","runtime"]}
```

取消订阅使用同样格式的 `unsubscribe`。`status` 中的 `command` 是安全仲裁后的 `/control/cmd_vel`，并非 APP 原始输入；`effective_estop_active` 才是实际生效的停车状态，包含人员近距急停等来源。

## 3. 运行态管理（v3 新增）

`node_manager` 是车端常驻运行态管理器。底盘、雷达、相机、控制安全链和 APP Bridge
保持为基础层，`mapping`、`navigation`、`mission` 三个任务配置互斥。APP 必须先切换
运行态并等待 `runtime` 就绪，再使用建图、导航或巡逻能力。

### 3.1 状态字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `active_profile` | string | 当前生效的运行态：`idle`、`mapping`、`navigation`、`mission` |
| `requested_profile` | string | APP 请求的目标运行态（切换过程中可能与 `active_profile` 不同） |
| `state` | string | 运行态状态：`IDLE`、`STARTING`、`STOPPING`、`READY`、`FAILED` |
| `generation` | number | 单调递增的切换代数，每次受理新的 `runtime_switch` 时加一 |
| `ready` | boolean | 当前运行态是否已就绪可用 |
| `message` | string | 人类可读的状态描述或失败原因 |

### 3.2 运行态取值与约束

| profile | 说明 | 允许的参数 |
| --- | --- | --- |
| `idle` | 空闲态，仅手动安全控制可用 | 无 |
| `mapping` | SLAM 建图 | 无（不允许传 `map_id`） |
| `navigation` | 单点导航 | `map_id`（必传，指向受管地图） |
| `mission` | 巡检巡逻 | `map_id`（必传）、`use_yolo`（可选，**仅允许**此 profile 使用） |

- `navigation` 和 `mission` **必须**传入 `map_id`，Bridge 按该受管地图 manifest 的 `yaml_file` 解析其 YAML 文件（通常为 `~/.icar/maps/<map_id>/map.yaml`），不接受任意路径。
- `mapping` 和 `idle` **不允许**传入 `map_id`。
- `use_yolo` **仅允许**在 `mission` 中使用。

### 3.3 `runtime_status` 命令

查询当前运行态状态：

```json
{"id":"rt-status-1","cmd":"runtime_status"}
```

成功响应返回完整运行态快照：

```json
{
  "type": "response",
  "ok": true,
  "cmd": "runtime_status",
  "id": "rt-status-1",
  "data": {
    "active_profile": "idle",
    "requested_profile": "idle",
    "state": "IDLE",
    "generation": 3,
    "ready": true,
    "message": ""
  }
}
```

### 3.4 `runtime_switch` 命令

切换运行态：

```json
{"id":"rt-switch-1","cmd":"runtime_switch","profile":"mapping"}
```

```json
{"id":"rt-switch-2","cmd":"runtime_switch","profile":"navigation","map_id":"lab_20260713"}
```

```json
{"id":"rt-switch-3","cmd":"runtime_switch","profile":"mission","map_id":"lab_20260713","use_yolo":false}
```

- 即时响应中的 `"accepted": true` **仅表示管理器已受理**请求，并非切换完成。
- APP **必须**订阅 `runtime` 遥测通道，等待 `state: "READY"` 且 `ready: true`，
  或收到 `state: "FAILED"` 并查看 `message` 获取失败原因。
- 失败时管理器会停止部分启动的任务栈并回落到 `idle`。
- 正在切换时，或请求已经处于 `READY` 的同一 profile 时，管理器会拒绝新的切换请求；APP 应继续等待当前 generation 的终态，而不是重复提交。

### 3.5 切换前置条件

在调用 `runtime_switch` 之前，APP 必须：

1. **取消 APP 发起的导航**：如果存在活跃的直接导航目标，调用 `nav_cancel` 并等待其结束。
2. **取消 APP 发起的巡检**：如果存在运行中的巡检任务，调用 `mission_cancel` 并等待其结束。

人工接管时可先调用 `mission_pause` 并等待 `mission.state=PAUSED`，以便操作员确认后再取消；这是推荐的操作流程，但不是 `runtime_switch` 的强制前置条件。

### 3.6 切换时的安全行为

每次运行态转换时，管理器会：

1. 将模式选择器切到 `manual`（`/mode_select=manual`）。
2. 向 `/cmd_vel_manual` 发布三次零速度命令，确保小车停止。
3. 随后停止旧配置的节点，启动新配置的节点。

**管理器绝不会自动解除急停**。切换不会发布"解除急停"命令；如果急停处于激活状态，
切换后小车仍保持停止。

## 4. 手动接管与安全边界

手动运动使用单客户端租约，默认有效期 1 秒。这样可以防止两个 APP/控制台同时向小车发速度命令。

1. 获取控制权：`{"id":"lease-1","cmd":"teleop_acquire"}`；响应包含 `lease_id` 和 `expires_in_sec`。
2. 使用该 `lease_id` 调用 `move`，每次 `move` 也会续期：

   ```json
   {"id":"move-1","cmd":"move","lease_id":"<lease_id>","linear":0.15,"angular":0.0}
   ```

3. 在操纵杆静止时，APP 应每 300–500 ms 调用 `teleop_heartbeat`；结束时调用 `teleop_release`。
4. 客户端断线、主动释放或超时后，车端立即向 `/cmd_vel_manual` 发布零速度，并广播 `control_lease` 事件。

`linear` 和 `angular` 必须是有限数，绝对值不得超过服务端 `capabilities.limits`。旧文本 `forward/back/left/right` 已禁止；`stop` 仅保留为兼容性零速度命令，新的 APP 应使用带租约的 `move`。

`mode` 接受 `manual`、`nav`、`vision`、`follow`；`estop` 接受布尔字段 `active`。APP 可中途接管，但应先调用 `mission_pause` 并等待 `mission.state=PAUSED`（直接导航则先 `nav_cancel`）；此后 `teleop_acquire` 才会成功，并由车端切换到 `manual`。释放/超时后车端保持零速度和手动模式，必须显式 `mission_resume` 才能恢复自动运动。急停和 `safety_mux` 始终拥有更高优先级。

## 5. 地图接口

地图由 SLAM 建图阶段产生。v3 中通过 `node_manager.launch.py` 统一管理运行态：
先使用 `runtime_switch` 切换到 `mapping` 运行态，等待 `runtime` 遥测报告
`state: READY`，随后即可使用地图相关命令。

如需开机直接进入建图态：

```bash
ros2 launch car_bringup node_manager.launch.py initial_profile:=mapping
```

不要同时启动旧的 `bringup.launch.py` 和 `node_manager.launch.py`，否则控制、雷达或
APP Bridge 会重名并竞争同一硬件。

建图启动时会运行 Nav2 `map_saver_server`，服务名默认 `/map_saver/save_map`。保存成功后，车端在 `~/.icar/maps/<map_id>/` 管理 `map.yaml`、PGM 图像和 `manifest.json`；路线接口只使用 `map_id`，不接受任意文件路径。

| 命令 | 请求字段 | 成功数据 | 说明 |
| --- | --- | --- | --- |
| `map_list` | 无 | `maps` | 返回所有已注册地图的 manifest 摘要 |
| `map_get` | `map_id` | `map` | 返回一个 manifest，不传输 PGM 图像内容 |
| `map_save` | `name` | `saved`, `map` | 调用车端 map saver；仅建图模式且服务处于可用状态时可用 |
| `initial_pose` | `map_id`, `x`, `y`, 可选 `yaw` | 位姿回显 | 向 `/initialpose` 发布 AMCL 初始位姿；APP 必须先在导航端加载同一地图 |

`map_save` 示例：

```json
{"id":"map-save-1","cmd":"map_save","name":"warehouse_floor_1"}
```

manifest 至少包含 `map_id`、`name`、`resolution`、`origin`、`width`、`height`、地图文件名与 SHA-256。地图文件下载/展示不是本 TCP 控制协议的职责；若 APP 需要地图底图，应通过部署侧受鉴权的文件服务或静态资源服务提供只读副本，并按 manifest 中的哈希校验。

## 6. 路线协议

路线是版本化 JSON 对象。保存前车端会同时完成结构校验和静态栅格校验：每个节点必须在该地图范围内，且不能落在占用格或未知格。`valid=true` 仅代表静态检查通过；动态障碍、代价地图膨胀、定位质量和实际 Nav2 可达性仍由运行时导航决定。

| 命令 | 请求字段 | 说明 |
| --- | --- | --- |
| `route_list` | 可选 `map_id` | 返回路线 ID、版本、地图、名称、循环标志和更新时间 |
| `route_get` | `route_id`，可选 `version` | `version` 缺省或为 `0` 时取最新版本 |
| `route_validate` | `route` | 只校验，不写数据库 |
| `route_save` | `route`，可选 `replace` | 校验通过后写入 SQLite；同一 ID/版本默认不可覆盖 |
| `route_delete` | `route_id`，可选 `version` | 不给版本时删除该路线的所有版本 |

路线最小示例：

```json
{
  "id":"route-check-1",
  "cmd":"route_validate",
  "route":{
    "schema_version":1,
    "route_id":"warehouse_a_day",
    "map_id":"warehouse_floor_1_20260711_120000_ab12cd34",
    "name":"仓库 A 白天巡检",
    "version":1,
    "loop":false,
    "checkpoints":[
      {
        "checkpoint_id":"door-01",
        "sequence":1,
        "name":"一号门",
        "type":"checkin",
        "pose":{"frame_id":"map","x":1.20,"y":-0.40,"yaw":1.57},
        "arrival":{"position_tolerance_m":0.30,"yaw_tolerance_rad":0.35,"dwell_sec":1.0,"max_pose_covariance":0.25},
        "checkin":{"method":"visual_marker","marker_type":"qr","expected_marker_id":"ICAR:door-01","timeout_sec":8.0,"retries":1,"confirmation_frames":2},
        "tasks":[],
        "failure_policy":{"navigation":"retry_then_wait_operator","checkin":"retry_then_wait_operator"}
      }
    ]
  }
}
```

限制：`schema_version` 当前必须为 1；`route_id`、`map_id`、`checkpoint_id` 不可为空或包含空白；节点 `sequence` 从 1 连续递增；坐标系必须为 `map`；版本为正整数。`checkin.method` 可为 `none`、`geofence` 或 `visual_marker`；视觉打卡只接受 `qr`、`apriltag`，且必须提供精确的 `expected_marker_id`。`none` 仅为 P3 前路线兼容，任务记录会明确标注 `NOT_REQUIRED`，不能视为物理打卡成功。

`geofence` 依次校验 AMCL 位姿距离、朝向、x/y/yaw 协方差、`/control/cmd_vel` 静止状态和 `dwell_sec`。`visual_marker` 在此基础上要求新的连续 `confirmation_frames` 个相机检测帧完整匹配标记类型与 ID；错误 ID、过期位姿、移动中检测、超时或缺少证据图都会失败。视觉成功时车端写入 `~/.icar/evidence/<mission_id>/<checkpoint_id>/` 的 JPEG 和 JSON 元数据（含 SHA-256）；TCP 不传输该文件的二进制内容。

## 7. 巡检任务接口

车端以 `ExecutePatrol` action 执行路线，以 `/mission/control` 服务实施暂停、继续、取消。TCP 桥将它们封装为以下命令：

| 命令 | 请求字段 | 说明 |
| --- | --- | --- |
| `mission_start` | `route_id`、可选 `route_version`（0=最新）、`start_checkpoint_index`、`loop` | 启动巡检；运行中的巡检或直接导航目标会被拒绝，避免两个 Nav2 客户端争抢路线 |
| `mission_pause` | `mission_id` | 请求暂停 |
| `mission_resume` | `mission_id` | 请求继续 |
| `mission_cancel` | `mission_id` | 请求取消 |
| `mission_checkins` | `mission_id` | 查询已持久化的每次打卡尝试、结果、匹配 ID 和车端证据路径 |
| `mission_inspections` | `mission_id` | 查询每项视觉巡检的结构化结论、置信度、人工复核标记和证据路径 |
| `mission_report` | `mission_id` | 查询任务、打卡、巡检、事件及结论计数的汇总报告 |
| `mission_export` | `mission_id` | 在车端受管理报告目录导出 JSON 和自包含 HTML，返回两个路径 |
| `mission_recoveries` | 无 | 查询因任务管理节点重启而停在 `WAITING_OPERATOR` 的任务，并返回重试当前点/从下一点继续的索引 |

启动示例：

```json
{"id":"mission-1","cmd":"mission_start","route_id":"warehouse_a_day","route_version":1,"start_checkpoint_index":0,"loop":false}
```

`mission_start` 的即时响应仅表示 action 已提交，最终是否被接受和执行进度请订阅 `mission`。任务状态中包含 `mission_id`、路线版本、当前节点、节点总数、进度、重试次数和详情；`event` 记录状态迁移和可审计事件，例如 `CHECKIN_VERIFIED`、`CHECKIN_RETRY`、`CHECKIN_FAILED_CONTINUED`。调用 `mission_checkins` 可获得完整结构化打卡记录。`evidence_path` 是车端受管理路径，只能通过部署方另行提供的受鉴权只读文件服务访问；桥接端口不会接受任意路径读取请求。直接导航 `nav_goal` 与巡检互斥；巡检期间应使用上述任务命令，不应发送 `nav_goal`。

### 7.1 P4 视觉巡检结果

订阅 `inspection` 会在每个 `RunInspection` Action 结束时收到结果；同一结果也会更新到 `status.inspection`。载荷字段为 `mission_id`、`checkpoint_id`、`task_id`、`task_type`、`target`、`conclusion`、`confidence`、`needs_human_review`、`evidence_paths`、`detail_json` 和时间戳。`conclusion` 只可能是 `PRESENT`、`ABSENT`、`ABNORMAL`、`UNKNOWN` 或 `NEEDS_HUMAN_REVIEW`。

APP 必须把 `UNKNOWN` 和 `NEEDS_HUMAN_REVIEW` 显示为待处理，不能替换为“不存在”或“已通过”。`mission_inspections` 返回该任务的持久化明细；`mission_report` 返回以下结构：

```json
{
  "mission": {"mission_id":"...","state":"COMPLETED"},
  "summary": {
    "checkin_attempts": 2,
    "checkin_successes": 2,
    "inspection_count": 1,
    "inspection_successes": 1,
    "needs_human_review_count": 0,
    "inspection_conclusions": {"PRESENT": 1}
  },
  "checkins": [],
  "inspections": [],
  "events": []
}
```

## 8. 直接导航和视觉跟随

| 命令 | 请求字段 | 说明 |
| --- | --- | --- |
| `nav_goal` | `x`, `y`，可选 `yaw`、`frame_id` | 发送单点 Nav2 目标，并自动选择 `nav` 模式；巡检运行时会拒绝 |
| `nav_cancel` | 无 | 取消由此桥接提交的已接受单点导航目标 |
| `follow_person` | `track_id`，可选 `activate` | 选择视觉跟踪 ID，默认切到 `follow` 模式 |
| `stop_follow` | 无 | 清空跟随目标；当前为跟随模式时切回 `manual` |

视觉跟踪 ID 只在本次相机跟踪会话内有效。`status.person_safety` 的减速/急停结果仅在深度和彩色数据时序有效时生效；APP 只能展示并请求操作，不能绕过这条安全链路。

## 9. ROS 接口对应关系（供部署和联调）

| TCP 能力 | 车端 ROS 接口 |
| --- | --- |
| 地图保存 | `nav2_msgs/srv/SaveMap`，默认 `/map_saver/save_map` |
| 初始位姿 / 位姿遥测 | `/initialpose` / `/amcl_pose`（`PoseWithCovarianceStamped`） |
| 路线存储 | `~/.icar/icar.db`，由 `car_mission` 管理 |
| 巡检 | `car_interfaces/action/ExecutePatrol`、`VerifyCheckpoint`、`RunInspection`、`InspectionResult`、`MissionControl`、`/mission/status`、`/mission/event`、`/inspection/result` |
| 手动控制 | `/cmd_vel_manual`，最终由 `safety_mux` 输出 `/control/cmd_vel` |
| 急停 | `/emergency_stop`，实际生效状态为 `/control/effective_estop` |

部署前应执行 `ros2 interface show nav2_msgs/srv/SaveMap`、`ros2 action info /execute_patrol` 和 `ros2 service type /mission/control`，确认目标 Jetson 上的 Nav2/Foxy 接口与本工程依赖一致。完整场景、分期和验收标准见 [复杂巡检场景详细实施方案.md](复杂巡检场景详细实施方案.md)。
