# 上位机控制 APP 设计文档（鸿蒙 ArkTS）

## 1. 设计目标

基于鸿蒙 ArkTS，开发上位机控制 APP，实现手机对小车的遥控、建图导航、雷达功能、视觉追踪等全功能控制。课程要求：基本需求 -> 开发 APP 控制小车运动。

## 2. 技术选型

| 层级 | 技术 |
|------|------|
| 开发语言 | ArkTS（鸿蒙） |
| 开发工具 | DevEco Studio |
| 最低 API | HarmonyOS 3.0+ |
| 网络请求 | @ohos.net.http |
| JSON解析 | 原生 JSON.parse |
| 后端 | Flask + SocketIO（部署在小车 Docker） |
| 通信协议 | HTTP REST API（docs/APP接口文档.md） |

## 3. 页面设计

底部 4 个 Tab 切换：

### Tab1：遥控

- 方向按钮（上下左右四个大按钮）
- 急停红色大按钮
- 模式选择器（手动/导航/视觉/跟随）
- 速度滑块

### Tab2：建图 & 导航

- 开始建图 / 停止建图
- 保存地图
- 开始导航 / 停止导航

### Tab3：雷达 & 视觉

- 避障（开关）
- 跟随（开关）
- 警卫（开关）
- 相机（开关）
- 颜色识别（开关）
- 追踪（开关）

### Tab4：状态

- 当前模式、速度、急停状态
- 运行中节点列表
- 定时 1 秒刷新

## 4. 网络层设计

调用小车 Flask 后端的 HTTP 接口：

```typescript
// 控制指令
http.createHttp().request('http://小车IP:5000/api/cmd', {
  method: http.RequestMethod.POST,
  header: { 'Content-Type': 'application/json' },
  extraData: { type: 'move', linear: 0.15, angular: 0.0 }
})

// 启动进程
http.createHttp().request('http://小车IP:5000/api/process/start', {
  method: http.RequestMethod.POST,
  extraData: { function: 'mapping' }
})

// 获取状态
http.createHttp().request('http://小车IP:5000/api/state', {
  method: http.RequestMethod.GET
})
```

## 5. 项目结构

```
entry/src/main/ets/
  pages/
    Index.ets              # 主页面（底部 Tab 导航）
    RemotePage.ets         # Tab1：遥控
    NavPage.ets            # Tab2：建图 & 导航
    SensorPage.ets         # Tab3：雷达 & 视觉
    StatusPage.ets         # Tab4：状态
  common/
    ApiClient.ets          # HTTP 请求封装
    Constants.ets          # 接口地址、默认值
```

## 6. 通信协议

严格复用 `docs/APP接口文档.md` 已有的 HTTP 接口，ArkTS 端只做网络调用和 UI 展示。
