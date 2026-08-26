import Foundation

/// Why a take failed to be the tone it was aiming at.
///
/// Raw values match `dấu`'s reason codes so the two engines stay legible to each other.
public enum ToneRuleFailure: String, Equatable, Sendable, CaseIterable, Codable {
    case notLevel = "not_level"
    case noFall = "no_fall"
    case noRise = "no_rise"
    case noDipRecovery = "no_dip_recovery"
    case noBrokenRise = "no_broken_rise"
    case noMergedDip = "no_merged_dip"
    case notShortLow = "not_short_low"
}

/// The per-target acceptance rules — "given you meant sắc, did you produce it?"
///
/// Ported from `api/dau/tones.py::_candidate_rule_failures`. This is the engine behind the
/// design's "sắc not detected" line, and it has no equivalent in nghe: nghe only ever needed
/// to describe a shape, while Dấu has to answer a question about a specific target.
///
/// This is the primary verdict path, and deliberately so. It asks a narrower, better-posed
/// question than the family classifier — which matters most exactly where the classifier is
/// weakest. Dipping is 3/8 as a classification but the hỏi acceptance rule is looser and
/// correctly scoped, so a learner drilling `phở` is judged on whether they dipped and
/// recovered, not on whether a classifier can pick their tone out of six.
public enum ToneRuleTable {
    /// Rules the take must satisfy to be accepted as `tone` in `accent`.
    /// An empty result means it passed.
    public static func failures(
        for tone: ToneMark,
        accent: Accent,
        features: ToneTakeFeatures
    ) -> [ToneRuleFailure] {
        let pitch = features.contour
        let energy = features.energy
        var reasons: [ToneRuleFailure] = []

        switch tone {
        case .ngang:
            if abs(pitch.slope) > 1.6 || pitch.pitchRange > 2.4 {
                reasons.append(.notLevel)
            }
        case .huyen:
            if pitch.end >= pitch.start - 0.7 || pitch.slope >= -0.7 {
                reasons.append(.noFall)
            }
        case .sac:
            if pitch.end <= pitch.start + 1.0 || pitch.finalRise <= 0.7 {
                reasons.append(.noRise)
            }
        case .hoi:
            if pitch.dipPosition < 0.25 || pitch.dipPosition > 0.82 || pitch.recovery < 0.45 {
                reasons.append(.noDipRecovery)
            }
        case .nga:
            // The one accent-split rule. Northern ngã is a broken rise; Southern ngã has
            // merged with hỏi into a single dipping tone, so it is judged as a dip.
            if accent == .north, pitch.end <= pitch.start + 0.8 {
                reasons.append(.noBrokenRise)
            }
            if accent == .south, pitch.recovery < 0.35 {
                reasons.append(.noMergedDip)
            }
        case .nang:
            if pitch.end >= pitch.start - 0.5
                || (energy.durationSeconds > 0.75 && energy.terminalEnergyDrop < 0.12) {
                reasons.append(.notShortLow)
            }
        }
        return reasons
    }

    public static func passes(
        _ tone: ToneMark,
        accent: Accent,
        features: ToneTakeFeatures
    ) -> Bool {
        failures(for: tone, accent: accent, features: features).isEmpty
    }

    /// Corroborating evidence for the merged Southern hỏi/ngã family, using pitch *and*
    /// creak. Ported from `_southern_dipping_family_evidence`.
    ///
    /// This is why the energy features are not optional: on glottalized Southern voice the
    /// dip often shows up as an energy notch or a voicing break rather than a clean pitch V,
    /// and pitch alone calls it flat.
    public static func southernDippingEvidence(
        for tone: ToneMark,
        features: ToneTakeFeatures
    ) -> Bool {
        guard tone == .hoi || tone == .nga else { return false }
        let pitch = features.contour
        let descent = pitch.start - pitch.minimum
        let hasDipShape = (0.25...0.70).contains(pitch.dipPosition)
            && descent >= 0.60
            && pitch.recovery >= 1.0
        let hasCreakEvidence = features.energy.centralRmsDip >= 0.20
            || features.energy.longestVoicingGapMs >= 40.0
        return hasDipShape && hasCreakEvidence
    }
}
