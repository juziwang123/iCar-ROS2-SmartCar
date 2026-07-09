/**
 * 音乐小车 — 时间轴编舞引擎（Android / Kotlin）
 *
 * 每 50ms（20Hz）检查播放进度，在时间戳到达时通过 ApiClient 发送 HTTP 控制指令。
 *
 * 用法:
 *   val engine = DanceEngine(routine, ApiClient.getInstance())
 *   engine.onProgress = { elapsed, total -> ... }
 *   engine.onComplete = { ... }
 *   engine.start()
 */

package com.icar.musiccar.engine

import android.os.Handler
import android.os.Looper
import com.icar.musiccar.models.CmdRequest
import com.icar.musiccar.models.DanceMove
import com.icar.musiccar.models.DanceRoutine
import com.icar.musiccar.models.MoveTypes
import com.icar.musiccar.network.ApiClient
import kotlinx.coroutines.*

class DanceEngine(
    private val routine: DanceRoutine,
    private val api: ApiClient
) {
    private val handler = Handler(Looper.getMainLooper())
    private var moveIndex: Int = 0
    private var startTime: Long = 0
    private var running: Boolean = false
    private var currentMove: DanceMove? = null
    private var currentMoveEndTime: Long = 0
    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private var tickJob: Job? = null

    /** 进度回调 (elapsed_ms, total_ms) */
    var onProgress: ((elapsed: Long, total: Long) -> Unit)? = null
    /** 完成回调 */
    var onComplete: (() -> Unit)? = null
    /** 错误回调 */
    var onError: ((msg: String) -> Unit)? = null
    /** 动作触发回调 */
    var onMove: ((move: DanceMove, index: Int) -> Unit)? = null

    /** 是否正在运行 */
    val isRunning: Boolean get() = running

    /** 当前进度百分比 */
    val progress: Int
        get() {
            if (!running) return 0
            val elapsed = System.currentTimeMillis() - startTime
            return minOf(100, (elapsed * 100 / routine.duration).toInt())
        }

    /** 开始执行编舞 */
    suspend fun start() {
        moveIndex = 0
        running = true
        currentMove = null
        startTime = System.currentTimeMillis()

        // 20Hz 主循环
        tickJob = scope.launch {
            while (isActive && running) {
                val elapsed = System.currentTimeMillis() - startTime

                // 进度回调
                onProgress?.invoke(elapsed, routine.duration)

                // 当前动作到期 → 自动停止
                currentMove?.let { move ->
                    if (elapsed >= currentMoveEndTime) {
                        sendCmd(CmdRequest(type = MoveTypes.STOP))
                        currentMove = null
                    }
                }

                // 触发新动作
                while (
                    moveIndex < routine.moves.size &&
                    elapsed >= routine.moves[moveIndex].timestamp
                ) {
                    val move = routine.moves[moveIndex]
                    executeMove(move, moveIndex)
                    moveIndex++
                }

                // 编舞结束
                if (moveIndex >= routine.moves.size && currentMove == null) {
                    stop()
                    onComplete?.invoke()
                    break
                }

                delay(50) // 20Hz
            }
        }
    }

    /** 停止执行 */
    fun stop() {
        running = false
        tickJob?.cancel()
        sendCmd(CmdRequest(type = MoveTypes.STOP))
    }

    // ── 内部 ──────────────────────────────────

    private fun executeMove(move: DanceMove, index: Int) {
        try {
            onMove?.invoke(move, index)

            when (move.type) {
                MoveTypes.MOVE -> {
                    sendCmd(CmdRequest(
                        type = MoveTypes.MOVE,
                        linear = move.linear,
                        angular = move.angular
                    ))
                    if (move.duration > 0) {
                        currentMove = move
                        currentMoveEndTime = startTime + move.timestamp + move.duration
                    }
                }
                MoveTypes.SPIN -> {
                    sendCmd(CmdRequest(
                        type = MoveTypes.MOVE,
                        linear = 0.0,
                        angular = move.angular
                    ))
                    if (move.duration > 0) {
                        currentMove = move
                        currentMoveEndTime = startTime + move.timestamp + move.duration
                    }
                }
                MoveTypes.STOP -> {
                    sendCmd(CmdRequest(type = MoveTypes.STOP))
                    currentMove = null
                }
                MoveTypes.PAUSE -> {
                    // pause 不做任何事，依赖上一个 duration 到期自动 stop
                    currentMove = null
                }
            }
        } catch (e: Exception) {
            onError?.invoke("动作 #$index 执行失败: ${e.message}")
        }
    }

    private fun sendCmd(cmd: CmdRequest) {
        scope.launch {
            try {
                api.postCmd(cmd)
            } catch (e: Exception) {
                onError?.invoke("指令发送失败: ${e.message}")
            }
        }
    }
}
