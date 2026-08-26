import Foundation
import Testing
@testable import DauCore

/// Synthetic signals with a known pitch trajectory.
enum TestSignal {
    static let sampleRate = 48_000.0

    /// A voiced tone gliding from `startHz` to `endHz` over `seconds`, amplitude well above
    /// the RMS gate. Phase is integrated so the instantaneous frequency is actually correct —
    /// a naive `sin(2π f(t) t)` sweeps at twice the intended rate.
    static func glide(
        from startHz: Double, to endHz: Double, seconds: Double, amplitude: Float = 0.3
    ) -> [Float] {
        let count = Int(sampleRate * seconds)
        var phase = 0.0
        return (0..<count).map { index in
            let progress = Double(index) / Double(max(count - 1, 1))
            let frequency = startHz + (endHz - startHz) * progress
            phase += 2 * .pi * frequency / sampleRate
            return amplitude * Float(sin(phase))
        }
    }

    static func steady(_ hz: Double, seconds: Double, amplitude: Float = 0.3) -> [Float] {
        glide(from: hz, to: hz, seconds: seconds, amplitude: amplitude)
    }

    /// A voiced vowel: an f0 with strong upper formants, the way real speech is shaped.
    /// Its raw zero-crossing rate far exceeds f0, which is what broke the original gate.
    static func vowel(f0: Double, seconds: Double, amplitude: Float = 0.3) -> [Float] {
        let count = Int(sampleRate * seconds)
        return (0..<count).map { index in
            let t = Double(index) / sampleRate
            let fundamental = sin(2 * .pi * f0 * t)
            let formantOne = 0.8 * sin(2 * .pi * 700 * t)
            let formantTwo = 0.6 * sin(2 * .pi * 1_400 * t)
            return amplitude * Float((fundamental + formantOne + formantTwo) / 2.4)
        }
    }

    static func silence(seconds: Double) -> [Float] {
        [Float](repeating: 0, count: Int(sampleRate * seconds))
    }
}

@Suite("pitch analyzer")
struct PitchAnalyzerTests {
    /// **The contract.** The live trace draws frames as they stream in; the verdict is
    /// computed from the finished take. If those two paths could ever disagree, the drawn
    /// line would contradict the words printed under it — which is the one failure this
    /// product cannot survive. So: identical output, whatever the chunking.
    @Test("streaming and batch agree frame for frame, at every chunk size")
    func streamingMatchesBatch() {
        let signal = TestSignal.glide(from: 120, to: 180, seconds: 0.6)
        let batch = PitchFrameAnalyzer.analyze(samples: signal, sampleRate: TestSignal.sampleRate)

        // 1 is pathological, 1024 is the real tap size, 4096 is a slow-tap fallback, and the
        // primes make sure nothing depends on chunk boundaries landing on a hop or stride.
        for chunkSize in [1, 7, 101, 256, 1024, 4096, signal.count] {
            var analyzer = PitchFrameAnalyzer(sampleRate: TestSignal.sampleRate)
            var streamed: [PitchFrame] = []
            var offset = 0
            while offset < signal.count {
                let end = min(offset + chunkSize, signal.count)
                streamed += analyzer.push(Array(signal[offset..<end]))
                offset = end
            }
            let take = analyzer.finish()
            #expect(streamed.count == analyzer.rawFrames.count, "chunk \(chunkSize)")
            #expect(take.frames == batch.frames, "chunk \(chunkSize): frames diverged")
            #expect(take.contour == batch.contour, "chunk \(chunkSize): contour diverged")
            #expect(take.rms == batch.rms, "chunk \(chunkSize): rms diverged")
            #expect(take.longestVoicingGapMs == batch.longestVoicingGapMs, "chunk \(chunkSize)")
        }
    }

    @Test("a steady tone reads as level")
    func steadyToneIsLevel() {
        let take = PitchFrameAnalyzer.analyze(
            samples: TestSignal.steady(140, seconds: 0.6), sampleRate: TestSignal.sampleRate
        )
        let features = take.contourFeatures
        #expect(features != nil)
        #expect(ToneShapeJudge.family(of: features!) == .level)
        #expect(abs(features!.slope) < ToneShapeJudge.levelMaximumSlope)
    }

    @Test("a rising glide reads as rising and passes the sắc rule")
    func risingGlideIsRising() {
        // ~5 semitones up, the shape a sắc actually has.
        let take = PitchFrameAnalyzer.analyze(
            samples: TestSignal.glide(from: 120, to: 160, seconds: 0.6),
            sampleRate: TestSignal.sampleRate
        )
        let features = take.takeFeatures
        #expect(features != nil)
        #expect(ToneShapeJudge.family(of: features!.contour) == .rising)
        #expect(ToneRuleTable.passes(.sac, accent: .north, features: features!))
        #expect(ToneRuleTable.failures(for: .huyen, accent: .north, features: features!) == [.noFall])
    }

    @Test("a falling glide reads as falling")
    func fallingGlideIsFalling() {
        let take = PitchFrameAnalyzer.analyze(
            samples: TestSignal.glide(from: 170, to: 120, seconds: 0.6),
            sampleRate: TestSignal.sampleRate
        )
        #expect(ToneShapeJudge.family(of: take.contourFeatures!) == .falling)
    }

    @Test("silence yields no readable contour and therefore no verdict")
    func silenceYieldsNoVerdict() {
        let take = PitchFrameAnalyzer.analyze(
            samples: TestSignal.silence(seconds: 0.5), sampleRate: TestSignal.sampleRate
        )
        #expect(take.contourFeatures == nil)
        #expect(take.voicedSeconds == 0)
        let verdict = VerdictPolicy.judge(
            target: .sac, accent: .north, features: take.takeFeatures
        )
        #expect(verdict.outcome == .inconclusive(.weakSignal))
        #expect(verdict.shapeMatch == nil)
    }

    /// Leading and trailing silence is not a glottal break; only an interior gap is.
    /// Getting this wrong would hand the nặng and Southern-dipping rules false evidence.
    @Test("only interior silence counts as a voicing gap")
    func onlyInteriorSilenceIsAGap() {
        let padded = TestSignal.silence(seconds: 0.2)
            + TestSignal.steady(140, seconds: 0.3)
            + TestSignal.silence(seconds: 0.2)
        let noGap = PitchFrameAnalyzer.analyze(samples: padded, sampleRate: TestSignal.sampleRate)
        #expect(noGap.longestVoicingGapMs == 0)

        let broken = TestSignal.steady(140, seconds: 0.25)
            + TestSignal.silence(seconds: 0.08)
            + TestSignal.steady(140, seconds: 0.25)
        let withGap = PitchFrameAnalyzer.analyze(samples: broken, sampleRate: TestSignal.sampleRate)
        #expect(withGap.longestVoicingGapMs >= 40, "a real break must register as creak evidence")
    }

    /// The port's one real defect, and a regression guard against reintroducing it.
    ///
    /// Zero-crossing rate follows whichever part of the spectrum carries the energy, so a
    /// bright vowel crosses zero far more than 440 times a second even at a 150 Hz pitch.
    /// Measured on the raw frame, the gate discarded almost every voiced frame in the
    /// reference corpus — three references, one of them a human recording, produced no
    /// contour at all. Measuring it on a 500 Hz low-band probe fixes that.
    @Test("a bright vowel is voiced despite a high raw crossing rate")
    func brightVowelIsVoiced() {
        let take = PitchFrameAnalyzer.analyze(
            samples: TestSignal.vowel(f0: 150, seconds: 0.6), sampleRate: TestSignal.sampleRate
        )
        #expect(take.voicedFraction > 0.5, "got \(take.voicedFraction)")
        #expect(take.contourFeatures != nil)
        #expect(ToneShapeJudge.family(of: take.contourFeatures!) == .level)
    }

    /// ...and the defence that gate was there to provide must survive. A loud tone well
    /// outside the voice band correlates strongly at some lag in the search range, so without
    /// a check it would produce a confident, meaningless pitch.
    @Test("an out-of-band tone is still rejected")
    func outOfBandToneIsRejected() {
        for frequency in [1_500.0, 3_000.0, 3_500.0] {
            let take = PitchFrameAnalyzer.analyze(
                samples: TestSignal.steady(frequency, seconds: 0.5),
                sampleRate: TestSignal.sampleRate
            )
            #expect(take.voicedFraction == 0, "\(frequency) Hz was treated as voice")
        }
    }

    @Test("in-band tones across the vocal range stay voiced")
    func inBandTonesStayVoiced() {
        for frequency in [110.0, 180.0, 350.0] {
            let take = PitchFrameAnalyzer.analyze(
                samples: TestSignal.steady(frequency, seconds: 0.5),
                sampleRate: TestSignal.sampleRate
            )
            #expect(take.voicedFraction > 0.8, "\(frequency) Hz was lost")
        }
    }

    @Test("octave repair pulls a doubled frame back without touching a real glissando")
    func octaveRepairIsTargeted() {
        var series: [Double?] = Array(repeating: 140, count: 15)
        series[7] = 280
        let repaired = PitchFrameAnalyzer.repairOctaveJumps(series)
        #expect(repaired[7] == 140)

        // A genuine wide sweep, whose neighbours track it, must be left alone.
        let glissando: [Double?] = (0..<15).map { 120 + Double($0) * 6 }
        #expect(PitchFrameAnalyzer.repairOctaveJumps(glissando) == glissando)
    }

    @Test("median smoothing kills a spike but keeps a monotone rise monotone")
    func medianSmoothPreservesShape() {
        var spiked: [Double?] = Array(repeating: 140, count: 11)
        spiked[5] = 190
        let smoothed = PitchFrameAnalyzer.medianSmooth(spiked).compactMap { $0 }
        #expect(smoothed.allSatisfy { $0 == 140 })

        let rise: [Double?] = (0..<11).map { 120 + Double($0) * 4 }
        let smoothedRise = PitchFrameAnalyzer.medianSmooth(rise).compactMap { $0 }
        #expect(zip(smoothedRise, smoothedRise.dropFirst()).allSatisfy { $0 <= $1 })
    }

    @Test("unvoiced frames survive resampling so syllable gaps stay visible")
    func resamplingKeepsGaps() {
        let values: [Double?] = [0, 1, nil, nil, nil, nil, 2, 3]
        let resampled = PitchFrameAnalyzer.resample(values, to: 8)
        #expect(resampled.contains { $0 == nil }, "a gap must not be interpolated away")
    }
}
