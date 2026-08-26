import SwiftUI

/// Placeholder — built out in the phase this screen belongs to. See the plan's build order.
struct WordsView: View {
    var body: some View {
        ZStack {
            DauTheme.ground.ignoresSafeArea()
            Text("Words")
                .font(.largeTitle.bold())
                .foregroundStyle(DauTheme.cream)
        }
    }
}
