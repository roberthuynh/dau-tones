import Testing
@testable import DauCore

/// The evidence the golden corpus test cannot provide.
///
/// `GoldenContourTests.ruleTableAcceptsTheCorpus` is tautological — those takes were selected
/// by these rules. These are takes that MUST be rejected, which is the only way to show the
/// rules discriminate at all.
@Suite("rule table")
struct ToneRuleTableTests {
    @Test("a flat take is not a rising sắc")
    func flatIsNotSac() {
        let flat = SyntheticContour.features(SyntheticContour.level)
        #expect(ToneRuleTable.failures(for: .sac, accent: .north, features: flat) == [.noRise])
        #expect(ToneRuleTable.failures(for: .sac, accent: .south, features: flat) == [.noRise])
        // ...but it is a perfectly good ngang.
        #expect(ToneRuleTable.passes(.ngang, accent: .north, features: flat))
    }

    @Test("a rising take is not a falling huyền")
    func risingIsNotHuyen() {
        let rising = SyntheticContour.features(SyntheticContour.rise(4))
        #expect(ToneRuleTable.failures(for: .huyen, accent: .north, features: rising) == [.noFall])
        #expect(ToneRuleTable.passes(.sac, accent: .north, features: rising))
    }

    @Test("a falling take is not a level ngang")
    func fallingIsNotNgang() {
        let falling = SyntheticContour.features(SyntheticContour.fall(4))
        #expect(ToneRuleTable.failures(for: .ngang, accent: .north, features: falling) == [.notLevel])
        #expect(ToneRuleTable.passes(.huyen, accent: .north, features: falling))
    }

    @Test("a long nặng with no terminal energy drop is rejected")
    func longNangWithoutDropIsRejected() {
        // nặng is short and low; a fall alone is not enough once the syllable runs long.
        let sustained = ToneEnergyFeatures(
            durationSeconds: 0.9, voicedFraction: 1.0, longestVoicingGapMs: 0,
            centralRmsDip: 0, terminalEnergyDrop: 0.05
        )
        let take = SyntheticContour.features(SyntheticContour.fall(3), energy: sustained)
        #expect(ToneRuleTable.failures(for: .nang, accent: .north, features: take) == [.notShortLow])
    }

    @Test("the same fall passes as nặng when the energy actually drops away")
    func shortNangWithDropPasses() {
        let clipped = ToneEnergyFeatures(
            durationSeconds: 0.9, voicedFraction: 1.0, longestVoicingGapMs: 0,
            centralRmsDip: 0, terminalEnergyDrop: 0.4
        )
        let take = SyntheticContour.features(SyntheticContour.fall(3), energy: clipped)
        #expect(ToneRuleTable.passes(.nang, accent: .north, features: take))
    }

    @Test("ngã splits by accent")
    func ngaSplitsByAccent() {
        // Northern ngã is a broken rise...
        let rising = SyntheticContour.features(SyntheticContour.rise(3))
        #expect(ToneRuleTable.passes(.nga, accent: .north, features: rising))
        // ...while Southern ngã has merged into the dipping tone, so a dip is right there
        // and a plain rise is not a broken rise in the North.
        let dipping = SyntheticContour.features(SyntheticContour.dip(depth: 3))
        #expect(ToneRuleTable.passes(.nga, accent: .south, features: dipping))
        #expect(ToneRuleTable.failures(for: .nga, accent: .north, features: dipping) == [.noBrokenRise])
    }

    /// A documented weakness, recorded rather than tuned away.
    ///
    /// The Southern ngã acceptance rule is `recovery >= 0.35`, and `recovery` is measured
    /// from the contour's minimum — which for any monotonic rise sits at the very start. So a
    /// steady climb "recovers" by its whole range and is accepted as Southern ngã, even
    /// though it never dipped.
    ///
    /// This is faithful to `api/dau/tones.py`, and it is not fixed here: these thresholds are
    /// calibrated, and the plan is explicit that they must not be tuned against TTS labels.
    /// It is also the same soft spot the family judge shows (Southern dipping, 3/8). The
    /// compensation lives one layer up — `VerdictPolicy` requires
    /// `southernDippingEvidence` before it will speak confidently about the merged pair, and
    /// abstains rather than guessing when the evidence is absent. Real Southern hỏi/ngã
    /// recordings are what actually settles it.
    @Test("Southern ngã acceptance is loose, by inheritance")
    func southernNgaAcceptanceIsLoose() {
        let rising = SyntheticContour.features(SyntheticContour.rise(3))
        #expect(ToneRuleTable.passes(.nga, accent: .south, features: rising))
        // But the corroborating evidence test — the one the verdict layer actually consults
        // — correctly declines to call it a dip.
        #expect(ToneRuleTable.southernDippingEvidence(for: .nga, features: rising) == false)
    }

    @Test("Southern dipping evidence needs creak, not just a pitch V")
    func southernDippingNeedsCreak() {
        let pitchOnly = SyntheticContour.features(SyntheticContour.dip(depth: 3))
        // A clean pitch dip with no glottal evidence is not enough to corroborate the merged
        // Southern family — this is the check that makes the weakest call honest.
        #expect(ToneRuleTable.southernDippingEvidence(for: .hoi, features: pitchOnly) == false)

        let creaky = ToneEnergyFeatures(
            durationSeconds: 0.5, voicedFraction: 0.8, longestVoicingGapMs: 55,
            centralRmsDip: 0.3, terminalEnergyDrop: 0.1
        )
        let withCreak = SyntheticContour.features(SyntheticContour.dip(depth: 3), energy: creaky)
        #expect(ToneRuleTable.southernDippingEvidence(for: .hoi, features: withCreak))
        #expect(ToneRuleTable.southernDippingEvidence(for: .nga, features: withCreak))
        // It only ever speaks about the merged pair.
        #expect(ToneRuleTable.southernDippingEvidence(for: .sac, features: withCreak) == false)
    }

    @Test("a wobble is not a dip")
    func wobbleIsNotADip() {
        let wobble = SyntheticContour.features(SyntheticContour.wobble)
        #expect(ToneShapeJudge.family(of: wobble.contour) != .dipping)
    }
}
