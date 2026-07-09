/**
 * 应用常量配置（iOS / Swift）
 */

import Foundation

// ── 网络配置 ──────────────────────────────────────

struct AppConstants {
    /// 默认小车 IP
    static let defaultCarIP = "192.168.1.1"
    /// 默认小车端口
    static let defaultCarPort = 5000
    /// HTTP 默认超时 (秒)
    static let httpTimeout: TimeInterval = 3.0
    /// LLM 请求超时 (秒)
    static let llmTimeout: TimeInterval = 35.0
}

// ── 控制模式 ──────────────────────────────────────

enum CtrlMode: String {
    case manual = "manual"
    case nav = "nav"
    case vision = "vision"
    case follow = "follow"
}

let CTRL_MODE_NAMES: [String: String] = [
    "manual": "手动遥控",
    "nav": "自动导航",
    "vision": "视觉追踪",
    "follow": "雷达跟随"
]

// ── 功能节点 ──────────────────────────────────────

struct FunctionNode: Identifiable {
    let key: String
    let name: String
    let category: String
    var requiresChassis: Bool = false
    
    var id: String { key }
}

let FUNCTION_NODES: [FunctionNode] = [
    // 基础控制
    FunctionNode(key: "chassis", name: "底盘驱动", category: "基础控制"),
    FunctionNode(key: "lidar", name: "激光雷达", category: "基础控制", requiresChassis: true),
    
    // 雷达功能
    FunctionNode(key: "avoidance", name: "雷达避障", category: "雷达", requiresChassis: true),
    FunctionNode(key: "tracker", name: "雷达跟随", category: "雷达", requiresChassis: true),
    FunctionNode(key: "guard", name: "雷达警卫", category: "雷达", requiresChassis: true),
    
    // 建图导航
    FunctionNode(key: "mapping", name: "开始建图", category: "建图"),
    FunctionNode(key: "mapping_display", name: "建图可视化", category: "建图"),
    FunctionNode(key: "save_map", name: "保存地图", category: "建图"),
    FunctionNode(key: "nav_bringup", name: "导航基础", category: "导航"),
    FunctionNode(key: "nav_display", name: "导航可视化", category: "导航"),
    FunctionNode(key: "nav_dwa", name: "DWA 导航", category: "导航"),
    FunctionNode(key: "nav_teb", name: "TEB 导航", category: "导航"),
    
    // 视觉功能
    FunctionNode(key: "camera", name: "深度相机", category: "视觉"),
    FunctionNode(key: "color_detect", name: "颜色识别", category: "视觉"),
    FunctionNode(key: "color_track", name: "颜色追踪", category: "视觉")
]

// ── 编舞配置 ──────────────────────────────────────

/// 编舞引擎循环频率 (Hz)
let DANCE_TICK_HZ: Int = 20
/// 编舞引擎循环间隔 (ms)
let DANCE_TICK_MS: Int64 = 1000 / Int64(DANCE_TICK_HZ)

/// 小车速度安全范围
struct SafeSpeed {
    static let minLinear: Double = -0.4
    static let maxLinear: Double = 0.4
    static let minAngular: Double = -1.2
    static let maxAngular: Double = 1.2
}
