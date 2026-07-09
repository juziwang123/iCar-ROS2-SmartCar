/**
 * 音乐小车 — 时间轴编舞引擎（iOS / Swift）
 *
 * 每 50ms（20Hz）检查播放进度，在时间戳到达时通过 ApiClient 发送 HTTP 控制指令。
 *
 * 用法:
 *   let engine = DanceEngine(routine: routine, api: ApiClient.shared)
 *   engine.onProgress = { elapsed, total in ... }
 *   engine.onComplete = { ... }
 *   await engine.start()
 */

import Foundation

@MainActor
class DanceEngine {
    private let routine: DanceRoutine
    private let api: ApiClient
    private var moveIndex: Int = 0
    private var startTime: TimeInterval = 0
    private var running: Bool = false
    private var currentMove: DanceMove? = nil
    private var currentMoveEndTime: TimeInterval = 0
    private var timer: Timer?
    
    /// 进度回调 (elapsed_ms, total_ms)
    var onProgress: ((Int64, Int64) -> Void)?
    /// 完成回调
    var onComplete: (() -> Void)?
    /// 错误回调
    var onError: ((String) -> Void)?
    /// 动作触发回调
    var onMove: ((DanceMove, Int) -> Void)?
    
    /// 是否正在运行
    var isRunning: Bool { running }
    
    /// 当前进度百分比
    var progress: Int {
        guard running else { return 0 }
        let elapsed = Date().timeIntervalSince1970 * 1000 - startTime
        return min(100, Int(elapsed * 100 / Double(routine.duration)))
    }
    
    init(routine: DanceRoutine, api: ApiClient = .shared) {
        self.routine = routine
        self.api = api
    }
    
    /// 开始执行编舞
    func start() async {
        moveIndex = 0
        running = true
        currentMove = nil
        startTime = Date().timeIntervalSince1970 * 1000
        
        // 20Hz 主循环
        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / Double(DANCE_TICK_HZ), repeats: true) { [weak self] _ in
            guard let self = self, self.running else { return }
            
            Task { @MainActor in
                let elapsed = Int64(Date().timeIntervalSince1970 * 1000 - self.startTime)
                
                // 进度回调
                self.onProgress?(elapsed, self.routine.duration)
                
                // 当前动作到期 → 自动停止
                if let move = self.currentMove, Double(elapsed) >= self.currentMoveEndTime {
                    try? await self.api.postCmd(CmdRequest(type: MoveType.stop))
                    self.currentMove = nil
                }
                
                // 触发新动作
                while self.moveIndex < self.routine.moves.count &&
                      elapsed >= self.routine.moves[self.moveIndex].timestamp {
                    let move = self.routine.moves[self.moveIndex]
                    self.executeMove(move, index: self.moveIndex)
                    self.moveIndex += 1
                }
                
                // 编舞结束
                if self.moveIndex >= self.routine.moves.count && self.currentMove == nil {
                    self.stop()
                    self.onComplete?()
                }
            }
        }
    }
    
    /// 停止执行
    func stop() {
        running = false
        timer?.invalidate()
        timer = nil
        Task {
            try? await api.postCmd(CmdRequest(type: MoveType.stop))
        }
    }
    
    // ── 内部 ──────────────────────────────────
    
    private func executeMove(_ move: DanceMove, index: Int) {
        onMove?(move, index)
        
        Task {
            do {
                switch move.type {
                case MoveType.move:
                    try await api.postCmd(CmdRequest(
                        type: MoveType.move,
                        linear: move.linear,
                        angular: move.angular
                    ))
                    if move.duration > 0 {
                        currentMove = move
                        currentMoveEndTime = startTime + Double(move.timestamp) + Double(move.duration)
                    }
                    
                case MoveType.spin:
                    try await api.postCmd(CmdRequest(
                        type: MoveType.move,
                        linear: 0.0,
                        angular: move.angular
                    ))
                    if move.duration > 0 {
                        currentMove = move
                        currentMoveEndTime = startTime + Double(move.timestamp) + Double(move.duration)
                    }
                    
                case MoveType.stop:
                    try await api.postCmd(CmdRequest(type: MoveType.stop))
                    currentMove = nil
                    
                case MoveType.pause:
                    // pause 不做任何事
                    currentMove = nil
                    
                default:
                    break
                }
            } catch {
                onError?("动作 #\(index) 执行失败: \(error.localizedDescription)")
            }
        }
    }
}
