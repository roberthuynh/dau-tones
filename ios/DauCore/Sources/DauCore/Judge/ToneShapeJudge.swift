import Foundation

/// Reads the shape a learner actually produced out of a pitch contour, with no reference
/// recording involved.
///
/// The contour arriving here is already speaker-relative — semitones against the take's own
/// median F0 — so a rise reads as a rise on its own terms.
///
/// Ported from nghe's `ToneShape.swift`, which in turn took its thresholds from `dấu`'s
/// per-tone rule table. `dấu`'s **template classifier is deliberately not ported**: it names
/// one of six tones at 72% held-out accuracy, and a trainer that intermittently calls a good
/// ngang a huyền teaches the opposite of what it is for. Families are the level the method
/// honestly supports; `VerdictPolicy` decides when a family may be spoken of as a word.
///
/// Held-out accuracy against `dấu`'s 36 labelled takes, recomputed 2026-08-26 against the
/// current thresholds: **level 5/6, falling 13/13, rising 9/9, dipping 3/8 — 30/36.**
/// (nghe's `docs/research/tone-shape-calibration.md` still prints the pre-`16a46fbb` table
/// of 6/6, 13/13, 8/9, 3/8; it is stale.) `GoldenContourTests` pins every one of the six
/// misses by name so a threshold change that trades one for two becomes visible.
///
/// The dipping gap is classification, not arithmetic — the feature port agrees with `dấu`'s
/// own numbers to 1.8e-5. Every dipping miss ends 1 to 10 semitones ABOVE where it started,
/// which is not a Southern dip; that audio is TTS carrying `accent_family_verified: false`,
/// so its labels are intended tones rather than confirmed ones. The thresholds were
/// deliberately not tuned to fit it, and must not be.
public enum ToneShapeFamily: String, Equatable, Sendable, CaseIterable, Codable {
    case level
    case rising
    case falling
    case dipping
    /// Measured, but not any recognizable tone shape — usually too short, too quiet, or a
    /// wandering take. Surface as "try again", never as a verdict.
    case unclear

    /// The four-family view used for verdicts; `unclear` has no tone counterpart.
    public var toneFamily: ToneFamily? {
        switch self {
        case .level: .level
        case .rising: .rising
        case .falling: .falling
        case .dipping: .dipping
        case .unclear: nil
        }
    }
}

/// What the take looked like, in plain terms.
public struct ToneShapeReading: Equatable, Sendable {
    public let family: ToneShapeFamily
    /// End minus start, signed. This is the number that answers "did I drift?"
    public let driftSemitones: Double
    /// Total spread of the take.
    public let rangeSemitones: Double
    public let features: ToneContourFeatures

    public init(
        family: ToneShapeFamily,
        driftSemitones: Double,
        rangeSemitones: Double,
        features: ToneContourFeatures
    ) {
        self.family = family
        self.driftSemitones = driftSemitones
        self.rangeSemitones = rangeSemitones
        self.features = features
    }
}

public enum ToneShapeJudge {
    // Ported thresholds, in semitones (and semitones per syllable for slopes). Each pair is
    // the condition `dấu` requires for a take to pass AS that tone.
    static let levelMaximumSlope = 1.6
    static let levelMaximumRange = 2.4
    static let fallingMinimumDrop = 0.7
    static let fallingMaximumSlope = -0.7
    static let risingMinimumClimb = 1.0
    static let risingMinimumFinalRise = 0.7

    // A drift this decisive is a tone, not an unsteady hold, so it is read before the level
    // box gets a chance to claim it. Without this, level's 2.4-semitone range ceiling
    // swallows an ordinary Southern huyền — a held `Chào` drops about two semitones — and
    // the mirror answers "Level" to a clean fall. The looser falling/rising rules stay BELOW
    // level, so honest mic jitter on a ngang is still read as a held tone.
    //
    // This pair is also what makes `south ma-ghost` (a ngang drifting +1.12 st on a +1.23
    // slope) read as rising: it clears both by about a tenth of a semitone. That is the one
    // miss worth watching, because `ma` is the first cell of the six-ma grid and the word
    // the cold-open teaches.
    static let directionalOverrideDrift = 1.0
    static let directionalOverrideSlope = 0.9

    // For the dip these come from `dấu`'s Southern hỏi/ngã evidence test, not from its hỏi
    // acceptance rule. The acceptance rule asks "given you meant hỏi, did you produce it?"
    // and is too loose to tell shapes apart on its own: `dấu` settles ambiguity with template
    // matching, which is the part deliberately not ported. A gentle wobble clears a 0.45
    // recovery, so a steady take would be read as a dip. Requiring a real descent AND a real
    // climb back is what separates a V from an unsteady flat.
    static let dippingPositionRange = 0.25...0.70
    static let dippingMinimumDescent = 0.60
    static let dippingMinimumRecovery = 1.0

    /// Read a contour. Returns nil when there is not enough voiced signal to say anything.
    public static func read(contour: [Double?]) -> ToneShapeReading? {
        guard let features = ToneContourFeatures.of(contour: contour) else { return nil }
        return read(features: features)
    }

    public static func read(features: ToneContourFeatures) -> ToneShapeReading {
        ToneShapeReading(
            family: family(of: features),
            driftSemitones: features.end - features.start,
            rangeSemitones: features.pitchRange,
            features: features
        )
    }

    /// Order matters, and the dip has to be asked first. A symmetric dip starts and ends in
    /// the same place, so its overall slope is near zero and the level rule would claim it —
    /// which is how a hỏi/ngã take reads as a held tone. The dip test is strict enough that a
    /// steady take cannot pass it, so asking it first costs the level case nothing. After
    /// that: a plain fall bottoms out at the very end and a plain rise starts at its lowest,
    /// so neither lands inside the dip window.
    ///
    /// A decisive fall or climb is then asked BEFORE level, because level's box is wide
    /// enough (2.4 semitones) to contain a real Vietnamese tone. The gentler falling/rising
    /// rules stay after level, where they only see takes level already refused.
    public static func family(of features: ToneContourFeatures) -> ToneShapeFamily {
        if dippingPositionRange.contains(features.dipPosition),
           features.start - features.minimum >= dippingMinimumDescent,
           features.recovery >= dippingMinimumRecovery,
           // A dip comes back to about where it started; a rise ends above it. Without this,
           // a rising take that sags before it climbs is read as a dip, which measured 5 of
           // 9 rising takes in the calibration set.
           features.end - features.start < risingMinimumClimb {
            return .dipping
        }
        if features.end <= features.start - directionalOverrideDrift,
           features.slope <= -directionalOverrideSlope {
            return .falling
        }
        if features.end >= features.start + directionalOverrideDrift,
           features.slope >= directionalOverrideSlope {
            return .rising
        }
        if abs(features.slope) <= levelMaximumSlope, features.pitchRange <= levelMaximumRange {
            return .level
        }
        if features.end < features.start - fallingMinimumDrop,
           features.slope < fallingMaximumSlope {
            return .falling
        }
        if features.end > features.start + risingMinimumClimb,
           features.finalRise > risingMinimumFinalRise {
            return .rising
        }
        return .unclear
    }
}
