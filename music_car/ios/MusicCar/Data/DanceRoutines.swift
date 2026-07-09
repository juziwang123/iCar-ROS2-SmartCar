/**
 * 音乐小车 — 示例编舞数据仓库（iOS / Swift）
 *
 * 包含三首预置编舞，可直接使用或作为 LLM 微调的训练参考。
 */

import Foundation

let DANCE_ROUTINES: [DanceRoutine] = [
    // ── 1. 欢乐颂 — 古典优雅 ──────────────────────
    DanceRoutine(
        name: "欢乐颂 — 古典优雅",
        song: "ode_to_joy.mp3",
        bpm: 120,
        duration: 30000,
        spaceRequired: "2m × 2m",
        moves: [
            DanceMove(timestamp: 0, type: MoveType.stop, tag: BeatTag.breakTag),
            DanceMove(timestamp: 3000, type: MoveType.move, linear: 0.08, angular: 0, duration: 2000, tag: BeatTag.beat),
            DanceMove(timestamp: 5200, type: MoveType.move, linear: 0.12, angular: 0.2, duration: 3000, tag: BeatTag.beat),
            DanceMove(timestamp: 8500, type: MoveType.move, linear: 0.1, angular: -0.3, duration: 3000, tag: BeatTag.beat),
            DanceMove(timestamp: 11800, type: MoveType.spin, angular: 1.0, duration: 2500, tag: BeatTag.strongBeat),
            DanceMove(timestamp: 14500, type: MoveType.move, linear: 0.15, angular: 0, duration: 2000, tag: BeatTag.beat),
            DanceMove(timestamp: 16800, type: MoveType.move, linear: -0.12, angular: 0, duration: 2000, tag: BeatTag.beat),
            DanceMove(timestamp: 19000, type: MoveType.move, linear: 0.1, angular: 0.5, duration: 3000, tag: BeatTag.fill),
            DanceMove(timestamp: 22300, type: MoveType.move, linear: 0.08, angular: 0, duration: 2000, tag: BeatTag.beat),
            DanceMove(timestamp: 24600, type: MoveType.move, linear: 0.05, angular: 0, duration: 1500, tag: BeatTag.beat),
            DanceMove(timestamp: 26400, type: MoveType.move, linear: -0.05, angular: 0, duration: 800, tag: BeatTag.beat),
            DanceMove(timestamp: 27500, type: MoveType.stop, tag: BeatTag.breakTag)
        ]
    ),
    
    // ── 2. 拍手歌 — 摇滚动感 ──────────────────────
    DanceRoutine(
        name: "拍手歌 — 摇滚动感",
        song: "we_will_rock_you.mp3",
        bpm: 90,
        duration: 25000,
        spaceRequired: "2m × 2m",
        moves: [
            DanceMove(timestamp: 0, type: MoveType.stop, tag: BeatTag.breakTag),
            DanceMove(timestamp: 1500, type: MoveType.move, linear: 0.3, angular: 0, duration: 500, tag: BeatTag.strongBeat),
            DanceMove(timestamp: 2200, type: MoveType.stop, tag: BeatTag.strongBeat),
            DanceMove(timestamp: 2900, type: MoveType.move, linear: 0.3, angular: 0, duration: 500, tag: BeatTag.strongBeat),
            DanceMove(timestamp: 3600, type: MoveType.stop, tag: BeatTag.strongBeat),
            DanceMove(timestamp: 4300, type: MoveType.spin, angular: 1.2, duration: 600, tag: BeatTag.strongBeat),
            DanceMove(timestamp: 5100, type: MoveType.move, linear: -0.3, angular: 0, duration: 500, tag: BeatTag.beat),
            DanceMove(timestamp: 5800, type: MoveType.stop, tag: BeatTag.beat),
            DanceMove(timestamp: 6600, type: MoveType.move, linear: 0.3, angular: 0.5, duration: 800, tag: BeatTag.strongBeat),
            DanceMove(timestamp: 7600, type: MoveType.spin, angular: -1.2, duration: 600, tag: BeatTag.strongBeat),
            DanceMove(timestamp: 8400, type: MoveType.move, linear: -0.25, angular: 0, duration: 500, tag: BeatTag.beat),
            DanceMove(timestamp: 9100, type: MoveType.stop, tag: BeatTag.beat),
            DanceMove(timestamp: 10000, type: MoveType.move, linear: 0.3, angular: 0, duration: 700, tag: BeatTag.strongBeat),
            DanceMove(timestamp: 10900, type: MoveType.stop, tag: BeatTag.strongBeat),
            DanceMove(timestamp: 11800, type: MoveType.spin, angular: 1.0, duration: 1500, tag: BeatTag.fill),
            DanceMove(timestamp: 13500, type: MoveType.move, linear: 0.25, angular: -0.8, duration: 2000, tag: BeatTag.beat),
            DanceMove(timestamp: 15800, type: MoveType.move, linear: -0.2, angular: 0, duration: 800, tag: BeatTag.beat),
            DanceMove(timestamp: 16800, type: MoveType.move, linear: 0.3, angular: 0, duration: 600, tag: BeatTag.strongBeat),
            DanceMove(timestamp: 17600, type: MoveType.stop, tag: BeatTag.strongBeat),
            DanceMove(timestamp: 18500, type: MoveType.spin, angular: 1.2, duration: 1000, tag: BeatTag.strongBeat),
            DanceMove(timestamp: 19700, type: MoveType.move, linear: -0.3, angular: 0, duration: 500, tag: BeatTag.beat),
            DanceMove(timestamp: 20400, type: MoveType.stop, tag: BeatTag.beat),
            DanceMove(timestamp: 21200, type: MoveType.move, linear: 0.15, angular: 0, duration: 800, tag: BeatTag.beat),
            DanceMove(timestamp: 22200, type: MoveType.move, linear: -0.08, angular: 0, duration: 300, tag: BeatTag.beat),
            DanceMove(timestamp: 22800, type: MoveType.stop, tag: BeatTag.breakTag)
        ]
    ),
    
    // ── 3. 小星星 — 温柔舒缓 ──────────────────────
    DanceRoutine(
        name: "小星星 — 温柔舒缓",
        song: "twinkle_twinkle.mp3",
        bpm: 100,
        duration: 25000,
        spaceRequired: "1m × 1m",
        moves: [
            DanceMove(timestamp: 0, type: MoveType.stop, tag: BeatTag.breakTag),
            DanceMove(timestamp: 3000, type: MoveType.move, linear: 0.06, angular: 0, duration: 2000, tag: BeatTag.beat),
            DanceMove(timestamp: 5200, type: MoveType.pause, tag: BeatTag.beat),
            DanceMove(timestamp: 6500, type: MoveType.move, linear: 0.06, angular: 0.3, duration: 2000, tag: BeatTag.beat),
            DanceMove(timestamp: 8700, type: MoveType.pause, tag: BeatTag.beat),
            DanceMove(timestamp: 10000, type: MoveType.move, linear: 0.06, angular: -0.3, duration: 2000, tag: BeatTag.beat),
            DanceMove(timestamp: 12200, type: MoveType.pause, tag: BeatTag.beat),
            DanceMove(timestamp: 13500, type: MoveType.move, linear: 0.06, angular: 0, duration: 2000, tag: BeatTag.beat),
            DanceMove(timestamp: 15700, type: MoveType.spin, angular: 0.5, duration: 3000, tag: BeatTag.fill),
            DanceMove(timestamp: 19000, type: MoveType.move, linear: 0.04, angular: 0, duration: 1500, tag: BeatTag.beat),
            DanceMove(timestamp: 20800, type: MoveType.move, linear: -0.04, angular: 0, duration: 800, tag: BeatTag.beat),
            DanceMove(timestamp: 21800, type: MoveType.stop, tag: BeatTag.breakTag)
        ]
    )
]
