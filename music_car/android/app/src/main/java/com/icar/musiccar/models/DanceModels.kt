/**
 * 音乐小车 — 数据模型（Android / Kotlin）
 */

package com.icar.musiccar.models

import kotlinx.serialization.Serializable

// ── 动作类型 ──────────────────────────────

typealias MoveType = String
object MoveTypes {
    const val MOVE = "move"
    const val STOP = "stop"
    const val SPIN = "spin"
    const val PAUSE = "pause"
}

// ── 节拍标记 ──────────────────────────────

typealias BeatTag = String
object BeatTags {
    const val BEAT = "beat"
    const val STRONG_BEAT = "strong_beat"
    const val FILL = "fill"
    const val BREAK = "break"
}

// ── 单个舞蹈动作 ──────────────────────────

@Serializable
data class DanceMove(
    /** 触发时间（毫秒，从歌曲开始计算） */
    val timestamp: Long,
    /** 动作类型 */
    val type: String,
    /** 线速度 m/s */
    val linear: Double = 0.0,
    /** 角速度 rad/s */
    val angular: Double = 0.0,
    /** 持续时间 ms（0=瞬时） */
    val duration: Long = 0,
    /** 节拍标记 */
    val tag: String? = null
)

// ── 完整编舞 ──────────────────────────────

@Serializable
data class DanceRoutine(
    /** 编舞名称 */
    val name: String,
    /** 歌曲文件名 */
    val song: String,
    /** BPM */
    val bpm: Int,
    /** 总时长（毫秒） */
    val duration: Long,
    /** 空间需求 */
    val spaceRequired: String,
    /** 动作序列（按 timestamp 升序） */
    val moves: List<DanceMove>
)

// ── AI 编舞请求 ───────────────────────────

@Serializable
data class ChoreographRequest(
    val song: String,
    val bpm: Int,
    val durationMs: Long,
    val style: String,
    val space: String,
    val extraRequirements: String? = null
)

// ── AI 编舞响应 ───────────────────────────

@Serializable
data class ChoreographResponse(
    val ok: Boolean,
    val routine: DanceRoutine? = null,
    val warnings: List<String>? = null,
    val error: String? = null,
    val backend: String? = null
)

// ── 控制指令 ──────────────────────────────

@Serializable
data class CmdRequest(
    val type: String,
    val linear: Double? = null,
    val angular: Double? = null,
    val mode: String? = null,
    val active: Boolean? = null
)

// ── 常用常量 ──────────────────────────────

val MOVE_TYPE_NAMES: Map<String, String> = mapOf(
    MoveTypes.MOVE to "移动",
    MoveTypes.STOP to "停止",
    MoveTypes.SPIN to "旋转",
    MoveTypes.PAUSE to "暂停"
)

val MOVE_TYPE_ICONS: Map<String, String> = mapOf(
    MoveTypes.MOVE to "🏃",
    MoveTypes.STOP to "🛑",
    MoveTypes.SPIN to "🔄",
    MoveTypes.PAUSE to "⏸️"
)

val STYLE_OPTIONS: List<String> = listOf(
    "欢快活泼", "优雅古典", "劲爆动感", "温柔舒缓",
    "科技未来感", "可爱萌系", "黑暗神秘"
)

val SPACE_OPTIONS: List<String> = listOf(
    "1m×1m", "2m×2m", "2m×3m", "3m×3m"
)
