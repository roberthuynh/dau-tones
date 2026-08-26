import SwiftUI

/// Screen 01 — three taps, no account. Built out in A4.
struct FirstRunView: View {
    var onContinue: () -> Void

    var body: some View {
        ZStack {
            DauTheme.ground.ignoresSafeArea()
            VStack(spacing: 16) {
                Text("Dấu")
                    .font(.system(size: 44, weight: .bold))
                    .foregroundStyle(DauTheme.cream)
                Text("See your tones")
                    .font(.caption.bold())
                    .tracking(2)
                    .foregroundStyle(DauTheme.faint)
                Button("Say your first word", action: onContinue)
                    .font(.headline)
                    .foregroundStyle(DauTheme.onCoral)
                    .frame(maxWidth: .infinity, minHeight: 58)
                    .background(DauTheme.coral, in: Capsule())
                    .padding(.top, 24)
            }
            .padding(24)
        }
    }
}
