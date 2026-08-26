import Foundation

/// One word in a live caption.
public struct CaptionWord: Equatable, Sendable, Identifiable {
    public enum State: Equatable, Sendable {
        /// The tone the spelling calls for was produced.
        case matched
        /// A different shape came out. Carries what was heard, when it can be named.
        case missed(produced: ToneMark?)
        /// Spoken, but not readable — too short, too quiet, or contradictory.
        case unread
        /// Not reached yet.
        case pending
    }

    public let id: Int
    public let expected: PhraseSyllable
    public let state: State
    /// What to render. For a missed word this is the syllable rewritten with the tone that
    /// was actually measured, so the caption shows what was said rather than what was meant.
    public let display: String

    public init(id: Int, expected: PhraseSyllable, state: State, display: String) {
        self.id = id
        self.expected = expected
        self.state = state
        self.display = display
    }

    public var isMissed: Bool {
        if case .missed = state { return true }
        return false
    }
}

/// Turns a phrase plus a per-syllable reading into the caption the learner sees.
///
/// This is the DSP-only path, and it is why screen 05 can ship without speech recognition at
/// all: for a phrase whose words are already known, segmentation supplies the timing and the
/// rule table supplies each verdict. No ASR, no permission prompt, no device-availability
/// risk. Free-speech captions are the same renderer with recognition supplying identity.
///
/// Alignment is positional, and honest about it: when the reader finds fewer runs than the
/// phrase has words, the remainder stay `pending` and the shortfall is stated. A phrase that
/// reads short must say so rather than silently looking complete.
public enum CaptionBuilder {
    public static func build(
        phrase: [PhraseSyllable],
        reading: PhraseToneReading?,
        accent: Accent,
        features: (Int) -> ToneTakeFeatures?
    ) -> [CaptionWord] {
        guard let reading else {
            return phrase.enumerated().map { index, syllable in
                CaptionWord(id: index, expected: syllable, state: .pending, display: syllable.surface)
            }
        }

        return phrase.enumerated().map { index, syllable in
            guard index < reading.syllables.count, let takeFeatures = features(index) else {
                return CaptionWord(
                    id: index, expected: syllable,
                    state: index < reading.syllables.count ? .unread : .pending,
                    display: syllable.surface
                )
            }
            let verdict = VerdictPolicy.judge(
                target: syllable.tone, accent: accent, features: takeFeatures
            )
            switch verdict.outcome {
            case .matched:
                return CaptionWord(id: index, expected: syllable, state: .matched, display: syllable.surface)
            case .missedNaming(let produced):
                // Show the word as it came out. Free-speech captions follow the same rule:
                // identity from the text, tone from the DSP.
                return CaptionWord(
                    id: index, expected: syllable, state: .missed(produced: produced),
                    display: ToneMark.applying(produced, to: syllable.surface)
                )
            case .missedShape:
                return CaptionWord(
                    id: index, expected: syllable, state: .missed(produced: nil),
                    display: syllable.surface
                )
            case .inconclusive:
                return CaptionWord(id: index, expected: syllable, state: .unread, display: syllable.surface)
            }
        }
    }

    /// "We read 6 of your 8 words" — said plainly when the take came up short.
    public static func shortfallNote(words: [CaptionWord]) -> String? {
        let read = words.filter { $0.state != .pending }.count
        guard read < words.count, read > 0 else { return nil }
        return "We read \(read) of your \(words.count) words — try a slightly slower pass."
    }
}
