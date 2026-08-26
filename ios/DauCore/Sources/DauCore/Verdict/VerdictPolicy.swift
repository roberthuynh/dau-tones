import Foundation

/// Turns measurements into a verdict — and decides what may honestly be claimed.
///
/// The whole product position rests here. Competitors return a confident number; Dấu returns
/// what the signal supports, which sometimes is "say it again". Three rules govern it:
///
///  1. **The acceptance rule is primary.** "Given you meant sắc, did you produce it?" is a
///     better-posed question than "which of six tones was that?", and it is strongest exactly
///     where the family classifier is weakest.
///  2. **A word is only named when the family resolves uniquely** for that accent. See
///     `ToneFamily.unambiguousTone(in:)` — level always resolves, rising resolves only in the
///     South, dipping only in the North, falling never.
///  3. **Contradiction abstains.** When the rule passes but the shape disagrees, no claim is
///     made. This is what keeps the loose Southern ngã rule from producing a confident wrong
///     "correct".
public enum VerdictPolicy {
    public static func judge(
        target: ToneMark,
        accent: Accent,
        features: ToneTakeFeatures?,
        referenceContour: [Double]? = nil,
        learnerContour: [Double]? = nil
    ) -> ToneVerdict {
        guard let features else {
            return ToneVerdict(
                outcome: .inconclusive(.weakSignal), target: target, accent: accent,
                failures: [], shapeMatch: nil, reading: nil
            )
        }

        let reading = ToneShapeJudge.read(features: features.contour)
        let shapeMatch = shapeMatch(learner: learnerContour, reference: referenceContour)
        let failures = ToneRuleTable.failures(for: target, accent: accent, features: features)
        let targetFamily = target.family(in: accent)
        let producedFamily = reading.family.toneFamily

        func verdict(_ outcome: ToneVerdict.Outcome, withMatch: Bool = true) -> ToneVerdict {
            ToneVerdict(
                outcome: outcome, target: target, accent: accent, failures: failures,
                shapeMatch: withMatch ? shapeMatch : nil, reading: reading
            )
        }

        if failures.isEmpty {
            // The rule accepted it. Only agree out loud if the shape agrees too — or, for the
            // merged Southern pair, if creak evidence corroborates what pitch alone missed.
            if producedFamily == targetFamily {
                return verdict(.matched)
            }
            if accent == .south, ToneRuleTable.southernDippingEvidence(for: target, features: features) {
                return verdict(.matched)
            }
            return verdict(.inconclusive(.contradictoryEvidence), withMatch: false)
        }

        // The rule refused it. Say as much as the shape supports, and no more.
        guard let producedFamily else {
            return verdict(.inconclusive(.unclearShape), withMatch: false)
        }
        if let named = producedFamily.unambiguousTone(in: accent), named != target {
            return verdict(.missedNaming(named))
        }
        return verdict(.missedShape(producedFamily))
    }

    private static func shapeMatch(learner: [Double]?, reference: [Double]?) -> ShapeMatch? {
        guard let learner, let reference else { return nil }
        return ShapeMatch.between(learner: learner, reference: reference)
    }
}
