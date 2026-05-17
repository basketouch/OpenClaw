import SwiftUI

struct AlexChatView: View {
    @StateObject private var vm = AlexViewModel()
    @Environment(\.dismiss) private var dismiss
    @FocusState private var inputFocused: Bool

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                messagesSection
                Divider()
                inputBar
            }
            .navigationTitle("Alex")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { toolbarContent }
            .background(Color(.systemGroupedBackground).ignoresSafeArea())
        }
    }

    // MARK: - Messages

    private var messagesSection: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    if vm.messages.isEmpty { welcomeView }

                    ForEach(vm.messages) { msg in
                        MessageRow(message: msg)
                            .id(msg.id)
                    }

                    if !vm.activeTools.isEmpty {
                        toolsRow
                    }

                    Color.clear.frame(height: 8).id("bottom")
                }
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 8)
            }
            .onChange(of: vm.messages.count) { _ in scroll(proxy) }
            .onChange(of: vm.messages.last?.content) { _ in scroll(proxy) }
        }
    }

    private func scroll(_ proxy: ScrollViewProxy) {
        withAnimation(.easeOut(duration: 0.15)) {
            proxy.scrollTo("bottom", anchor: .bottom)
        }
    }

    // MARK: - Welcome

    private var welcomeView: some View {
        VStack(spacing: 12) {
            Text("⚡").font(.system(size: 44))
            Text("Hola, soy Alex")
                .font(.system(size: 22, weight: .bold))
            Text("Accedo a tus artículos, posts y newsletter.\n¿En qué trabajamos?")
                .font(.system(size: 14))
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            VStack(spacing: 8) {
                ForEach(suggestions, id: \.self) { s in
                    Button {
                        vm.inputText = s
                        Task { await vm.sendMessage() }
                    } label: {
                        Text(s)
                            .font(.system(size: 13))
                            .foregroundColor(.primary)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 8)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color(.secondarySystemGroupedBackground))
                            .cornerRadius(10)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.top, 40)
        .padding(.bottom, 20)
        .frame(maxWidth: .infinity)
    }

    private let suggestions = [
        "¿Qué artículos tengo pendientes?",
        "Crea un post de LinkedIn con el último artículo",
        "¿Cuál es el estado del newsletter esta semana?",
        "Resume los vídeos en la cola de publicación",
    ]

    // MARK: - Tool indicators

    private var toolsRow: some View {
        HStack(spacing: 6) {
            ForEach(vm.activeTools, id: \.self) { tool in
                HStack(spacing: 4) {
                    ProgressView().scaleEffect(0.65)
                    Text(tool).font(.system(size: 11, weight: .medium))
                }
                .foregroundColor(.purple)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(Color.purple.opacity(0.1))
                .cornerRadius(8)
            }
        }
        .padding(.leading, 40)
    }

    // MARK: - Input bar

    private var inputBar: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("Escribe un mensaje…", text: $vm.inputText, axis: .vertical)
                .font(.system(size: 15))
                .lineLimit(1...6)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(Color(.secondarySystemGroupedBackground))
                .cornerRadius(22)
                .focused($inputFocused)

            Button {
                Task { await vm.sendMessage() }
            } label: {
                Image(systemName: vm.isLoading ? "stop.circle.fill" : "arrow.up.circle.fill")
                    .font(.system(size: 34))
                    .foregroundColor(canSend ? .purple : Color(.systemGray4))
            }
            .disabled(!canSend)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .padding(.bottom, 4)
        .background(Color(.systemGroupedBackground))
    }

    private var canSend: Bool {
        !vm.inputText.trimmingCharacters(in: .whitespaces).isEmpty && !vm.isLoading
    }

    // MARK: - Toolbar

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .navigationBarLeading) {
            Button("Cerrar") { dismiss() }
        }
        ToolbarItem(placement: .navigationBarTrailing) {
            Button {
                vm.newConversation()
            } label: {
                Image(systemName: "square.and.pencil")
            }
        }
    }
}

// MARK: - Message bubble

struct MessageRow: View {
    let message: AlexMessage

    private var isUser: Bool { message.role == "user" }
    private var isEmpty: Bool { message.content.isEmpty }

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            if isUser { Spacer(minLength: 56) }

            if !isUser {
                ZStack {
                    Circle()
                        .fill(Color.purple.opacity(0.15))
                        .frame(width: 30, height: 30)
                    Text("⚡").font(.system(size: 14))
                }
            }

            Text(isEmpty ? "▌" : message.content)
                .font(.system(size: 15))
                .foregroundColor(isUser ? .white : .primary)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(isUser ? Color.purple : Color(.secondarySystemGroupedBackground))
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                .textSelection(.enabled)

            if !isUser { Spacer(minLength: 56) }
        }
    }
}
