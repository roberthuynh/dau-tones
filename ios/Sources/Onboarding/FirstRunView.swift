import DauCore
import SwiftUI

/// Screen 01 — three taps, no account, and the privacy claim stated as the pitch rather than
/// buried in a policy. The target is a graded word inside 30 seconds.
struct FirstRunView: View {
    @Environment(DauSettings.self) private var settings
    @Environment(ContentStore.self) private var store
    @State private var chosenAccent: Accent = .south

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text("Dấu")
                    .font(.system(size: 44, weight: .bold))
                    .foregroundStyle(DauTheme.cream)
                Text("SEE YOUR TONES")
                    .font(.system(size: 13, weight: .bold))
                    .tracking(2)
                    .foregroundStyle(DauTheme.faint)
            }

            toneStrip.padding(.top, 22)

            Text("One sound. Six meanings.\nYour pitch decides.")
                .font(.system(size: 27, weight: .bold))
                .foregroundStyle(DauTheme.cream)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 30)

            Text("Say a word and watch your pitch trace against a native speaker's — then see the word you actually said.")
                .font(.system(size: 15))
                .foregroundStyle(DauTheme.muted)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 6)

            Text("WHICH VIETNAMESE DO YOU WANT?")
                .font(.system(size: 12, weight: .bold))
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
                Text("Say your first word")
                    .font(.system(size: 17, weight: .bold))
                    .foregroundStyle(DauTheme.onCoral)
                    .frame(maxWidth: .infinity, minHeight: 58)
                    .background(DauTheme.coral, in: Capsule())
            }
            .accessibilityIdentifier("startButton")

            Text("Takes 30 seconds · no sign-up")
                .font(.system(size: 12.5))
                .foregroundStyle(DauTheme.faint)
                .frame(maxWidth: .infinity)
                .padding(.top, 10)
        }
        .padding(.horizontal, 24)
        .padding(.top, 60)
        .padding(.bottom, 40)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(DauTheme.ground.ignoresSafeArea())
        .onAppear { chosenAccent = settings.accent }
    }

    private var toneStrip: some View {
        HStack(spacing: 8) {
            ForEach(store.sixMaWords) { word in
                VStack(spacing: 4) {
                    ToneContourGlyph(tone: word.tone.glyphMark(for: chosenAccent), width: 34)
                    Text(word.syllable)
                        .font(.system(size: 12))
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
                    .font(.system(size: 19, weight: .bold))
                    .foregroundStyle(isChosen ? DauTheme.cream : Color(hex: 0xCDC4B4))
                Text("\(accent.city) · \(accent.spokenToneCount) tones")
                    .font(.system(size: 13))
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
                .font(.system(size: 17))
                .foregroundStyle(DauTheme.verified)
                .frame(width: 38, height: 38)
                .background(DauTheme.verified.opacity(0.14), in: RoundedRectangle(cornerRadius: 12))
            // The claim is the product, so it leads. Everything in the app is built to keep
            // it true — there is no network client to turn off.
            Text("**Your voice never leaves this iPhone.** Pitch grading runs on-device — no audio uploads, no account.")
                .font(.system(size: 13))
                .foregroundStyle(DauTheme.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(DauTheme.hairline, lineWidth: 1))
    }
}
