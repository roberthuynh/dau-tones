import DauCore
import SwiftUI

/// Screen 04 — meaning first, then the acoustics, then exactly one physical fix.
///
/// Every string here comes from `VerdictCopy` in DauCore, so what the app is willing to claim
/// is decided (and unit-tested) in the engine rather than in a view. The three states are the
/// three the signal actually supports: matched, missed, and no verdict at all.
struct VerdictView: View {
    let verdict: ToneVerdict
    let word: DauContent.Word
    let learner: [Double]
    let reference: [Double]?
    var onRetry: () -> Void
    var onNext: () -> Void

    @Environment(ContentStore.self) private var store
    @Environment(DauSettings.self) private var settings

    /// The word the learner actually said, when the produced family names one. Nil is the
    /// common case and is not a failure — it means the shape did not resolve to a single
    /// tone, so no word is named.
    private var producedWord: DauContent.Word? {
        guard case .missedNaming(let tone) = verdict.outcome else { return nil }
        return store.content.word(base: word.asciiBase, tone: tone)
    }

    private var copyWord: VerdictCopy.Word {
        VerdictCopy.Word(surface: word.syllable, meaning: word.meaningEn)
    }

    private var accent: Color {
        switch verdict.outcome {
        case .matched: DauTheme.verified
        case .inconclusive: Color(hex: 0xF4A641)
        case .missedNaming, .missedShape: DauTheme.coral
        }
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                header.padding(.top, 8)
                if let produced = producedWord {
                    meaningSwap(produced: produced).padding(.top, 20)
                } else {
                    targetCard.padding(.top, 20)
                }
                traceCard.padding(.top, 14)
                if let note = ambiguityNote { ambiguityView(note).padding(.top, 12) }
                provenance.padding(.top, 12)
                actions.padding(.top, 22).padding(.bottom, 30)
            }
        }
        .scrollIndicators(.hidden)
    }

    private var header: some View {
        VStack(spacing: 8) {
            Text(VerdictCopy.eyebrow(for: verdict).uppercased())
                .font(.system(size: 12, weight: .bold))
                .tracking(1.8)
                .foregroundStyle(accent)
            Text(VerdictCopy.headline(
                for: verdict, target: copyWord,
                produced: producedWord.map { VerdictCopy.Word(surface: $0.syllable, meaning: $0.meaningEn) }
            ))
            .font(.system(size: 30, weight: .bold))
            .foregroundStyle(DauTheme.cream)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            Text(VerdictCopy.detail(for: verdict, target: copyWord))
                .font(.system(size: 15))
                .foregroundStyle(DauTheme.muted)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityIdentifier("verdictHeader")
    }

    /// The brand moment: what you meant, and what you actually said, side by side.
    private func meaningSwap(produced: DauContent.Word) -> some View {
        HStack(spacing: 12) {
            wordChip(word, label: "you meant", tint: DauTheme.faint)
            Image(systemName: "arrow.right")
                .font(.system(size: 15, weight: .bold))
                .foregroundStyle(DauTheme.faint)
            wordChip(produced, label: "you said", tint: DauTheme.coral)
        }
    }

    private func wordChip(_ word: DauContent.Word, label: String, tint: Color) -> some View {
        VStack(spacing: 6) {
            Text(label.uppercased())
                .font(.system(size: 10, weight: .bold))
                .tracking(1.2)
                .foregroundStyle(DauTheme.faint)
            ToneContourGlyph(tone: word.tone.glyphMark(for: settings.accent), width: 52)
            Text(word.syllable)
                .font(.system(size: 22, weight: .bold))
                .foregroundStyle(tint)
            Text(word.meaningEn)
                .font(.system(size: 12))
                .foregroundStyle(DauTheme.faint)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
        .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 20))
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(
            tint == DauTheme.coral ? DauTheme.coral.opacity(0.5) : DauTheme.hairline, lineWidth: 1
        ))
    }

    private var targetCard: some View {
        VStack(spacing: 6) {
            ToneContourGlyph(tone: word.tone.glyphMark(for: settings.accent), width: 104)
            Text("\(word.syllable) · \(word.meaningEn)")
                .font(.system(size: 17, weight: .bold))
                .foregroundStyle(verdict.isMatch ? DauTheme.verified : DauTheme.coral)
            Text("dấu \(word.tone.label) — the \(word.tone.hint) one")
                .font(.system(size: 12))
                .foregroundStyle(DauTheme.faint)
        }
        .frame(width: 210)
        .padding(.vertical, 16)
        .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 20))
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(
            verdict.isMatch ? DauTheme.verified.opacity(0.4) : DauTheme.hairline, lineWidth: 1
        ))
    }

    private var traceCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            ToneCurveView(
                target: reference,
                learner: learner,
                learnerColor: verdict.isMatch ? DauTheme.verified : DauTheme.cream
            )
            .frame(height: 110)
            HStack(alignment: .top, spacing: 10) {
                Text(VerdictCopy.physicalCue(for: word.tone))
                    .font(.system(size: 13.5))
                    .foregroundStyle(DauTheme.muted)
                Spacer(minLength: 0)
                // The number, when the signal supports one. It never leads, and it is
                // absent entirely rather than soft when the take could not be read.
                if let match = verdict.shapeMatch {
                    Text(VerdictCopy.shapeMatchLabel(match))
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(accent)
                        .fixedSize()
                        .accessibilityIdentifier("shapeMatch")
                }
            }
        }
        .padding(16)
        .background(DauTheme.well, in: RoundedRectangle(cornerRadius: 20))
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(DauTheme.hairline, lineWidth: 1))
    }

    private var ambiguityNote: String? {
        let candidates = store.content.minimalPairs(for: word)
            .filter { candidate in
                guard case .missedShape(let family) = verdict.outcome else { return false }
                return candidate.tone.family(in: settings.accent) == family
            }
            .map { VerdictCopy.Word(surface: $0.syllable, meaning: $0.meaningEn) }
        return VerdictCopy.ambiguityNote(for: verdict, candidates: candidates)
    }

    private func ambiguityView(_ note: String) -> some View {
        Text(note)
            .font(.system(size: 13))
            .foregroundStyle(DauTheme.muted)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(14)
            .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 16))
    }

    private var provenance: some View {
        Text(VerdictCopy.provenance(for: verdict))
            .font(.system(size: 12))
            .foregroundStyle(DauTheme.faint)
    }

    private var actions: some View {
        VStack(spacing: 10) {
            Button(action: verdict.isMatch ? onNext : onRetry) {
                Text(verdict.isMatch ? "Next word" : "Try \(word.syllable) again")
                    .font(.system(size: 16.5, weight: .bold))
                    .foregroundStyle(DauTheme.onCoral)
                    .frame(maxWidth: .infinity, minHeight: 56)
                    .background(DauTheme.coral, in: Capsule())
            }
            .accessibilityIdentifier("primaryAction")
            HStack(spacing: 10) {
                if store.referenceAudioURL(word: word.id, accent: settings.accent) != nil {
                    secondaryButton("Hear \(settings.accent.label) target") {
                        if let url = store.referenceAudioURL(word: word.id, accent: settings.accent) {
                            ReferencePlayer.shared.play(url: url)
                        }
                    }
                }
                if !verdict.isMatch {
                    secondaryButton("Skip") { onNext() }
                }
            }
            if !word.hasReference(for: settings.accent) {
                Text("No \(settings.accent.label) recording of this one yet.")
                    .font(.system(size: 12))
                    .foregroundStyle(DauTheme.faint)
            }
        }
    }

    private func secondaryButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 14, weight: .bold))
                .foregroundStyle(Color(hex: 0xCDC4B4))
                .frame(maxWidth: .infinity, minHeight: 48)
                .overlay(Capsule().stroke(DauTheme.cream.opacity(0.14), lineWidth: 1))
        }
    }
}
