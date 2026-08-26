import SwiftUI

/// Tabs from the v1 canvas: Practice · Words · You.
///
/// Onboarding (screen 01) gates the shell until an accent is chosen; `-skipOnboarding` jumps
/// straight to the tabs for UITests and screenshots.
struct RootView: View {
    @Environment(DauSettings.self) private var settings
    @State private var selection: Tab = .practice

    enum Tab: Hashable { case practice, words, you }

    var body: some View {
        Group {
            if settings.hasOnboarded {
                TabView(selection: $selection) {
                    TodayView()
                        .tabItem { Label("Practice", systemImage: "mic.fill") }
                        .tag(Tab.practice)
                    WordsView()
                        .tabItem { Label("Words", systemImage: "square.grid.2x2.fill") }
                        .tag(Tab.words)
                    YouView()
                        .tabItem { Label("You", systemImage: "person.fill") }
                        .tag(Tab.you)
                }
                .tint(DauTheme.coral)
            } else {
                FirstRunView()
            }
        }
        .background(DauTheme.ground)
    }
}
