/**
 * 应用常量配置（Android / Kotlin）
 */

package com.icar.musiccar

// ── 网络配置 ──────────────────────────────────────

object AppConstants {
    /** 默认小车 IP */
    const val DEFAULT_CAR_IP: String = "192.168.1.1"

    /** 默认小车端口 */
    const val DEFAULT_CAR_PORT: Int = 5000

    /** HTTP 默认超时 (ms) */
    const val HTTP_TIMEOUT: Long = 3000

    /** LLM 请求超时 (ms) — AI 编舞生成需要更长时间 */
    const val LLM_TIMEOUT: Long = 35000
}

// ── 控制模式 ──────────────────────────────────────

enum class CtrlMode(val key: String) {
    Manual("manual"),
    Nav("nav"),
    Vision("vision"),
    Follow("follow")
}

val CTRL_MODE_NAMES: Map<String, String> = mapOf(
    "manual" to "手动遥控",
    "nav" to "自动导航",
    "vision" to "视觉追踪",
    "follow" to "雷达跟随"
)

// ── 功能节点 ──────────────────────────────────────

data class FunctionNode(
    val key: String,
    val name: String,
    val category: String,
    val requiresChassis: Boolean = false
)

val FUNCTION_NODES: List<FunctionNode> = listOf(
    // 基础控制
    FunctionNode("chassis", "底盘驱动", "基础控制"),
    FunctionNode("lidar", "激光雷达", "基础控制", requiresChassis = true),

    // 雷达功能
    FunctionNode("avoidance", "雷达避障", "雷达", requiresChassis = true),
    FunctionNode("tracker", "雷达跟随", "雷达", requiresChassis = true),
    FunctionNode("guard", "雷达警卫", "雷达", requiresChassis = true),

    // 建图导航
    FunctionNode("mapping", "开始建图", "建图"),
    FunctionNode("mapping_display", "建图可视化", "建图"),
    FunctionNode("save_map", "保存地图", "建图"),
    FunctionNode("nav_bringup", "导航基础", "导航"),
    FunctionNode("nav_display", "导航可视化", "导航"),
    FunctionNode("nav_dwa", "DWA 导航", "导航"),
    FunctionNode("nav_teb", "TEB 导航", "导航"),

    // 视觉功能
    FunctionNode("camera", "深度相机", "视觉"),
    FunctionNode("color_detect", "颜色识别", "视觉"),
    FunctionNode("color_track", "颜色追踪", "视觉")
)

// ── 编舞配置 ──────────────────────────────────────

/** 编舞引擎循环频率 (Hz) */
const val DANCE_TICK_HZ: Int = 20

/** 编舞引擎循环间隔 (ms) */
const val DANCE_TICK_MS: Long = 1000L / DANCE_TICK_HZ

/** 小车速度安全范围 */
object SafeSpeed {
    const val MIN_LINEAR: Double = -0.4
    const val MAX_LINEAR: Double = 0.4
    const val MIN_ANGULAR: Double = -1.2
    const val MAX_ANGULAR: Double = 1.2
}
