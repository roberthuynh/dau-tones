import SwiftUI

/// Placeholder — built out in the phase this screen belongs to. See the plan's build order.
struct YouView: View {
    var body: some View {
        ZStack {
            DauTheme.ground.ignoresSafeArea()
            Text("Your tones")
                .font(.largeTitle.bold())
                .foregroundStyle(DauTheme.cream)
        }
    }
}
