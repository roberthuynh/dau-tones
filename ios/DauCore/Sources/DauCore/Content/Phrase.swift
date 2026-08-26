import Foundation

/// A short phrase to say aloud, for the captions screen.
///
/// Deliberately carries no per-word tone annotations. Vietnamese writes its tones, so the
/// expected tone of every syllable is derivable from the spelling via `ToneMark.of(_:)` —
/// authoring them separately would only create a second source of truth to drift.
public struct Phrase: Codable, Equatable, Sendable, Identifiable {
    public let id: String
    public let text: String
    public let gloss: String
    /// Inventory word ids this phrase drills, when any.
    public let wordIDs: [String]

    public init(id: String, text: String, gloss: String, wordIDs: [String] = []) {
        self.id = id
        self.text = text
        self.gloss = gloss
        self.wordIDs = wordIDs
    }

    /// The phrase split into spoken syllables, each carrying the tone its spelling implies.
    public var syllables: [PhraseSyllable] { Phrase.syllables(in: text) }

    public static func syllables(in text: String) -> [PhraseSyllable] {
        text
            .split(whereSeparator: { $0.isWhitespace })
            .map { token in
                let surface = token.trimmingCharacters(in: .punctuationCharacters)
                return PhraseSyllable(surface: surface, tone: ToneMark.of(surface))
            }
            .filter { !$0.surface.isEmpty }
    }
}

public struct PhraseSyllable: Equatable, Sendable {
    public let surface: String
    public let tone: ToneMark

    public init(surface: String, tone: ToneMark) {
        self.surface = surface
        self.tone = tone
    }
}
