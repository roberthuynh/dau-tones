import Foundation

/// The six Vietnamese tones. Raw values stay ASCII for JSON stability.
///
/// Ported from nghe (`Inventory/InventoryPlan.swift` + `Domain/VietnameseTone.swift`), merged
/// into one type. Detection reads the first tone-bearing combining mark in NFD; vowel-quality
/// marks (circumflex, breve, horn) are not tones, and no mark means ngang.
public enum ToneMark: String, Codable, Sendable, CaseIterable, Hashable {
    case ngang
    case sac
    case huyen
    case hoi
    case nga
    case nang

    /// Vietnamese display name ("sắc").
    public var label: String {
        switch self {
        case .ngang: "ngang"
        case .sac: "sắc"
        case .huyen: "huyền"
        case .hoi: "hỏi"
        case .nga: "ngã"
        case .nang: "nặng"
        }
    }

    /// One-word English pitch cue for contour chips.
    public var hint: String {
        switch self {
        case .ngang: "level"
        case .sac: "rises"
        case .huyen: "falls"
        case .hoi: "dips"
        case .nga: "broken"
        case .nang: "drops"
        }
    }

    /// The combining scalar this tone is written with, or nil for ngang (no mark).
    public var combiningScalar: Unicode.Scalar? {
        switch self {
        case .ngang: nil
        case .sac: Unicode.Scalar(0x0301)!
        case .huyen: Unicode.Scalar(0x0300)!
        case .hoi: Unicode.Scalar(0x0309)!
        case .nga: Unicode.Scalar(0x0303)!
        case .nang: Unicode.Scalar(0x0323)!
        }
    }

    /// The tone written on `text`.
    public static func of(_ text: String) -> ToneMark {
        for scalar in text.decomposedStringWithCanonicalMapping.unicodeScalars {
            switch scalar.value {
            case 0x0301: return .sac
            case 0x0300: return .huyen
            case 0x0309: return .hoi
            case 0x0303: return .nga
            case 0x0323: return .nang
            default: continue
            }
        }
        return .ngang
    }

    /// `text` with every tone mark removed — the toneless spelling.
    ///
    /// Phase B needs this: ASR normalizes tone diacritics (gpt-4o-transcribe wrote `mả` as
    /// `mã`, and Apple's recognizer normalizes too), so a caption takes word *identity* from
    /// recognition and re-applies the mark the DSP actually measured. See `CaptionRenderer`.
    public static func stripped(from text: String) -> String {
        let toneScalars: Set<UInt32> = [0x0301, 0x0300, 0x0309, 0x0303, 0x0323]
        var out = String.UnicodeScalarView()
        for scalar in text.decomposedStringWithCanonicalMapping.unicodeScalars
        where !toneScalars.contains(scalar.value) {
            out.append(scalar)
        }
        return String(out).precomposedStringWithCanonicalMapping
    }

    /// `text` rewritten to carry `tone`, replacing whatever mark it had.
    ///
    /// Placement follows Vietnamese orthography, which is not simply "the last vowel":
    ///  1. ê, ô and ơ take the mark whenever they appear (tiếng, tối, phường).
    ///  2. Otherwise a syllable closed by a consonant marks the last nucleus vowel (toán, ắn).
    ///  3. Otherwise an open syllable marks the *penultimate* vowel (cừa, mùa, kìa) — except
    ///     the glide onsets oa/oe/uy, which mark the last (hoà, khoẻ, thuý).
    ///  4. A single vowel takes it.
    public static func applying(_ tone: ToneMark, to text: String) -> String {
        let bare = stripped(from: text)
        guard let mark = tone.combiningScalar else { return bare }
        let chars = Array(bare)
        guard let anchor = toneAnchorIndex(in: chars) else { return bare }
        var view = String.UnicodeScalarView()
        for (i, character) in chars.enumerated() {
            if i == anchor {
                view.append(contentsOf: String(character).decomposedStringWithCanonicalMapping.unicodeScalars)
                view.append(mark)
            } else {
                view.append(contentsOf: String(character).unicodeScalars)
            }
        }
        return String(view).precomposedStringWithCanonicalMapping
    }

    private static let vowels: Set<Character> = Set("aăâeêioôơuưyAĂÂEÊIOÔƠUƯY")
    /// Vowels that always win the tone mark when present.
    private static let strongVowels: Set<Character> = Set("êôơÊÔƠ")
    /// Glide onsets whose open syllable marks the last vowel rather than the penultimate.
    private static let glideOnsets: Set<String> = ["oa", "oe", "uy"]

    /// Index of the character the tone mark attaches to.
    private static func toneAnchorIndex(in chars: [Character]) -> Int? {
        guard let start = chars.firstIndex(where: { vowels.contains($0) }) else { return nil }
        var end = start
        while end + 1 < chars.count, vowels.contains(chars[end + 1]) { end += 1 }

        if let strong = (start...end).first(where: { strongVowels.contains(chars[$0]) }) {
            return strong
        }
        let isClosed = end + 1 < chars.count
        if isClosed { return end }

        let nucleusLength: Int = end - start + 1
        guard nucleusLength >= 2 else { return start }
        let onset = String(chars[start...(start + 1)]).lowercased()
        if nucleusLength == 2, glideOnsets.contains(onset) { return end }
        return end - 1
    }
}
