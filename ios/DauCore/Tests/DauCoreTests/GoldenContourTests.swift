import Testing
@testable import DauCore

/// Pins the Swift engine against `dấu`'s 36 accepted reference takes.
///
/// Two independent things are checked: that the feature arithmetic agrees with the Python it
/// was ported from, and that the family judge reproduces the exact held-out table — including
/// every one of its six misses, by name. Naming them matters: a threshold change that fixes
/// one miss and breaks two nets out to the same 30/36 and would otherwise pass unnoticed.
@Suite("golden contours")
struct GoldenContourTests {
    /// The feature port agrees with `dấu`'s own numbers to ~1.8e-5; 1e-4 leaves headroom
    /// without letting a real regression through.
    static let tolerance = 1e-4

    @Test("the 36 accepted takes load")
    func fixturesLoad() {
        #expect(GoldenFixtures.all.count == 36)
        #expect(GoldenFixtures.all.allSatisfy { $0.contour.count == 64 })
        // 19 North, 17 South — South is missing ma-grave and phuong-phoenix, which failed
        // generation. That asymmetry is a declared exception, not a gap to fill silently.
        #expect(GoldenFixtures.all.filter { $0.accent == "north" }.count == 19)
        #expect(GoldenFixtures.all.filter { $0.accent == "south" }.count == 17)
    }

    @Test("pitch features match the Python they were ported from")
    func featuresMatchPython() {
        for take in GoldenFixtures.all {
            let computed = ToneContourFeatures.of(
                resampledPoints: take.contour, sampleCount: take.contour.count
            )
            guard let computed else {
                Issue.record("\(take.label): features returned nil")
                continue
            }
            let stored = take.features
            func check(_ name: String, _ got: Double, _ want: Double) {
                #expect(
                    abs(got - want) < Self.tolerance,
                    "\(take.label) \(name): \(got) vs \(want)"
                )
            }
            check("start", computed.start, stored.start)
            check("end", computed.end, stored.end)
            check("slope", computed.slope, stored.slope)
            check("curvature", computed.curvature, stored.curvature)
            check("pitchRange", computed.pitchRange, stored.pitchRange)
            check("minimum", computed.minimum, stored.minimum)
            check("dipPosition", computed.dipPosition, stored.dipPosition)
            check("recovery", computed.recovery, stored.recovery)
            check("finalRise", computed.finalRise, stored.finalRise)
        }
    }

    /// Every take that the family judge reads as something other than its labelled family.
    ///
    /// These are not bugs to fix by tuning. Five of the six are Southern takes whose audio is
    /// `gpt-realtime` TTS carrying `accent_family_verified: false` — the labels are intended
    /// tones, not confirmed ones — and every Southern dipping miss ends well ABOVE where it
    /// started, which is not a dip at all. Tuning thresholds to fit them would be fitting to
    /// synthesized labels. The fix is real Southern hỏi/ngã audio.
    ///
    /// `south ma-ghost` is the one worth watching: a ngang drifting +1.12 st on a +1.23 slope
    /// clears the directional override by about a tenth of a semitone. `ma` is the first cell
    /// of the six-ma grid and the cold-open word, so a Southern learner saying a slightly
    /// drifting `ma` is told they rose.
    static let knownMisses: [String: (expected: ToneFamily, read: ToneShapeFamily)] = [
        "north cua-door": (.dipping, .falling),
        "south ma-ghost": (.level, .rising),
        "south ma-code": (.dipping, .rising),
        "south pho-noodle-soup": (.dipping, .rising),
        "south sua-milk": (.dipping, .rising),
        "south mu-hat": (.dipping, .rising),
    ]

    @Test("family judge reproduces the held-out table, miss for miss")
    func familyTableIsPinned() {
        var tally: [ToneFamily: (hit: Int, total: Int)] = [:]
        var observedMisses: [String: (expected: ToneFamily, read: ToneShapeFamily)] = [:]

        for take in GoldenFixtures.all {
            let expected = take.toneMark.family(in: take.accentValue)
            let read = ToneShapeJudge.family(of: take.takeFeatures.contour)
            var entry = tally[expected] ?? (0, 0)
            entry.total += 1
            if read.toneFamily == expected {
                entry.hit += 1
            } else {
                observedMisses[take.label] = (expected, read)
            }
            tally[expected] = entry
        }

        // Recomputed 2026-08-26 against the post-16a46fbb thresholds. nghe's
        // docs/research/tone-shape-calibration.md still prints the older 6/6 · 13/13 · 8/9
        // · 3/8; it is stale and should be corrected there too.
        #expect(tally[.level]?.hit == 5, "level")
        #expect(tally[.level]?.total == 6)
        #expect(tally[.rising]?.hit == 9, "rising")
        #expect(tally[.rising]?.total == 9)
        #expect(tally[.falling]?.hit == 13, "falling")
        #expect(tally[.falling]?.total == 13)
        #expect(tally[.dipping]?.hit == 3, "dipping")
        #expect(tally[.dipping]?.total == 8)

        #expect(
            Set(observedMisses.keys) == Set(Self.knownMisses.keys),
            """
            miss set changed.
              now missing: \(observedMisses.keys.sorted())
              expected:    \(Self.knownMisses.keys.sorted())
            """
        )
        for (label, expectation) in Self.knownMisses {
            guard let observed = observedMisses[label] else { continue }
            #expect(
                observed.read == expectation.read,
                "\(label) now reads \(observed.read.rawValue), was \(expectation.read.rawValue)"
            )
        }
    }

    /// The rule table accepts all 36 — **and this proves nothing about its accuracy.**
    /// `validate_target_candidate` selected these very takes by these very rules (302
    /// candidates were rejected), so this is a tautology. It is worth keeping only as a
    /// regression guard on the port itself: if a ported rule drifts, this breaks.
    /// Real evidence lives in `ToneRuleTableTests`, which feeds it takes that must fail.
    @Test("rule table accepts every accepted take (tautological — see the comment)")
    func ruleTableAcceptsTheCorpus() {
        for take in GoldenFixtures.all {
            let failures = ToneRuleTable.failures(
                for: take.toneMark, accent: take.accentValue, features: take.takeFeatures
            )
            #expect(failures.isEmpty, "\(take.label) failed \(failures.map(\.rawValue))")
        }
    }

    /// Provenance the copy depends on: only two takes in the corpus are real human
    /// recordings, and they are the highest-trust audio available for an acceptance demo.
    /// Everything else is `gpt-realtime` TTS — which is why the UI never credits a teacher.
    @Test("provenance is what the copy claims")
    func provenanceIsHonest() {
        let human = GoldenFixtures.all.filter { $0.model == nil }
        #expect(human.count == 2)
        #expect(Set(human.map(\.label)) == ["north ma-grave", "north pho-noodle-soup"])

        // accent_family_verified is set only by the Southern hỏi/ngã creak test — it is not
        // a quality grade, and it is never true for a Northern take.
        let verified = GoldenFixtures.all.filter(\.accentFamilyVerified)
        #expect(verified.allSatisfy { $0.accent == "south" })
        #expect(verified.count == 5)
    }
}
