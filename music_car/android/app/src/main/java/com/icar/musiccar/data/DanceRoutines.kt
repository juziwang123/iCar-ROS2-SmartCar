/**
 * 音乐小车 — 示例编舞数据仓库（Android / Kotlin）
 *
 * 包含三首预置编舞，可直接使用或作为 LLM 微调的训练参考。
 */

package com.icar.musiccar.data

import com.icar.musiccar.models.DanceMove
import com.icar.musiccar.models.DanceRoutine
import com.icar.musiccar.models.MoveTypes

val DANCE_ROUTINES: List<DanceRoutine> = listOf(
    // ── 1. 欢乐颂 — 古典优雅 ──────────────────────
    DanceRoutine(
        name = "欢乐颂 — 古典优雅",
        song = "ode_to_joy.mp3",
        bpm = 120,
        duration = 30000,
        spaceRequired = "2m × 2m",
        moves = listOf(
            DanceMove(0, MoveTypes.STOP, tag = "break"),
            DanceMove(3000, MoveTypes.MOVE, linear = 0.08, angular = 0.0, duration = 2000, tag = "beat"),
            DanceMove(5200, MoveTypes.MOVE, linear = 0.12, angular = 0.2, duration = 3000, tag = "beat"),
            DanceMove(8500, MoveTypes.MOVE, linear = 0.1, angular = -0.3, duration = 3000, tag = "beat"),
            DanceMove(11800, MoveTypes.SPIN, angular = 1.0, duration = 2500, tag = "strong_beat"),
            DanceMove(14500, MoveTypes.MOVE, linear = 0.15, angular = 0.0, duration = 2000, tag = "beat"),
            DanceMove(16800, MoveTypes.MOVE, linear = -0.12, angular = 0.0, duration = 2000, tag = "beat"),
            DanceMove(19000, MoveTypes.MOVE, linear = 0.1, angular = 0.5, duration = 3000, tag = "fill"),
            DanceMove(22300, MoveTypes.MOVE, linear = 0.08, angular = 0.0, duration = 2000, tag = "beat"),
            DanceMove(24600, MoveTypes.MOVE, linear = 0.05, angular = 0.0, duration = 1500, tag = "beat"),
            DanceMove(26400, MoveTypes.MOVE, linear = -0.05, angular = 0.0, duration = 800, tag = "beat"),
            DanceMove(27500, MoveTypes.STOP, tag = "break")
        )
    ),

    // ── 2. 拍手歌 — 摇滚动感 ──────────────────────
    DanceRoutine(
        name = "拍手歌 — 摇滚动感",
        song = "we_will_rock_you.mp3",
        bpm = 90,
        duration = 25000,
        spaceRequired = "2m × 2m",
        moves = listOf(
            DanceMove(0, MoveTypes.STOP, tag = "break"),
            DanceMove(1500, MoveTypes.MOVE, linear = 0.3, angular = 0.0, duration = 500, tag = "strong_beat"),
            DanceMove(2200, MoveTypes.STOP, tag = "strong_beat"),
            DanceMove(2900, MoveTypes.MOVE, linear = 0.3, angular = 0.0, duration = 500, tag = "strong_beat"),
            DanceMove(3600, MoveTypes.STOP, tag = "strong_beat"),
            DanceMove(4300, MoveTypes.SPIN, angular = 1.2, duration = 600, tag = "strong_beat"),
            DanceMove(5100, MoveTypes.MOVE, linear = -0.3, angular = 0.0, duration = 500, tag = "beat"),
            DanceMove(5800, MoveTypes.STOP, tag = "beat"),
            DanceMove(6600, MoveTypes.MOVE, linear = 0.3, angular = 0.5, duration = 800, tag = "strong_beat"),
            DanceMove(7600, MoveTypes.SPIN, angular = -1.2, duration = 600, tag = "strong_beat"),
            DanceMove(8400, MoveTypes.MOVE, linear = -0.25, angular = 0.0, duration = 500, tag = "beat"),
            DanceMove(9100, MoveTypes.STOP, tag = "beat"),
            DanceMove(10000, MoveTypes.MOVE, linear = 0.3, angular = 0.0, duration = 700, tag = "strong_beat"),
            DanceMove(10900, MoveTypes.STOP, tag = "strong_beat"),
            DanceMove(11800, MoveTypes.SPIN, angular = 1.0, duration = 1500, tag = "fill"),
            DanceMove(13500, MoveTypes.MOVE, linear = 0.25, angular = -0.8, duration = 2000, tag = "beat"),
            DanceMove(15800, MoveTypes.MOVE, linear = -0.2, angular = 0.0, duration = 800, tag = "beat"),
            DanceMove(16800, MoveTypes.MOVE, linear = 0.3, angular = 0.0, duration = 600, tag = "strong_beat"),
            DanceMove(17600, MoveTypes.STOP, tag = "strong_beat"),
            DanceMove(18500, MoveTypes.SPIN, angular = 1.2, duration = 1000, tag = "strong_beat"),
            DanceMove(19700, MoveTypes.MOVE, linear = -0.3, angular = 0.0, duration = 500, tag = "beat"),
            DanceMove(20400, MoveTypes.STOP, tag = "beat"),
            DanceMove(21200, MoveTypes.MOVE, linear = 0.15, angular = 0.0, duration = 800, tag = "beat"),
            DanceMove(22200, MoveTypes.MOVE, linear = -0.08, angular = 0.0, duration = 300, tag = "beat"),
            DanceMove(22800, MoveTypes.STOP, tag = "break")
        )
    ),

    // ── 3. 小星星 — 温柔舒缓 ──────────────────────
    DanceRoutine(
        name = "小星星 — 温柔舒缓",
        song = "twinkle_twinkle.mp3",
        bpm = 100,
        duration = 25000,
        spaceRequired = "1m × 1m",
        moves = listOf(
            DanceMove(0, MoveTypes.STOP, tag = "break"),
            DanceMove(3000, MoveTypes.MOVE, linear = 0.06, angular = 0.0, duration = 2000, tag = "beat"),
            DanceMove(5200, MoveTypes.PAUSE, tag = "beat"),
            DanceMove(6500, MoveTypes.MOVE, linear = 0.06, angular = 0.3, duration = 2000, tag = "beat"),
            DanceMove(8700, MoveTypes.PAUSE, tag = "beat"),
            DanceMove(10000, MoveTypes.MOVE, linear = 0.06, angular = -0.3, duration = 2000, tag = "beat"),
            DanceMove(12200, MoveTypes.PAUSE, tag = "beat"),
            DanceMove(13500, MoveTypes.MOVE, linear = 0.06, angular = 0.0, duration = 2000, tag = "beat"),
            DanceMove(15700, MoveTypes.SPIN, angular = 0.5, duration = 3000, tag = "fill"),
            DanceMove(19000, MoveTypes.MOVE, linear = 0.04, angular = 0.0, duration = 1500, tag = "beat"),
            DanceMove(20800, MoveTypes.MOVE, linear = -0.04, angular = 0.0, duration = 800, tag = "beat"),
            DanceMove(21800, MoveTypes.STOP, tag = "break")
        )
    )
)
