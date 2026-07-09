/**
 * 音乐小车 — AI 编舞客户端（iOS / Swift）
 *
 * 调用小车后端 /api/choreograph/* 接口，实现 AI 生成 + 微调编舞。
 */

import Foundation

class AIChoreographer {
    private var baseURL: String = "http://\(AppConstants.defaultCarIP):\(AppConstants.defaultCarPort)"
    private let session: URLSession
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()
    
    init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = AppConstants.llmTimeout
        config.timeoutIntervalForResource = AppConstants.llmTimeout
        session = URLSession(configuration: config)
    }
    
    func setServer(ip: String, port: Int) {
        baseURL = "http://\(ip):\(port)"
    }
    
    /// AI 生成编舞
    func generate(_ req: ChoreographRequest) async -> ChoreographResponse {
        return await post(path: "/api/choreograph/generate", body: req)
    }
    
    /// AI 微调已有编舞
    func refine(routine: DanceRoutine, feedback: String) async -> ChoreographResponse {
        let data: [String: Any] = [
            "routine": try! JSONEncoder().encode(routine),
            "feedback": feedback
        ]
        return await post(path: "/api/choreograph/refine", body: data)
    }
    
    /// 校验编舞合法性（不调 LLM）
    func validate(_ routine: DanceRoutine) async -> ChoreographResponse {
        return await post(path: "/api/choreograph/validate", body: routine)
    }
    
    // MARK: - 内部
    
    struct PromptResponse: Codable {
        let ok: Bool
        var prompt: String? = nil
        var backend: String? = nil
    }
    
    /// 查看当前 System Prompt
    func getPrompt() async -> PromptResponse {
        guard let url = URL(string: "\(baseURL)/api/choreograph/prompt") else {
            return PromptResponse(ok: false)
        }
        do {
            let (data, _) = try await session.data(from: url)
            return try decoder.decode(PromptResponse.self, from: data)
        } catch {
            return PromptResponse(ok: false)
        }
    }
    
    private func post(path: String, body: Encodable) async -> ChoreographResponse {
        guard let url = URL(string: "\(baseURL)\(path)") else {
            return ChoreographResponse(ok: false, error: "无效 URL")
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        do {
            request.httpBody = try encoder.encode(AnyEncodable(body))
        } catch {
            return ChoreographResponse(ok: false, error: "编码错误: \(error.localizedDescription)")
        }
        
        do {
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else {
                return ChoreographResponse(ok: false, error: "HTTP 错误")
            }
            return try decoder.decode(ChoreographResponse.self, from: data)
        } catch {
            return ChoreographResponse(ok: false, error: "网络错误: \(error.localizedDescription)")
        }
    }
    
    private func post(path: String, body: [String: Any]) async -> ChoreographResponse {
        guard let url = URL(string: "\(baseURL)\(path)") else {
            return ChoreographResponse(ok: false, error: "无效 URL")
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        do {
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else {
                return ChoreographResponse(ok: false, error: "HTTP 错误")
            }
            return try decoder.decode(ChoreographResponse.self, from: data)
        } catch {
            return ChoreographResponse(ok: false, error: "网络错误: \(error.localizedDescription)")
        }
    }
}

// ── AnyEncodable 包装器 ─────────────────────

struct AnyEncodable: Encodable {
    let value: Encodable
    
    init(_ value: Encodable) {
        self.value = value
    }
    
    func encode(to encoder: Encoder) throws {
        try value.encode(to: encoder)
    }
}
