import Testing
@testable import DauCore

/// The product position, made executable.
///
/// Every claim Dấu makes about a take passes through `VerdictPolicy`, so these tests are the
/// place the honesty rules are actually enforced. If a future change makes the app claim more
/// than the signal supports, it breaks here rather than in front of a learner.
@Suite("verdict policy")
struct VerdictPolicyTests {
    static func judge(
        target: ToneMark, accent: Accent, contour: [Double],
        energy: ToneEnergyFeatures = .neutral, reference: [Double]? = nil
    ) -> ToneVerdict {
        VerdictPolicy.judge(
            target: target, accent: accent,
            features: SyntheticContour.features(contour, energy: energy),
            referenceContour: reference, learnerContour: contour
        )
    }

    // MARK: - The brand moment

    /// The cold-open: the learner aims at má (mother) and produces a flat ngang, so they said
    /// `ma` — ghost. Level resolves uniquely in both accents, which is what makes naming the
    /// word defensible rather than a guess.
    @Test("a flat take aimed at má is named as ma, in both accents")
    func flatAimedAtSacIsNamedGhost() {
        for accent in Accent.allCases {
            let verdict = Self.judge(target: .sac, accent: accent, contour: SyntheticContour.level)
            #expect(verdict.outcome == .missedNaming(.ngang), "\(accent)")
            #expect(verdict.failures == [.noRise])
        }
    }

    /// The counterpart the design leans on: aim at ngang, produce a rise. In the South that
    /// names sắc; in the North it must NOT, because sắc and ngã share the rising family.
    @Test("naming a rise depends on the accent")
    func namingARiseDependsOnAccent() {
        let south = Self.judge(target: .ngang, accent: .south, contour: SyntheticContour.rise(4))
        #expect(south.outcome == .missedNaming(.sac))

        let north = Self.judge(target: .ngang, accent: .north, contour: SyntheticContour.rise(4))
        #expect(north.outcome == .missedShape(.rising))
        if case .missedNaming = north.outcome {
            Issue.record("North must not name a rising tone — sắc and ngã share it")
        }
    }

    /// Falling never resolves: huyền and nặng are separated by duration and terminal energy,
    /// not by contour shape. A fall must therefore always be described, never named.
    @Test("a fall is never named as a word")
    func fallIsNeverNamed() {
        for accent in Accent.allCases {
            let verdict = Self.judge(target: .sac, accent: accent, contour: SyntheticContour.fall(4))
            #expect(verdict.outcome == .missedShape(.falling), "\(accent)")
        }
    }

    // MARK: - Abstention

    @Test("no features means no verdict and no number")
    func noFeaturesMeansNoVerdict() {
        let verdict = VerdictPolicy.judge(
            target: .sac, accent: .north, features: nil,
            referenceContour: SyntheticContour.rise(4), learnerContour: SyntheticContour.rise(4)
        )
        #expect(verdict.outcome == .inconclusive(.weakSignal))
        #expect(verdict.shapeMatch == nil, "a weak take must show no number at all")
        #expect(verdict.isInconclusive)
    }

    /// The loose Southern ngã rule accepts a plain rise. The shape judge says that was a
    /// rise, not a dip. Rather than resolve the disagreement in the app's favour, abstain.
    /// This is the check that stops a confident wrong "correct".
    @Test("rule and shape disagreeing produces no claim")
    func contradictionAbstains() {
        let verdict = Self.judge(
            target: .nga, accent: .south, contour: SyntheticContour.rise(3),
            reference: SyntheticContour.dip(depth: 3)
        )
        #expect(verdict.outcome == .inconclusive(.contradictoryEvidence))
        #expect(verdict.isMatch == false)
        #expect(verdict.shapeMatch == nil, "an abstention must not carry a number")
    }

    /// ...but creak evidence corroborates the merged Southern pair where pitch alone missed
    /// it, which is exactly what the energy features were ported for.
    @Test("creak evidence rescues the merged Southern pair")
    func creakCorroboratesSouthernDip() {
        let creaky = ToneEnergyFeatures(
            durationSeconds: 0.5, voicedFraction: 0.8, longestVoicingGapMs: 55,
            centralRmsDip: 0.3, terminalEnergyDrop: 0.1
        )
        let verdict = Self.judge(
            target: .hoi, accent: .south, contour: SyntheticContour.dip(depth: 3), energy: creaky
        )
        #expect(verdict.isMatch)
    }

    // MARK: - The number

    @Test("a shape match needs both contours and is suppressed otherwise")
    func shapeMatchRequiresAReference() {
        let withReference = Self.judge(
            target: .sac, accent: .north, contour: SyntheticContour.rise(4),
            reference: SyntheticContour.rise(4)
        )
        #expect(withReference.shapeMatch?.percent == 100)

        let withoutReference = Self.judge(
            target: .sac, accent: .north, contour: SyntheticContour.rise(4)
        )
        #expect(withoutReference.shapeMatch == nil)
    }

    @Test("shape match falls as the take diverges from the target")
    func shapeMatchTracksDivergence() {
        let target = SyntheticContour.rise(4)
        let close = ShapeMatch.between(learner: SyntheticContour.rise(3.5), reference: target)!
        let far = ShapeMatch.between(learner: SyntheticContour.fall(4), reference: target)!
        #expect(close.percent > far.percent)
        #expect(far.percent < 50, "an opposite contour must not read as half right")
        #expect(ShapeMatch.between(learner: [], reference: []) == nil)
        #expect(ShapeMatch.between(learner: [1, 2], reference: [1]) == nil)
    }

    /// The plan's explicit requirement: a rule failure must never be rendered as success.
    @Test("a rule failure never presents as a match")
    func ruleFailureNeverPresentsAsMatch() {
        let contours = [
            SyntheticContour.level, SyntheticContour.rise(4), SyntheticContour.fall(4),
            SyntheticContour.dip(depth: 3), SyntheticContour.wobble,
        ]
        for tone in ToneMark.allCases {
            for accent in Accent.allCases {
                for contour in contours {
                    let verdict = Self.judge(
                        target: tone, accent: accent, contour: contour, reference: contour
                    )
                    if !verdict.failures.isEmpty {
                        #expect(
                            verdict.isMatch == false,
                            "\(tone.rawValue)/\(accent.rawValue) failed \(verdict.failures) yet reported a match"
                        )
                    }
                    // And a matched verdict always agrees with the rules.
                    if verdict.isMatch { #expect(verdict.failures.isEmpty) }
                }
            }
        }
    }

    // MARK: - Copy

    @Test("copy never uses score, accuracy, or confidence language")
    func copyAvoidsScoreLanguage() {
        // "graded on this iPhone" is deliberate and stays — grading is what the DSP does,
        // and saying where it happened is the privacy claim. What must never appear is a
        // *score*: a number implying a model's opinion of the learner rather than a
        // measurement of their contour.
        let banned = ["score", "accuracy", "confidence", "% correct", "out of 100", "rating"]
        let target = VerdictCopy.Word(surface: "má", meaning: "mother")
        let produced = VerdictCopy.Word(surface: "ma", meaning: "ghost")
        let contours = [
            SyntheticContour.level, SyntheticContour.rise(4),
            SyntheticContour.fall(4), SyntheticContour.wobble,
        ]
        var strings: [String] = []
        for tone in ToneMark.allCases {
            for accent in Accent.allCases {
                for contour in contours {
                    let verdict = Self.judge(
                        target: tone, accent: accent, contour: contour, reference: contour
                    )
                    strings.append(VerdictCopy.eyebrow(for: verdict))
                    strings.append(VerdictCopy.headline(for: verdict, target: target, produced: produced))
                    strings.append(VerdictCopy.detail(for: verdict, target: target))
                    strings.append(VerdictCopy.provenance(for: verdict))
                    if let match = verdict.shapeMatch {
                        strings.append(VerdictCopy.shapeMatchLabel(match))
                    }
                }
            }
        }
        for string in strings {
            let lowered = string.lowercased()
            for word in banned {
                #expect(!lowered.contains(word), "copy said '\(word)': \(string)")
            }
        }
        // ...and every verdict states where grading happened.
        #expect(strings.contains { $0.contains("on this iPhone") })
    }

    @Test("the shape-match label reads as a measurement")
    func shapeMatchLabelIsAMeasurement() {
        let match = ShapeMatch(percent: 78, rmsDeviationSemitones: 1.76)
        #expect(VerdictCopy.shapeMatchLabel(match) == "78% shape match")
    }

    @Test("an inconclusive verdict never claims a tone was detected")
    func inconclusiveNeverClaimsDetection() {
        let verdict = Self.judge(
            target: .nga, accent: .south, contour: SyntheticContour.rise(3)
        )
        #expect(VerdictCopy.provenance(for: verdict) == "no verdict · graded on this iPhone")
        let target = VerdictCopy.Word(surface: "mã", meaning: "code")
        let detail = VerdictCopy.detail(for: verdict, target: target)
        #expect(detail.contains("rather not guess"))
    }
}
