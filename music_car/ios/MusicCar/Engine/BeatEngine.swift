/**
 * 音乐小车 — 节拍驱动引擎（iOS / Swift）
 *
 * 按固定 BPM 节拍触发循环动作模板。
 * 比时间轴模式更灵活——同一编舞可适配不同 BPM 的歌曲。
 *
 * 用法:
 *   let engine = BeatEngine(bpm: 120, pattern: CHORUS_PATTERN, api: ApiClient.shared)
 *   engine.start()
 *   engine.changePattern(VERSE_PATTERN)
 */

import Foundation

@MainActor
class BeatEngine {
    private let api: ApiClient
    private var pattern: [DanceMove]
    private var bpm: Int
    private var beatInterval: TimeInterval
    private var patternIndex: Int = 0
    private var running: Bool = false
    private var beatCount: Int = 0
    private var timer: Timer?
    
    var onBeat: ((Int) -> Void)?
    var onError: ((String) -> Void)?
    
    init(bpm: Int, pattern: [DanceMove], api: ApiClient = .shared) {
        self.bpm = bpm
        self.pattern = pattern
        self.api = api
        self.beatInterval = 60.0 / Double(bpm)
    }
    
    /// 开始节拍循环
    func start() {
        running = true
        patternIndex = 0
        beatCount = 0
        
        timer = Timer.scheduledTimer(withTimeInterval: beatInterval, repeats: true) { [weak self] _ in
            guard let self = self, self.running else { return }
            
            Task { @MainActor in
                self.beatCount += 1
                self.onBeat?(self.beatCount)
                
                if !self.pattern.isEmpty {
                    let move = self.pattern[self.patternIndex % self.pattern.count]
                    self.executeMove(move)
                    self.patternIndex = (self.patternIndex + 1) % self.pattern.count
                }
            }
        }
    }
    
    /// 停止
    func stop() {
        running = false
        timer?.invalidate()
        timer = nil
        Task {
            try? await api.postCmd(CmdRequest(type: MoveType.stop))
        }
    }
    
    /// 更换动作模板（歌曲段落切换时调用）
    func changePattern(_ newPattern: [DanceMove]) {
        pattern = newPattern
        patternIndex = 0
    }
    
    /// 更改 BPM（变速时）
    func changeBpm(_ bpm: Int) {
        self.bpm = bpm
        beatInterval = 60.0 / Double(bpm)
        // 重启 timer 以使用新的间隔
        if running {
            timer?.invalidate()
            timer = Timer.scheduledTimer(withTimeInterval: beatInterval, repeats: true) { [weak self] _ in
                guard let self = self, self.running else { return }
                Task { @MainActor in
                    self.beatCount += 1
                    self.onBeat?(self.beatCount)
                    if !self.pattern.isEmpty {
                        let move = self.pattern[self.patternIndex % self.pattern.count]
                        self.executeMove(move)
                        self.patternIndex = (self.patternIndex + 1) % self.pattern.count
                    }
                }
            }
        }
    }
    
    // ── 内部 ──────────────────────────────────
    
    private func executeMove(_ move: DanceMove) {
        Task {
            do {
                switch move.type {
                case MoveType.move, MoveType.spin:
                    try await api.postCmd(CmdRequest(
                        type: MoveType.move,
                        linear: move.linear,
                        angular: move.angular
                    ))
                case MoveType.stop, MoveType.pause:
                    try await api.postCmd(CmdRequest(type: MoveType.stop))
                default:
                    break
                }
            } catch {
                onError?("节拍动作执行失败: \(error.localizedDescription)")
            }
        }
    }
}

// ── 常用动作模板 ──────────────────────────────────

/// 副歌模板（激烈）
let CHORUS_PATTERN: [DanceMove] = [
    DanceMove(timestamp: 0, type: MoveType.move, linear: 0.3, angular: 0, tag: BeatTag.beat),
    DanceMove(timestamp: 0, type: MoveType.spin, angular: 1.2, tag: BeatTag.strongBeat),
    DanceMove(timestamp: 0, type: MoveType.move, linear: -0.25, angular: 0, tag: BeatTag.beat),
    DanceMove(timestamp: 0, type: MoveType.spin, angular: -1.2, tag: BeatTag.strongBeat)
]

/// 主歌模板（舒缓）
let VERSE_PATTERN: [DanceMove] = [
    DanceMove(timestamp: 0, type: MoveType.move, linear: 0.12, angular: 0.1, tag: BeatTag.beat),
    DanceMove(timestamp: 0, type: MoveType.pause, tag: BeatTag.beat),
    DanceMove(timestamp: 0, type: MoveType.move, linear: 0.12, angular: -0.1, tag: BeatTag.beat),
    DanceMove(timestamp: 0, type: MoveType.pause, tag: BeatTag.beat)
]

/// 前奏/尾声模板（静止）
let INTRO_PATTERN: [DanceMove] = [
    DanceMove(timestamp: 0, type: MoveType.stop, tag: BeatTag.breakTag)
]

/// 间奏模板（8字绕圈）
let BRIDGE_PATTERN: [DanceMove] = [
    DanceMove(timestamp: 0, type: MoveType.move, linear: 0.1, angular: 0.7, tag: BeatTag.beat),
    DanceMove(timestamp: 0, type: MoveType.move, linear: 0.1, angular: -0.7, tag: BeatTag.beat)
]
