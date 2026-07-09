/**
 * 网络层 — WebSocket 状态推送客户端（iOS / Swift）
 *
 * 对应鸿蒙端的 StateSocket.ets，
 * 连接 Flask-SocketIO 服务，接收每 200ms 的状态推送。
 *
 * 协议：SocketIO v4（EIO=4, transport=websocket）
 *
 * 依赖: URLSessionWebSocketTask (iOS 13+)
 */

import Foundation

@MainActor
class StateSocket: NSObject, URLSessionWebSocketDelegate {
    private var webSocketTask: URLSessionWebSocketTask?
    private var session: URLSession!
    private var baseURL: String = "ws://\(AppConstants.defaultCarIP):\(AppConstants.defaultCarPort)"
    private var shouldReconnect: Bool = false
    private var reconnectDelay: TimeInterval = 1.0
    private let maxReconnectDelay: TimeInterval = 30.0
    private var reconnectTimer: Timer?
    
    /// 状态回调
    var onState: ((CarState) -> Void)?
    /// 连接成功回调
    var onConnected: (() -> Void)?
    /// 错误回调
    var onError: ((String) -> Void)?
    /// 断开回调
    var onDisconnected: (() -> Void)?
    
    override init() {
        super.init()
        session = URLSession(configuration: .default, delegate: self, delegateQueue: nil)
    }
    
    func setServer(ip: String, port: Int = 5000) {
        baseURL = "ws://\(ip):\(port)"
    }
    
    /// 连接 WebSocket
    func connect() {
        shouldReconnect = true
        cancelReconnect()
        
        let urlString = "\(baseURL)/socket.io/?EIO=4&transport=websocket"
        guard let url = URL(string: urlString) else {
            onError?("无效的 URL: \(urlString)")
            return
        }
        
        webSocketTask = session.webSocketTask(with: url)
        webSocketTask?.resume()
        
        onConnected?()
        receiveMessage()
    }
    
    /// 断开连接
    func disconnect() {
        shouldReconnect = false
        cancelReconnect()
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        webSocketTask = nil
    }
    
    /// 发送指令（备用通道，通过 WebSocket 发 cmd 事件）
    func sendCmd(_ cmd: [String: Any]) {
        guard let jsonData = try? JSONSerialization.data(withJSONObject: ["cmd", cmd]),
              let jsonStr = String(data: jsonData, encoding: .utf8) else {
            return
        }
        let payload = "42\(jsonStr)"
        webSocketTask?.send(.string(payload)) { _ in }
    }
    
    // ── 内部 ──────────────────────────────────
    
    private func receiveMessage() {
        webSocketTask?.receive { [weak self] result in
            guard let self = self else { return }
            
            switch result {
            case .success(let message):
                switch message {
                case .string(let text):
                    Task { @MainActor in
                        self.handleMessage(text)
                    }
                case .data(_):
                    break
                @unknown default:
                    break
                }
                // 继续接收
                self.receiveMessage()
                
            case .failure(let error):
                Task { @MainActor in
                    self.onError?("WebSocket 错误: \(error.localizedDescription)")
                    if self.shouldReconnect {
                        self.scheduleReconnect()
                    }
                }
            }
        }
    }
    
    private func handleMessage(_ text: String) {
        guard text.contains("\"state\"") else { return }
        
        // 移除 SocketIO 帧头: 42["state",
        guard let start = text.range(of: "[{")?.lowerBound,
              let end = text.range(of: "}]", options: .backwards)?.upperBound else {
            return
        }
        
        let innerRange = text.index(after: start)..<text.index(before: end)
        let inner = String(text[innerRange])
        
        guard let data = inner.data(using: .utf8),
              let arr = try? JSONSerialization.jsonObject(with: data) as? [Any],
              arr.count >= 2,
              arr[0] as? String == "state",
              let stateDict = arr[1] as? [String: Any] else {
            return
        }
        
        let state = CarState(
            linear_x: stateDict["linear_x"] as? Double ?? 0,
            angular_z: stateDict["angular_z"] as? Double ?? 0,
            estop: stateDict["estop"] as? Bool ?? false,
            mode: stateDict["mode"] as? String ?? "",
            running_nodes: stateDict["running_nodes"] as? [String] ?? []
        )
        
        onState?(state)
    }
    
    private func scheduleReconnect() {
        cancelReconnect()
        reconnectTimer = Timer.scheduledTimer(withTimeInterval: reconnectDelay, repeats: false) { [weak self] _ in
            Task { @MainActor in
                print("[StateSocket] 重连中... (延迟 \(self?.reconnectDelay ?? 0)s)")
                self?.connect()
                if let delay = self?.reconnectDelay {
                    self?.reconnectDelay = min(delay * 2, self?.maxReconnectDelay ?? 30)
                }
            }
        }
    }
    
    private func cancelReconnect() {
        reconnectTimer?.invalidate()
        reconnectTimer = nil
    }
    
    // MARK: - URLSessionWebSocketDelegate
    
    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        Task { @MainActor in
            onDisconnected?()
            if shouldReconnect {
                scheduleReconnect()
            }
        }
    }
}
