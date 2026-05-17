import SwiftUI

@MainActor
class AlexViewModel: ObservableObject {
    @Published var messages: [AlexMessage] = []
    @Published var inputText: String = ""
    @Published var isLoading = false
    @Published var activeTools: [String] = []
    @Published var errorMessage: String? = nil

    func sendMessage() async {
        let text = inputText.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty, !isLoading else { return }

        inputText = ""
        messages.append(AlexMessage(role: "user", content: text))
        isLoading = true
        activeTools = []
        errorMessage = nil

        // Placeholder for streaming response
        messages.append(AlexMessage(role: "assistant", content: ""))
        let idx = messages.count - 1

        let history = messages.dropLast().map { ["role": $0.role, "content": $0.content] }

        do {
            for try await event in await AlexService.shared.chat(messages: Array(history)) {
                switch event {
                case .text(let chunk):
                    messages[idx].content += chunk
                case .toolStart(let name):
                    if !activeTools.contains(name) { activeTools.append(name) }
                case .toolDone(let name):
                    activeTools.removeAll { $0 == name }
                case .done:
                    break
                case .error(let msg):
                    messages[idx].content = "Error: \(msg)"
                }
            }
        } catch {
            messages[idx].content = messages[idx].content.isEmpty
                ? "Error de conexión: \(error.localizedDescription)"
                : messages[idx].content
        }

        isLoading = false
        activeTools = []

        // Remove empty assistant message if nothing came back
        if messages.last?.content.isEmpty == true {
            messages.removeLast()
        }
    }

    func newConversation() {
        messages = []
        inputText = ""
        activeTools = []
        errorMessage = nil
    }
}
