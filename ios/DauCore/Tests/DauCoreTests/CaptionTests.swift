import Testing
@testable import DauCore

@Suite("phrases")
struct PhraseTests {
    /// The expected tone of every syllable comes from its spelling — no annotation needed,
    /// and no second source of truth to drift.
    @Test("a phrase derives its tones from the text")
    func derivesTonesFromText() {
        let phrase = Phrase(
            id: "dinner", text: "Tối nay tôi về nhà ăn cơm với má.",
            gloss: "Tonight I'm going home to eat with Mom."
        )
        let syllables = phrase.syllables
        #expect(syllables.count == 9)
        #expect(syllables.map(\.surface) == ["Tối", "nay", "tôi", "về", "nhà", "ăn", "cơm", "với", "má"])
        #expect(syllables.map(\.tone) == [
            .sac, .ngang, .ngang, .huyen, .huyen, .ngang, .ngang, .sac, .sac,
        ])
        // Trailing punctuation must not become part of the word.
        #expect(syllables.last?.surface == "má")
    }
}

@Suite("captions")
struct CaptionTests {
    private static func phrase() -> [PhraseSyllable] {
        Phrase.syllables(in: "ma mà má")
    }

    private static func reading(count: Int) -> PhraseToneReading {
        PhraseToneReading(
            syllables: (0..<count).map { _ in
                ToneShapeJudge.read(features: SyntheticContour.features(SyntheticContour.level).contour)
            },
            syllableRanges: (0..<count).map { $0..<($0 + 1) }
        )
    }

    @Test("a word said correctly reads as matched")
    func matchedWord() {
        let words = CaptionBuilder.build(
            phrase: Self.phrase(), reading: Self.reading(count: 3), accent: .south,
            features: { index in
                // Each syllable produced exactly its own tone.
                switch index {
                case 0: SyntheticContour.features(SyntheticContour.level)
                case 1: SyntheticContour.features(SyntheticContour.fall(4))
                default: SyntheticContour.features(SyntheticContour.rise(4))
                }
            }
        )
        #expect(words.map(\.state) == [.matched, .matched, .matched])
        #expect(words.map(\.display) == ["ma", "mà", "má"])
        #expect(CaptionBuilder.shortfallNote(words: words) == nil)
    }

    /// The caption shows what was *said*, not what was meant — the same rule free-speech
    /// captions will follow when recognition supplies word identity.
    @Test("a missed word is rewritten with the tone that was measured")
    func missedWordShowsWhatWasSaid() {
        let words = CaptionBuilder.build(
            phrase: Self.phrase(), reading: Self.reading(count: 3), accent: .south,
            // Every syllable came out level.
            features: { _ in SyntheticContour.features(SyntheticContour.level) }
        )
        #expect(words[0].state == .matched)
        // mà (huyền) said level -> shown as ma, the word actually produced.
        #expect(words[1].isMissed)
        #expect(words[1].display == "ma")
        #expect(words[2].isMissed)
        #expect(words[2].display == "ma")
    }

    /// A phrase that reads short must say so rather than looking complete.
    @Test("an unread tail is reported, not hidden")
    func shortfallIsReported() {
        let words = CaptionBuilder.build(
            phrase: Self.phrase(), reading: Self.reading(count: 1), accent: .south,
            features: { _ in SyntheticContour.features(SyntheticContour.level) }
        )
        #expect(words[0].state == .matched)
        #expect(words[1].state == .pending)
        #expect(words[2].state == .pending)
        #expect(CaptionBuilder.shortfallNote(words: words) == "We read 1 of your 3 words — try a slightly slower pass.")
    }

    @Test("no reading at all leaves every word pending")
    func noReadingLeavesPending() {
        let words = CaptionBuilder.build(
            phrase: Self.phrase(), reading: nil, accent: .south, features: { _ in nil }
        )
        #expect(words.allSatisfy { $0.state == .pending })
        #expect(CaptionBuilder.shortfallNote(words: words) == nil)
    }

    /// A syllable the judge cannot read is `unread`, never silently a miss. Guessing here
    /// would put a wrong word on screen with full confidence.
    @Test("an unreadable syllable is unread, not a miss")
    func unreadableIsNotAMiss() {
        let words = CaptionBuilder.build(
            phrase: Self.phrase(), reading: Self.reading(count: 3), accent: .south,
            features: { index in index == 1 ? nil : SyntheticContour.features(SyntheticContour.level) }
        )
        #expect(words[1].state == .unread)
        #expect(words[1].isMissed == false)
        #expect(words[1].display == "mà", "an unread word shows what was asked for, unchanged")
    }
}
