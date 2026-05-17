import Foundation

// MARK: - Models

struct AlexMessage: Identifiable, Equatable {
    let id = UUID()
    let role: String
    var content: String
}

enum AlexEvent {
    case text(String)
    case toolStart(String)
    case toolDone(String)
    case done
    case error(String)
}

// MARK: - Service

actor AlexService {
    static let shared = AlexService()

    private let baseURL = "https://openclaw.basketouch.com"
    private var token: String? = nil

    // MARK: Login

    func login() async throws {
        var req = URLRequest(url: URL(string: "\(baseURL)/api/login")!)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode([
            "username": Secrets.alexUsername,
            "password": Secrets.alexPassword,
        ])
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse, http.statusCode == 200 else {
            throw URLError(.userAuthenticationRequired)
        }
        let json = try JSONDecoder().decode([String: String].self, from: data)
        token = json["token"]
    }

    private func authToken() async throws -> String {
        if let t = token { return t }
        try await login()
        return token!
    }

    // MARK: Chat (SSE stream)

    func chat(messages: [[String: String]]) -> AsyncThrowingStream<AlexEvent, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    let t = try await authToken()
                    var req = URLRequest(url: URL(string: "\(baseURL)/api/chat")!)
                    req.httpMethod = "POST"
                    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    req.setValue("Bearer \(t)", forHTTPHeaderField: "Authorization")
                    req.httpBody = try JSONSerialization.data(withJSONObject: ["messages": messages])

                    let (bytes, response) = try await URLSession.shared.bytes(for: req)

                    if let http = response as? HTTPURLResponse, http.statusCode == 401 {
                        token = nil
                        throw URLError(.userAuthenticationRequired)
                    }

                    for try await line in bytes.lines {
                        guard line.hasPrefix("data: ") else { continue }
                        let raw = String(line.dropFirst(6)).trimmingCharacters(in: .whitespaces)
                        guard !raw.isEmpty,
                              let data = raw.data(using: .utf8),
                              let ev = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                              let type = ev["type"] as? String
                        else { continue }

                        switch type {
                        case "text":
                            if let c = ev["content"] as? String { continuation.yield(.text(c)) }
                        case "tool_start":
                            if let n = ev["name"] as? String { continuation.yield(.toolStart(n)) }
                        case "tool_done":
                            if let n = ev["name"] as? String { continuation.yield(.toolDone(n)) }
                        case "done":
                            continuation.yield(.done)
                        case "error":
                            if let m = ev["message"] as? String { continuation.yield(.error(m)) }
                        default:
                            break
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }
}
