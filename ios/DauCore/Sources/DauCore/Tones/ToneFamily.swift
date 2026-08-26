import Foundation

/// The four pitch-observable families the six orthographic tones collapse into.
///
/// Ported from `api/dau/tones.py::tone_family`. Northern ngã groups with rising sắc when
/// glottal cues are not conclusive; in common Southern speech hỏi and ngã merge, so they
/// share the dipping family.
///
/// Families — not tones — are what the contour judge reads, because that is what pitch alone
/// can honestly support. See `VerdictPolicy` for when a family resolves back to a nameable
/// word and when it must not.
public enum ToneFamily: String, Codable, Sendable, CaseIterable, Hashable {
    case level
    case rising
    case falling
    case dipping

    /// How the family is described to a learner when the exact tone is not resolvable.
    public var shapeDescription: String {
        switch self {
        case .level: "level"
        case .rising: "rising"
        case .falling: "falling"
        case .dipping: "dipping"
        }
    }
}

public extension ToneMark {
    /// The pitch family this tone belongs to for `accent`.
    func family(in accent: Accent) -> ToneFamily {
        switch self {
        case .ngang: .level
        case .huyen, .nang: .falling
        case .sac: .rising
        case .nga: accent == .south ? .dipping : .rising
        case .hoi: .dipping
        }
    }
}

public extension ToneFamily {
    /// Tones of `accent` that produce this family.
    func tones(in accent: Accent) -> [ToneMark] {
        ToneMark.allCases.filter { $0.family(in: accent) == self }
    }

    /// The single tone this family implies for `accent`, or nil when more than one tone
    /// produces it.
    ///
    /// This is the honesty gate for naming a word the learner did not mean. It resolves
    /// uniquely for level (ngang, both accents), rising (sắc, South only — North shares it
    /// with ngã), and dipping (hỏi in the North; in the South hỏi and ngã genuinely merge,
    /// so no unique answer exists and none is claimed). Falling never resolves: huyền and
    /// nặng are separated by duration and final energy, not by contour shape alone.
    func unambiguousTone(in accent: Accent) -> ToneMark? {
        let candidates = tones(in: accent)
        return candidates.count == 1 ? candidates[0] : nil
    }
}
