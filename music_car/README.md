# 音乐小车 — AI 编舞系统

> 让小车随音乐起舞！支持时间轴编舞 + AI 自动生成编舞 + LLM 微调专属模型。

## 目录结构

```
music_car/
├── backend/                          # Python 后端（通用，所有平台共用）
│   ├── __init__.py                   # 模块入口
│   ├── models.py                     # 数据模型（DanceMove, DanceRoutine...）
│   ├── validate_routine.py           # 编舞校验与自动修正
│   ├── choreographer_prompt.txt      # LLM System Prompt
│   ├── llm_choreographer.py          # LLM 编舞引擎（支持 DeepSeek/Qwen/OpenAI/本地）
│   ├── api.py                        # Flask Blueprint（挂接到现有 app_server）
│   ├── augment_data.py               # 数据增强（训练数据生成）
│   └── train_choreographer.py        # LoRA 微调脚本
│
├── android/                          # Android 前端（Kotlin + Jetpack Compose）
│   └── app/src/main/java/com/icar/musiccar/
│       ├── models/DanceModels.kt     # 数据模型
│       ├── network/                  # 网络层
│       │   ├── ApiClient.kt          # HTTP 客户端（OkHttp）
│       │   ├── StateSocket.kt        # WebSocket 状态推送
│       │   └── AIChoreographer.kt    # AI 编舞 HTTP 客户端
│       ├── engine/                   # 编舞引擎
│       │   ├── DanceEngine.kt        # 时间轴编舞引擎（20Hz）
│       │   └── BeatEngine.kt         # 节拍驱动引擎 + 动作模板
│       ├── data/DanceRoutines.kt     # 预置编舞数据（3首）
│       ├── ui/MusicCarScreen.kt      # 主页面（Jetpack Compose）
│       └── AppConstants.kt           # 常量配置
│
├── ios/                              # iOS 前端（Swift + SwiftUI）
│   └── MusicCar/
│       ├── Models/DanceModels.swift  # 数据模型
│       ├── Network/                  # 网络层
│       │   ├── ApiClient.swift       # HTTP 客户端（URLSession）
│       │   ├── StateSocket.swift     # WebSocket 状态推送
│       │   └── AIChoreographer.swift # AI 编舞 HTTP 客户端
│       ├── Engine/                   # 编舞引擎
│       │   ├── DanceEngine.swift     # 时间轴编舞引擎（20Hz）
│       │   └── BeatEngine.swift      # 节拍驱动引擎 + 动作模板
│       ├── Data/DanceRoutines.swift  # 预置编舞数据（3首）
│       ├── UI/MusicCarView.swift     # 主页面（SwiftUI）
│       └── AppConstants.swift        # 常量配置
│
├── frontend/                         # [已废弃] ArkTS 前端（鸿蒙 APP）
│   └── ... (保留作为参考，不再维护)
│
├── data/                             # 训练数据（后续生成）
│   └── README.md                     # 数据格式说明
│
└── README.md                         # 本文件
```

## 快速开始

### 1. 后端集成（小车端）

在现有的 `app_server.py` 中挂载音乐小车蓝图：

```python
# app_server.py 末尾添加：
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../music_car/backend'))
from music_car.backend.api import music_car_bp
app.register_blueprint(music_car_bp)
```

设置环境变量：

```bash
export LLM_BACKEND=deepseek           # 或 qwen / openai / local
export DEEPSEEK_API_KEY=sk-xxxx       # DeepSeek API Key
```

### 2. 前端集成

#### Android（Kotlin + Jetpack Compose）

将 `music_car/android/app/src/main/java/com/icar/musiccar/` 目录复制到 Android 工程：

```
app/src/main/java/com/icar/musiccar/
├── models/DanceModels.kt
├── network/ApiClient.kt, StateSocket.kt, AIChoreographer.kt
├── engine/DanceEngine.kt, BeatEngine.kt
├── data/DanceRoutines.kt
├── ui/MusicCarScreen.kt
└── AppConstants.kt
```

**依赖**（`build.gradle.kts`）：

```kotlin
dependencies {
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.0")
    implementation("androidx.compose.material3:material3")
}
```

在 `MainActivity.kt` 中使用：

```kotlin
setContent {
    MusicCarScreen()
}
```

#### iOS（Swift + SwiftUI）

将 `music_car/ios/MusicCar/` 目录拖入 Xcode 工程。

**系统要求**：iOS 15.0+（使用 Swift Concurrency 的 `async/await`）

在 `App.swift` 入口中使用：

```swift
@main
struct MusicCarApp: App {
    var body: some Scene {
        WindowGroup {
            MusicCarView()
        }
    }
}
```

### 3. 测试流程

```bash
# 1. 启动小车后端
ros2 launch car_app_bridge app_bridge.launch.py

# 2. 测试 API
curl -X POST http://localhost:5000/api/choreograph/generate \
  -H "Content-Type: application/json" \
  -d '{"song":"小苹果","bpm":125,"durationMs":60000,"style":"欢快"}'

# 3. Android/iOS APP 端打开音乐小车页面，点击生成/播放
```

## 平台对照

| 文件 | Android (Kotlin) | iOS (Swift) | 鸿蒙 (ArkTS) |
|------|-----------------|-------------|-------------|
| 数据模型 | `models/DanceModels.kt` | `Models/DanceModels.swift` | `DanceModels.ets` |
| HTTP 客户端 | `network/ApiClient.kt` | `Network/ApiClient.swift` | `ApiClient.ets` |
| WebSocket | `network/StateSocket.kt` | `Network/StateSocket.swift` | `StateSocket.ets` |
| AI 编舞 | `network/AIChoreographer.kt` | `Network/AIChoreographer.swift` | `AIChoreographer.ets` |
| 时间轴引擎 | `engine/DanceEngine.kt` | `Engine/DanceEngine.swift` | `DanceEngine.ets` |
| 节拍引擎 | `engine/BeatEngine.kt` | `Engine/BeatEngine.swift` | `BeatEngine.ets` |
| 预置编舞 | `data/DanceRoutines.kt` | `Data/DanceRoutines.swift` | `DanceRoutines.ets` |
| 主页面 | `ui/MusicCarScreen.kt` | `UI/MusicCarView.swift` | `MusicCarPage.ets` |
| 常量配置 | `AppConstants.kt` | `AppConstants.swift` | `AppConstants.ets` |

> **注意**：鸿蒙 `frontend/` 目录已废弃，保留作为历史参考，不再维护。后续开发请使用 Android/iOS 版本。

## 两种编舞模式

| 模式 | 引擎 | 适用场景 |
|------|------|----------|
| **时间轴** | `DanceEngine` | 预设编舞，每毫秒精确控制 |
| **节拍驱动** | `BeatEngine` | 循环模板，适配任意同 BPM 歌曲 |

## AI 编舞接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/choreograph/generate` | POST | AI 生成编舞 |
| `/api/choreograph/refine` | POST | AI 微调编舞 |
| `/api/choreograph/validate` | POST | 校验合法性 |
| `/api/choreograph/prompt` | GET | 查看 System Prompt |

## 微调流程

```bash
# 1. 用 LLM API 批量生成训练数据（或手写 3-5 首）
# 2. 数据增强
python augment_data.py ./data/original/ ./data/augmented/ 20

# 3. LoRA 微调（需要 GPU）
python train_choreographer.py \
  --data_dir ./data/augmented/ \
  --output_dir ./choreographer-lora \
  --model Qwen/Qwen2.5-1.5B-Instruct \
  --epochs 3

# 4. 部署本地推理
ollama create choreographer -f Modelfile
```

## 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `LLM_BACKEND` | LLM 后端类型 | `deepseek` / `qwen` / `openai` / `local` |
| `LLM_MODEL` | 模型名（覆盖默认值） | `deepseek-chat` |
| `LLM_BASE_URL` | 自定义 API 地址 | `http://localhost:11434/v1` |
| `LLM_API_KEY` | API 密钥 | `sk-xxxx` |
| `DEEPSEEK_API_KEY` | DeepSeek 专用 | `sk-xxxx` |
