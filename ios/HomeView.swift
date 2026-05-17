import SwiftUI

struct HomeView: View {
    @EnvironmentObject var viewModel: ArticlesViewModel
    @StateObject private var socialViewModel = SocialPostsViewModel.shared
    @StateObject private var savedViewModel = SupabaseArticlesViewModel.shared
    @State private var selectedTab = 0

    var body: some View {
        TabView(selection: $selectedTab) {
            HomeTabView(selectedTab: $selectedTab)
                .environmentObject(viewModel)
                .tabItem { Label("Home", systemImage: "house") }
                .tag(0)

            NewsListView()
                .environmentObject(viewModel)
                .tabItem { Label("Noticias", systemImage: "newspaper") }
                .tag(1)

            SocialPostsView(viewModel: socialViewModel)
                .tabItem { Label("RRSS", systemImage: "square.and.pencil") }
                .tag(2)

            NewsletterView()
                .tabItem { Label("Newsletter", systemImage: "envelope.open.fill") }
                .tag(3)
        }
        .onAppear {
            if viewModel.articles.isEmpty {
                Task { await viewModel.loadArticles() }
            }
        }
    }
}

// MARK: - Home Launcher
struct HomeTabView: View {
    @Binding var selectedTab: Int
    @StateObject private var savedViewModel = SupabaseArticlesViewModel.shared
    @StateObject private var socialViewModel = SocialPostsViewModel.shared
    @State private var showCalendario = false
    @State private var showNewsletter = false
    @State private var showVideos = false
    @State private var showAlex = false

    private let columns = [GridItem(.flexible(), spacing: 16), GridItem(.flexible(), spacing: 16)]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                // Cabecera
                VStack(alignment: .leading, spacing: 4) {
                    Text("NewsFlow")
                        .font(.system(size: 34, weight: .bold, design: .default))
                    Text("Basketouch Solutions Spain")
                        .font(.system(size: 13, weight: .regular, design: .monospaced))
                        .foregroundColor(.secondary)
                        .textCase(.uppercase)
                        .kerning(0.5)
                }
                .padding(.top, 16)

                // Grid de accesos
                LazyVGrid(columns: columns, spacing: 16) {
                    HomeTile(icon: "newspaper", color: .blue,
                        title: "Noticias", subtitle: "RSS en tiempo real") {
                        selectedTab = 1
                    }

                    HomeTile(icon: "square.and.pencil",
                        color: Color(red: 0.49, green: 0.23, blue: 0.93),
                        title: "RRSS", subtitle: "LinkedIn · X con IA") {
                        selectedTab = 2
                    }

                    HomeTile(icon: "envelope.open.fill",
                        color: Color(red: 0.91, green: 0.25, blue: 0.11),
                        title: "Newsletter", subtitle: "INSIDE Life") {
                        selectedTab = 3
                    }

                    HomeTile(icon: "calendar",
                        color: Color(red: 0.85, green: 0.47, blue: 0.02),
                        title: "Calendario", subtitle: "Planifica tus publicaciones") {
                        showCalendario = true
                    }

                    HomeTile(icon: "play.rectangle.fill",
                        color: Color(red: 0.85, green: 0.1, blue: 0.1),
                        title: "Videos", subtitle: "Drive · Galería → RRSS") {
                        showVideos = true
                    }

                    HomeTile(icon: "safari",
                        color: Color(red: 0.0, green: 0.48, blue: 1.0),
                        title: "INSIDE Life", subtitle: "insidelife.club/newsletter") {
                        showNewsletter = true
                    }
                }

                // Alex — tile ancho completo
                Button { showAlex = true } label: {
                    HStack(spacing: 14) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 14)
                                .fill(Color.purple.opacity(0.12))
                                .frame(width: 56, height: 56)
                            Text("⚡")
                                .font(.system(size: 26))
                        }
                        VStack(alignment: .leading, spacing: 3) {
                            Text("Alex")
                                .font(.system(size: 17, weight: .semibold))
                                .foregroundColor(.primary)
                            Text("Asistente operativo IA · NewsFlow")
                                .font(.system(size: 12))
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(Color(.tertiaryLabel))
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity)
                    .background(Color(.secondarySystemGroupedBackground))
                    .cornerRadius(18)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 20)
        }
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
        .sheet(isPresented: $showCalendario) {
            NavigationStack {
                SocialPostsCalendarView(viewModel: socialViewModel)
                    .toolbar {
                        ToolbarItem(placement: .navigationBarTrailing) {
                            Button("Cerrar") { showCalendario = false }
                        }
                    }
            }
        }
        .sheet(isPresented: $showVideos) {
            VideosView()
        }
        .sheet(isPresented: $showNewsletter) {
            SafariView(
                url: URL(string: "https://insidelife.club/newsletter")!,
                showingCreatePost: .constant(false),
                webURLForPost: .constant(nil),
                webTitleForPost: .constant(nil)
            )
            .edgesIgnoringSafeArea(.all)
        }
        .sheet(isPresented: $showAlex) {
            AlexChatView()
        }
    }
}

// MARK: - Tile individual
struct HomeTile: View {
    let icon: String
    let color: Color
    let title: String
    let subtitle: String
    var badge: Int? = nil
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 0) {
                // Icono + badge
                ZStack(alignment: .topTrailing) {
                    RoundedRectangle(cornerRadius: 14)
                        .fill(color.opacity(0.12))
                        .frame(width: 56, height: 56)
                    Image(systemName: icon)
                        .font(.system(size: 26, weight: .medium))
                        .foregroundColor(color)
                    if let badge = badge {
                        Text("\(badge)")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundColor(.white)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(Color.red)
                            .clipShape(Capsule())
                            .offset(x: 6, y: -6)
                    }
                }
                .frame(width: 56, height: 56)
                .padding(.bottom, 14)

                // Texto
                Text(title)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(.primary)
                    .lineLimit(1)
                Text(subtitle)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 2)

                Spacer(minLength: 0)
            }
            .padding(16)
            .frame(maxWidth: .infinity, minHeight: 140, alignment: .topLeading)
            .background(Color(.secondarySystemGroupedBackground))
            .cornerRadius(18)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - More
struct MoreView: View {
    @ObservedObject var savedViewModel: SupabaseArticlesViewModel
    @ObservedObject var socialViewModel: SocialPostsViewModel

    var body: some View {
        NavigationStack {
            List {
                NavigationLink {
                    ArchivoView(viewModel: savedViewModel)
                        .navigationTitle("Archivo")
                } label: {
                    Label("Archivo", systemImage: "archivebox")
                }
                NavigationLink {
                    SocialPostsCalendarView(viewModel: socialViewModel)
                } label: {
                    Label("Calendario", systemImage: "calendar")
                }
            }
            .navigationTitle("More")
        }
    }
}

#Preview {
    HomeView()
        .environmentObject(ArticlesViewModel())
}
