/**
 * 音乐小车 — 数据模型（iOS / Swift）
 */

import Foundation

// ── 动作类型 ──────────────────────────────

struct MoveType {
    static let move = "move"
    static let stop = "stop"
    static let spin = "spin"
    static let pause = "pause"
}

// ── 节拍标记 ──────────────────────────────

struct BeatTag {
    static let beat = "beat"
    static let strongBeat = "strong_beat"
    static let fill = "fill"
    static let breakTag = "break"
}

// ── 单个舞蹈动作 ──────────────────────────

struct DanceMove: Codable, Identifiable {
    /// 触发时间（毫秒，从歌曲开始计算）
    let timestamp: Int64
    /// 动作类型
    let type: String
    /// 线速度 m/s
    var linear: Double = 0.0
    /// 角速度 rad/s
    var angular: Double = 0.0
    /// 持续时间 ms（0=瞬时）
    var duration: Int64 = 0
    /// 节拍标记
    var tag: String? = nil
    
    var id: Int64 { timestamp }
}

// ── 完整编舞 ──────────────────────────────

struct DanceRoutine: Codable, Identifiable {
    /// 编舞名称
    let name: String
    /// 歌曲文件名
    let song: String
    /// BPM
    let bpm: Int
    /// 总时长（毫秒）
    let duration: Int64
    /// 空间需求
    let spaceRequired: String
    /// 动作序列（按 timestamp 升序）
    let moves: [DanceMove]
    
    var id: String { name }
}

// ── AI 编舞请求 ───────────────────────────

struct ChoreographRequest: Codable {
    let song: String
    let bpm: Int
    let durationMs: Int64
    let style: String
    let space: String
    var extraRequirements: String? = nil
}

// ── AI 编舞响应 ───────────────────────────

struct ChoreographResponse: Codable {
    let ok: Bool
    var routine: DanceRoutine? = nil
    var warnings: [String]? = nil
    var error: String? = nil
    var backend: String? = nil
}

// ── 控制指令 ──────────────────────────────

struct CmdRequest: Codable {
    let type: String
    var linear: Double? = nil
    var angular: Double? = nil
    var mode: String? = nil
    var active: Bool? = nil
}

// ── API 响应 ──────────────────────────────

struct ApiResponse: Codable {
    let ok: Bool
    var error: String? = nil
    var pid: Int? = nil
}

// ── 小车状态 ──────────────────────────────

struct CarState: Codable {
    let linear_x: Double
    let angular_z: Double
    let estop: Bool
    let mode: String
    var running_nodes: [String] = []
}

// ── 常用常量 ──────────────────────────────

let MOVE_TYPE_NAMES: [String: String] = [
    MoveType.move: "移动",
    MoveType.stop: "停止",
    MoveType.spin: "旋转",
    MoveType.pause: "暂停"
]

let MOVE_TYPE_ICONS: [String: String] = [
    MoveType.move: "🏃",
    MoveType.stop: "🛑",
    MoveType.spin: "🔄",
    MoveType.pause: "⏸️"
]

let STYLE_OPTIONS: [String] = [
    "欢快活泼", "优雅古典", "劲爆动感", "温柔舒缓",
    "科技未来感", "可爱萌系", "黑暗神秘"
]

let SPACE_OPTIONS: [String] = [
    "1m×1m", "2m×2m", "2m×3m", "3m×3m"
]
