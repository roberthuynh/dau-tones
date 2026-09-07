import SwiftUI

/// Tabs from the v1 canvas: Practice · Words · You.
///
/// Onboarding (screen 01) gates the shell until an accent is chosen; `-skipOnboarding` jumps
/// straight to the tabs for UITests and screenshots.
struct RootView: View {
    @Environment(DauSettings.self) private var settings
    @Environment(QuestProgressStore.self) private var quest
    @State private var selection: Tab = .today

    enum Tab: Hashable { case today, learn, you }

    var body: some View {
        Group {
            if settings.hasOnboarded {
                TabView(selection: $selection) {
                    QuestHomeView()
                        .tabItem { Label("Today", systemImage: "sun.max.fill") }
                        .tag(Tab.today)
                    LearnView()
                        .tabItem { Label("Learn", systemImage: "book.pages.fill") }
                        .tag(Tab.learn)
                    YouView()
                        .tabItem { Label("You", systemImage: "person.fill") }
                        .tag(Tab.you)
                }
                .tint(DauTheme.jade)
            } else {
                FirstRunView()
            }
        }
        .background(DauTheme.ground)
        .safeAreaInset(edge: .top) {
            if let error = quest.saveError {
                Text(error).font(.footnote).foregroundStyle(DauTheme.missed)
                    .padding().frame(maxWidth: .infinity).background(DauTheme.card)
            }
        }
    }
}
