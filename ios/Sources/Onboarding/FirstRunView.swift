import DauCore
import SwiftUI

/// Screen 01 — three taps, no account, and the privacy claim stated as the pitch rather than
/// buried in a policy. The target is a graded word inside 30 seconds.
struct FirstRunView: View {
    @Environment(DauSettings.self) private var settings
    @Environment(ContentStore.self) private var store
    @State private var chosenAccent: Accent = .south

    var body: some View {
        ScrollView {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 4) {
                Text("VietQuest")
                    .font(.largeTitle.bold())
                    .foregroundStyle(DauTheme.ink)
                Text("SPEAK WITH A PURPOSE")
                    .font(.caption.bold())
                    .tracking(2)
                    .foregroundStyle(DauTheme.faint)
            }

            Image("cafe-scene")
                .resizable()
                .scaledToFill()
                .frame(height: 170)
                .clipShape(RoundedRectangle(cornerRadius: 24))
                .padding(.top, 18)

            Text("Vietnamese for the moments that matter.")
                .font(.title.bold())
                .foregroundStyle(DauTheme.ink)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 30)

            Text("Learn through short, useful missions. Your first stop is a Southern Vietnamese café.")
                .font(.system(.subheadline))
                .foregroundStyle(DauTheme.muted)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 6)

            Text("TONE STUDIO ACCENT")
                .font(.system(.caption).weight(.bold))
                .tracking(1.8)
                .foregroundStyle(DauTheme.faint)
                .padding(.top, 26)

            HStack(spacing: 10) {
                ForEach(Accent.allCases, id: \.self) { accent in
                    accentCard(accent)
                }
            }
            .padding(.top, 10)

            privacyCard.padding(.top, 14)

            Spacer(minLength: 20)

            Button {
                settings.accent = chosenAccent
                settings.hasOnboarded = true
            } label: {
                Text("Start my first mission")
                    .font(.system(.body).weight(.bold))
                    .foregroundStyle(DauTheme.onCoral)
                    .frame(maxWidth: .infinity, minHeight: 58)
                    .background(DauTheme.coral, in: Capsule())
            }
            .accessibilityIdentifier("startButton")

            Text("No sign-up · works offline")
                .font(.system(.caption))
                .foregroundStyle(DauTheme.faint)
                .frame(maxWidth: .infinity)
                .padding(.top, 10)
        }
        .padding(.horizontal, 24)
        .padding(.top, 24)
        .padding(.bottom, 40)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        }
        .background(DauTheme.ground.ignoresSafeArea())
        .onAppear { chosenAccent = settings.accent }
    }

    private var toneStrip: some View {
        HStack(spacing: 8) {
            ForEach(store.sixMaWords) { word in
                VStack(spacing: 4) {
                    ToneContourGlyph(tone: word.tone.glyphMark(for: chosenAccent), width: 34)
                    Text(word.syllable)
                        .font(.system(.caption))
                        .foregroundStyle(DauTheme.faint)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 10)
                .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(DauTheme.hairline, lineWidth: 1))
            }
        }
    }

    private func accentCard(_ accent: Accent) -> some View {
        let isChosen = chosenAccent == accent
        return Button {
            chosenAccent = accent
        } label: {
            VStack(alignment: .leading, spacing: 2) {
                Text(accent.label)
                    .font(.system(.title3).weight(.bold))
                    .foregroundStyle(DauTheme.ink)
                Text("\(accent.city) · \(accent.spokenToneCount) tones")
                    .font(.system(.footnote))
                    .foregroundStyle(isChosen ? DauTheme.muted : DauTheme.faint)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 18)
            .padding(.vertical, 16)
            .background(
                isChosen ? DauTheme.coral.opacity(0.12) : DauTheme.card,
                in: RoundedRectangle(cornerRadius: 18)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 18)
                    .stroke(isChosen ? DauTheme.coral : DauTheme.hairline, lineWidth: 1.5)
            )
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("accent-\(accent.rawValue)")
        .accessibilityAddTraits(isChosen ? [.isSelected] : [])
    }

    private var privacyCard: some View {
        HStack(spacing: 12) {
            Image(systemName: "mic.fill")
                .font(.system(.body))
                .foregroundStyle(DauTheme.verified)
                .frame(width: 38, height: 38)
                .background(DauTheme.verified.opacity(0.14), in: RoundedRectangle(cornerRadius: 12))
            // The claim is the product, so it leads. Everything in the app is built to keep
            // it true — there is no network client to turn off.
            Text("**Your voice stays on this iPhone.** Mission recordings are local and temporary — no audio uploads, no account.")
                .font(.system(.footnote))
                .foregroundStyle(DauTheme.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(DauTheme.hairline, lineWidth: 1))
    }
}
