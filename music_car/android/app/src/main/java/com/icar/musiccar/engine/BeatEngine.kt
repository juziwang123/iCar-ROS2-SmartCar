/**
 * 音乐小车 — 节拍驱动引擎（Android / Kotlin）
 *
 * 按固定 BPM 节拍触发循环动作模板。
 * 比时间轴模式更灵活——同一编舞可适配不同 BPM 的歌曲。
 *
 * 用法:
 *   val engine = BeatEngine(120, CHORUS_PATTERN, ApiClient.getInstance())
 *   engine.start()
 *   engine.changePattern(VERSE_PATTERN)
 */

package com.icar.musiccar.engine

import com.icar.musiccar.models.CmdRequest
import com.icar.musiccar.models.DanceMove
import com.icar.musiccar.models.MoveTypes
import com.icar.musiccar.network.ApiClient
import kotlinx.coroutines.*

class BeatEngine(
    private var bpm: Int,
    private var pattern: List<DanceMove>,
    private val api: ApiClient
) {
    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private var patternIndex: Int = 0
    private var running: Boolean = false
    private var beatCount: Int = 0
    private var beatInterval: Long = 60000L / bpm
    private var tickJob: Job? = null

    var onBeat: ((beatNumber: Int) -> Unit)? = null
    var onError: ((msg: String) -> Unit)? = null

    /** 开始节拍循环 */
    fun start() {
        running = true
        patternIndex = 0
        beatCount = 0
        val interval = beatInterval

        tickJob = scope.launch {
            while (isActive && running) {
                beatCount++
                onBeat?.invoke(beatCount)

                if (pattern.isNotEmpty()) {
                    val move = pattern[patternIndex % pattern.size]
                    executeMove(move)
                    patternIndex = (patternIndex + 1) % pattern.size
                }

                delay(interval)
            }
        }
    }

    /** 停止 */
    fun stop() {
        running = false
        tickJob?.cancel()
        scope.launch {
            try { api.postCmd(CmdRequest(type = MoveTypes.STOP)) } catch (_: Exception) {}
        }
    }

    /** 更换动作模板（歌曲段落切换时调用） */
    fun changePattern(newPattern: List<DanceMove>) {
        pattern = newPattern
        patternIndex = 0
    }

    /** 更改 BPM（变速时） */
    fun changeBpm(bpm: Int) {
        this.bpm = bpm
        beatInterval = 60000L / bpm
    }

    // ── 内部 ──────────────────────────────────

    private fun executeMove(move: DanceMove) {
        try {
            when (move.type) {
                MoveTypes.MOVE, MoveTypes.SPIN -> {
                    scope.launch {
                        api.postCmd(CmdRequest(
                            type = MoveTypes.MOVE,
                            linear = move.linear,
                            angular = move.angular
                        ))
                    }
                }
                MoveTypes.STOP, MoveTypes.PAUSE -> {
                    scope.launch {
                        api.postCmd(CmdRequest(type = MoveTypes.STOP))
                    }
                }
            }
        } catch (e: Exception) {
            onError?.invoke("节拍动作执行失败: ${e.message}")
        }
    }
}

// ── 常用动作模板 ──────────────────────────────────

/** 副歌模板（激烈） */
val CHORUS_PATTERN: List<DanceMove> = listOf(
    DanceMove(timestamp = 0, type = MoveTypes.MOVE, linear = 0.3, angular = 0.0, tag = "beat"),
    DanceMove(timestamp = 0, type = MoveTypes.SPIN, angular = 1.2, tag = "strong_beat"),
    DanceMove(timestamp = 0, type = MoveTypes.MOVE, linear = -0.25, angular = 0.0, tag = "beat"),
    DanceMove(timestamp = 0, type = MoveTypes.SPIN, angular = -1.2, tag = "strong_beat")
)

/** 主歌模板（舒缓） */
val VERSE_PATTERN: List<DanceMove> = listOf(
    DanceMove(timestamp = 0, type = MoveTypes.MOVE, linear = 0.12, angular = 0.1, tag = "beat"),
    DanceMove(timestamp = 0, type = MoveTypes.PAUSE, tag = "beat"),
    DanceMove(timestamp = 0, type = MoveTypes.MOVE, linear = 0.12, angular = -0.1, tag = "beat"),
    DanceMove(timestamp = 0, type = MoveTypes.PAUSE, tag = "beat")
)

/** 前奏/尾声模板（静止） */
val INTRO_PATTERN: List<DanceMove> = listOf(
    DanceMove(timestamp = 0, type = MoveTypes.STOP, tag = "break")
)

/** 间奏模板（8字绕圈） */
val BRIDGE_PATTERN: List<DanceMove> = listOf(
    DanceMove(timestamp = 0, type = MoveTypes.MOVE, linear = 0.1, angular = 0.7, tag = "beat"),
    DanceMove(timestamp = 0, type = MoveTypes.MOVE, linear = 0.1, angular = -0.7, tag = "beat")
)
