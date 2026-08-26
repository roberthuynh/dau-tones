import Foundation

/// The word inventory the app ships with.
///
/// Generated at build time by `dau-tool build-content` from `api/data/inventory.json`, so the
/// web app and the iOS app cannot drift apart on what a word means or which tone it carries.
/// At 19 words this is a decoded-once JSON value — no SQLite, no migrations. Revisit only
/// past a few thousand words.
public struct DauContent: Codable, Equatable, Sendable {
    public static let currentSchemaVersion = 1

    public let schemaVersion: Int
    public let locale: String
    public let defaultAccent: Accent
    public let tones: [ToneInfo]
    public let words: [Word]
    public let minimalPairGroups: [MinimalPairGroup]
    public let themedDrills: [ThemedDrill]
    /// Word order for the first-run queue. The cold-open leans on the head of this list, so
    /// it starts with the six-ma set where verdicts are strongest and most nameable.
    public let featuredQueue: [String]

    public init(
        schemaVersion: Int, locale: String, defaultAccent: Accent, tones: [ToneInfo],
        words: [Word], minimalPairGroups: [MinimalPairGroup], themedDrills: [ThemedDrill],
        featuredQueue: [String]
    ) {
        self.schemaVersion = schemaVersion
        self.locale = locale
        self.defaultAccent = defaultAccent
        self.tones = tones
        self.words = words
        self.minimalPairGroups = minimalPairGroups
        self.themedDrills = themedDrills
        self.featuredQueue = featuredQueue
    }

    public struct ToneInfo: Codable, Equatable, Sendable {
        public let id: ToneMark
        public let nameVi: String
        public let nameEn: String
        public let markEn: String
        /// Hex colour from the design canvas.
        public let color: String
        /// One physical instruction, authored alongside the web app.
        public let physicalCue: String

        public init(
            id: ToneMark, nameVi: String, nameEn: String, markEn: String, color: String,
            physicalCue: String
        ) {
            self.id = id
            self.nameVi = nameVi
            self.nameEn = nameEn
            self.markEn = markEn
            self.color = color
            self.physicalCue = physicalCue
        }
    }

    public struct Word: Codable, Equatable, Sendable, Identifiable {
        public let id: String
        public let syllable: String
        public let asciiBase: String
        public let tone: ToneMark
        public let meaningEn: String
        public let alternateMeaningsEn: [String]
        public let usageNote: String
        public let minimalPairGroup: String?
        public let minimalPairIDs: [String]
        /// Accents that have a bundled reference recording for this word. South is missing
        /// `ma-grave` and `phuong-phoenix`, whose generation failed — a declared exception,
        /// surfaced honestly in the UI rather than hidden.
        public let referenceAccents: [Accent]

        public init(
            id: String, syllable: String, asciiBase: String, tone: ToneMark, meaningEn: String,
            alternateMeaningsEn: [String], usageNote: String, minimalPairGroup: String?,
            minimalPairIDs: [String], referenceAccents: [Accent]
        ) {
            self.id = id
            self.syllable = syllable
            self.asciiBase = asciiBase
            self.tone = tone
            self.meaningEn = meaningEn
            self.alternateMeaningsEn = alternateMeaningsEn
            self.usageNote = usageNote
            self.minimalPairGroup = minimalPairGroup
            self.minimalPairIDs = minimalPairIDs
            self.referenceAccents = referenceAccents
        }

        public func hasReference(for accent: Accent) -> Bool {
            referenceAccents.contains(accent)
        }
    }

    public struct MinimalPairGroup: Codable, Equatable, Sendable, Identifiable {
        public let id: String
        public let asciiBase: String
        public let title: String
        public let wordIDs: [String]

        public init(id: String, asciiBase: String, title: String, wordIDs: [String]) {
            self.id = id
            self.asciiBase = asciiBase
            self.title = title
            self.wordIDs = wordIDs
        }
    }

    public struct ThemedDrill: Codable, Equatable, Sendable, Identifiable {
        public let id: String
        public let title: String
        public let description: String
        public let wordIDs: [String]

        public init(id: String, title: String, description: String, wordIDs: [String]) {
            self.id = id
            self.title = title
            self.description = description
            self.wordIDs = wordIDs
        }
    }

    // MARK: - Lookup

    public func word(id: String) -> Word? { words.first { $0.id == id } }
    public func tone(_ mark: ToneMark) -> ToneInfo? { tones.first { $0.id == mark } }
    public func words(withTone tone: ToneMark) -> [Word] { words.filter { $0.tone == tone } }

    /// The six-ma set — one sound, six meanings. The product's icon and its map.
    public func sixMaGroup() -> MinimalPairGroup? {
        minimalPairGroups.first { $0.asciiBase == "ma" }
    }

    /// Words that contrast with `word` on tone alone — what the verdict shows when the
    /// learner said a different word than they meant.
    public func minimalPairs(for word: Word) -> [Word] {
        word.minimalPairIDs.compactMap { self.word(id: $0) }
    }

    /// The word `word`'s syllable becomes when spoken with `tone`, if the inventory has one.
    /// This is what turns "you produced a level tone" into "you said ma — ghost".
    public func word(base: String, tone: ToneMark) -> Word? {
        words.first { $0.asciiBase == base && $0.tone == tone }
    }
}

public extension DauContent {
    /// Decode from bundled JSON, failing loudly on a schema mismatch.
    ///
    /// Content is generated from in-repo source at build time, so a mismatch is a build bug,
    /// not a runtime condition — there is deliberately no fallback path to paper over it.
    static func decode(from data: Data) throws -> DauContent {
        let content = try JSONDecoder().decode(DauContent.self, from: data)
        guard content.schemaVersion == currentSchemaVersion else {
            throw ContentError.schemaMismatch(found: content.schemaVersion, expected: currentSchemaVersion)
        }
        return content
    }

    enum ContentError: Error, CustomStringConvertible {
        case schemaMismatch(found: Int, expected: Int)

        public var description: String {
            switch self {
            case let .schemaMismatch(found, expected):
                "dau-content schema \(found) but this build expects \(expected) — re-run `dau-tool build-content`."
            }
        }
    }
}
