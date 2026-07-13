# Node Manager 使用说明

`node_manager` 是实车的常驻运行态管理器。它把底盘、雷达、相机、控制安全链和
APP Bridge 保持为基础层，只在 `mapping`、`navigation`、`mission` 三个互斥任务
配置之间切换。

## 一次启动

进入 Docker、加载 ROS 环境并编译后，使用下面的入口启动整车：

```bash
ros2 launch car_bringup node_manager.launch.py
```

默认配置启动厂家底盘/雷达、V4L2 彩色相机桥、控制与避障、APP Bridge 和管理器，
运行态为 `idle`。`idle` 中只有手动安全控制可用，不会启动 SLAM、Nav2 或任务节点。

如果需要开机直接进入某个配置，必须显式提供其依赖。例如：

```bash
ros2 launch car_bringup node_manager.launch.py \
  initial_profile:=navigation \
  map:=/root/.icar/maps/lab_20260713/map.yaml
```

不要同时启动旧的 `bringup.launch.py` 和 `node_manager.launch.py`，否则控制、雷达或
APP Bridge 会重名并竞争同一硬件。

## APP 协议

APP Bridge 协议版本为 3，新增：

```json
{"cmd":"runtime_status"}
{"cmd":"runtime_switch","profile":"mapping"}
{"cmd":"runtime_switch","profile":"navigation","map_id":"lab_20260713"}
{"cmd":"runtime_switch","profile":"mission","map_id":"lab_20260713","use_yolo":false}
```

`navigation` 和 `mission` 只接受由 `map_id` 指向的受管地图；Bridge 会将其解析为
`~/.icar/maps/<map_id>/map.yaml`，不会允许 APP 传任意宿主机路径。请求成功仅表示
管理器已受理，APP 应订阅 `runtime` 遥测，等待 `state: READY`。失败时会报告
`state: FAILED` 和原因。

## ROS 接口与安全行为

内部客户端也可使用以下服务：

```bash
ros2 service call /runtime/set_profile car_interfaces/srv/SetRuntimeProfile \
  "{profile: 'mapping', map_path: '', route_file: '', use_yolo: false}"
```

`navigation` 与 `mission` 的 `map_path` 必须是存在的绝对路径；`mission` 还需要一个
存在的路由文件。`/runtime/status` 会发布 `active_profile`、请求的配置、转换代号和
失败信息，并采用 transient-local QoS。

每次转换会先选择 `/mode_select=manual` 并发布三次零速度，随后才停止旧配置和启动新
配置。管理器绝不会发布“解除急停”命令；转换失败时会停止部分启动的任务栈并回落到
`idle`。

## 冒烟测试

新增的独立模块仅验证安全的 `idle → mapping → idle` 转换：

```bash
SMOKE_MODULES=node_manager bash scripts/run_full_system_smoke_test.sh
```

它会启动 `node_manager.launch.py`，确认 APP Bridge 和服务注册，检查 SLAM 与
`/map_saver/save_map` 的就绪，再回到 `idle`。不发布导航目标、速度命令或任务。
