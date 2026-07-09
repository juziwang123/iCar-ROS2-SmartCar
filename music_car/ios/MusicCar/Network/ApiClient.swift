/**
 * 网络层 — HTTP 客户端（iOS / Swift）
 *
 * 对应鸿蒙端的 ApiClient.ets，严格复用 APP接口文档.md 的 HTTP 接口。
 *
 * 接口：
 *   POST /api/cmd              — 控制指令
 *   POST /api/process/start    — 启动功能节点
 *   POST /api/process/stop     — 停止功能节点
 *   GET  /api/state            — 获取状态（一次性快照）
 */

import Foundation

class ApiClient {
    static let shared = ApiClient()
    
    private var baseURL: String = "http://\(AppConstants.defaultCarIP):\(AppConstants.defaultCarPort)"
    private let session: URLSession
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()
    
    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = AppConstants.httpTimeout
        config.timeoutIntervalForResource = AppConstants.httpTimeout
        session = URLSession(configuration: config)
    }
    
    /// 设置小车地址
    func setServer(ip: String, port: Int = 5000) {
        baseURL = "http://\(ip):\(port)"
    }
    
    // ── 公开接口 ────────────────────────────────
    
    /// 发送控制指令
    func postCmd(_ cmd: CmdRequest) async throws -> ApiResponse {
        return try await post(path: "/api/cmd", body: cmd)
    }
    
    /// 启动功能节点
    func startProcess(_ funcName: String) async throws -> ApiResponse {
        return try await postDict(path: "/api/process/start", dict: ["function": funcName])
    }
    
    /// 停止功能节点
    func stopProcess(_ funcName: String) async throws -> ApiResponse {
        return try await postDict(path: "/api/process/stop", dict: ["function": funcName])
    }
    
    /// 获取小车状态（一次性快照）
    func getState() async throws -> CarState {
        guard let url = URL(string: "\(baseURL)/api/state") else {
            throw URLError(.badURL)
        }
        
        let (data, response) = try await session.data(from: url)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        
        return try decoder.decode(CarState.self, from: data)
    }
    
    /// 测试连通性
    func ping() async -> Bool {
        do {
            _ = try await getState()
            return true
        } catch {
            return false
        }
    }
    
    // ── 内部方法 ────────────────────────────────
    
    private func post<T: Encodable>(path: String, body: T) async throws -> ApiResponse {
        guard let url = URL(string: "\(baseURL)\(path)") else {
            throw URLError(.badURL)
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        
        if httpResponse.statusCode == 200 {
            return try decoder.decode(ApiResponse.self, from: data)
        }
        
        return ApiResponse(ok: false, error: "HTTP \(httpResponse.statusCode)")
    }

    /// 字典版 POST（用于简单键值对请求，如 process/start）
    private func postDict(path: String, dict: [String: String]) async throws -> ApiResponse {
        guard let url = URL(string: "\(baseURL)\(path)") else {
            throw URLError(.badURL)
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: dict)

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            return ApiResponse(ok: false, error: "HTTP \((response as? HTTPURLResponse)?.statusCode ?? 0)")
        }

        return try decoder.decode(ApiResponse.self, from: data)
    }
}
