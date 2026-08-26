import SwiftUI

/// Placeholder — built out in the phase this screen belongs to. See the plan's build order.
struct TodayView: View {
    var body: some View {
        ZStack {
            DauTheme.ground.ignoresSafeArea()
            Text("Today")
                .font(.largeTitle.bold())
                .foregroundStyle(DauTheme.cream)
        }
    }
}
