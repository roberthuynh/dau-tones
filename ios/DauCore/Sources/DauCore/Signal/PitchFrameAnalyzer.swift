import Foundation

/// One analysis frame: an estimate every 10 ms.
public struct PitchFrame: Equatable, Sendable {
    /// Estimated fundamental in Hz, or nil when the frame is unvoiced or rejected.
    public let hz: Double?
    /// Frame energy, used for the creak and terminal-drop evidence.
    public let rms: Double
    /// Frame position from the start of the take.
    public let index: Int

    public init(hz: Double?, rms: Double, index: Int) {
        self.hz = hz
        self.rms = rms
        self.index = index
    }
}

/// A finished take: the normalized contour plus everything the judge and rule table need.
public struct PitchTake: Equatable, Sendable {
    /// Speaker-relative semitones against the take's own median F0, nil where unvoiced.
    /// Raw 10 ms hop resolution — anything that segments syllables must read this, because
    /// resampling destroys the gap structure between them.
    public let frames: [Double?]
    /// The voiced span of `frames`, resampled to the 64-point analysis axis the thresholds
    /// were calibrated on.
    ///
    /// Trimmed to the utterance first. This mirrors `isolate_primary_speech` in the Python,
    /// and it is not cosmetic: resampling across a file's leading and trailing silence
    /// squashes the syllable into a fraction of the axis, which moves every position feature
    /// (`dipPosition` above all) and makes a learner contour incomparable with a reference
    /// recorded with different padding.
    public let contour: [Double?]
    /// Per-frame energy, on the same axis as `frames`.
    public let rms: [Double]
    public let durationSeconds: Double
    public let voicedSeconds: Double
    /// Longest interior run of unvoiced frames, in milliseconds — glottal-break evidence.
    public let longestVoicingGapMs: Double

    public var voicedFraction: Double {
        guard !frames.isEmpty else { return 0 }
        return Double(frames.compactMap { $0 }.count) / Double(frames.count)
    }

    /// The energy features the rule table needs, derived from this take.
    public var energyFeatures: ToneEnergyFeatures {
        RMSEnvelope.features(
            rms: rms,
            durationSeconds: durationSeconds,
            voicedFraction: voicedFraction,
            longestVoicingGapMs: longestVoicingGapMs
        )
    }

    /// Contour features, or nil when there is too little voiced signal to read.
    public var contourFeatures: ToneContourFeatures? {
        ToneContourFeatures.of(contour: contour)
    }

    /// `contour` with interior gaps bridged, as a full 64-point series.
    ///
    /// This is what `ShapeMatch` must compare against a reference. Dropping the unvoiced
    /// points instead (a `compactMap`) shortens the series, so it no longer aligns with the
    /// 64-point target and the comparison silently returns nothing — the number just never
    /// appears. Nil when there is too little voiced signal to bridge.
    public var filledContour: [Double]? {
        guard contour.compactMap({ $0 }).count >= ToneContourFeatures.minimumVoicedPoints else {
            return nil
        }
        let interpolated = ToneNumerics.interpolatingGaps(in: contour)
        guard interpolated.count == contour.count else { return nil }
        return ToneNumerics.resampled(interpolated, to: ToneNumerics.analysisPoints)
    }

    public var takeFeatures: ToneTakeFeatures? {
        guard let contourFeatures else { return nil }
        return ToneTakeFeatures(contour: contourFeatures, energy: energyFeatures)
    }
}

/// Streaming autocorrelation pitch tracker.
///
/// Ported from nghe's `SystemTonePitchExtractor`, restructured so samples can be pushed in as
/// they arrive from an audio tap instead of read from a finished file. **The algorithm is
/// unchanged** — YIN was considered and rejected: this decimates to 8 kHz and searches lags
/// 20–114 over 240-sample frames, roughly 5.5 MFLOP/s, already comfortably real-time on any
/// A-series, and swapping it would discard the octave-repair work nghe's `16a46fbb` added
/// after a doubled frame near the ±12 clamp flattened a real fall.
///
/// Streaming and batch must agree frame for frame — the live trace and the verdict cannot be
/// allowed to disagree, or the drawn line contradicts the words underneath it.
/// `PitchAnalyzerTests` enforces that by pushing the same signal in every chunk size.
///
/// The subtle part is decimation: the batch path picks every Nth sample of the *whole* take,
/// so the streaming path tracks a global sample counter and picks the same absolute indices
/// rather than restarting the pattern at each chunk boundary.
public struct PitchFrameAnalyzer: Sendable {
    public let sampleRate: Double
    public let decimationStride: Int
    public let reducedRate: Double
    public let frameSize: Int
    public let hopSize: Int

    private let minimumLag: Int
    private let maximumLag: Int
    private let isViable: Bool

    /// Decimated samples for the whole take. A hard cap of 8 s at 8 kHz is 64k values, so
    /// holding them is cheap and makes exact batch equivalence trivial.
    private var reduced: [Double] = []
    /// The same stream through a causal 500 Hz one-pole lowpass, used for the voicing gates.
    /// Causal on purpose: a zero-phase two-pass filter would need the whole take and could not
    /// stream, and both gates read energy and zero crossings, which are phase-insensitive.
    private var lowBand: [Double] = []
    private var lowBandState = 0.0
    private var nextFrameStart = 0
    private var absoluteSampleIndex = 0
    private var frames: [PitchFrame] = []
    private var totalSamples = 0

    /// Gates, unchanged from the port.
    static let rmsFloor = 0.006
    static let zeroCrossingCeiling = 440.0
    static let correlationFloor = 0.52
    /// Cutoff for the voicing probe. Vietnamese f0 lives well under this; vowel formants and
    /// fricative noise live above it.
    static let lowBandCutoffHz = 500.0
    /// Share of frame energy that must survive the lowpass for the frame to be voiced speech.
    ///
    /// Measured over the reference corpus: real speech frames sit at 0.41 and above, while
    /// out-of-band pure tones land near 0.20–0.34 and are then caught by the zero-crossing
    /// ceiling. 0.20 is a floor that rejects nothing real while keeping a second line of
    /// defence against a loud tone that is not a voice.
    static let lowBandShareFloor = 0.20
    static let hopSeconds = 0.010
    static let frameSeconds = 0.030

    public init(sampleRate: Double) {
        self.sampleRate = sampleRate
        let stride = max(1, Int((sampleRate / 8_000).rounded(.down)))
        self.decimationStride = stride
        let reducedRate = sampleRate > 0 ? sampleRate / Double(stride) : 0
        self.reducedRate = reducedRate
        let frameSize = max(1, Int((reducedRate * Self.frameSeconds).rounded()))
        self.frameSize = frameSize
        self.hopSize = max(1, Int((reducedRate * Self.hopSeconds).rounded()))
        self.minimumLag = max(1, Int((reducedRate / 400).rounded(.down)))
        self.maximumLag = min(frameSize - 2, Int((reducedRate / 70).rounded(.up)))
        self.isViable = sampleRate > 0 && maximumLag > minimumLag
    }

    /// Feed newly captured samples. Returns the frames that completed as a result — the live
    /// trace draws these; they are raw Hz, not yet octave-repaired or smoothed.
    @discardableResult
    public mutating func push(_ samples: [Float]) -> [PitchFrame] {
        guard isViable, !samples.isEmpty else {
            totalSamples += samples.count
            return []
        }
        let coefficient = exp(-2 * .pi * Self.lowBandCutoffHz / reducedRate)
        for sample in samples {
            if absoluteSampleIndex % decimationStride == 0 {
                let value = Double(sample)
                reduced.append(value)
                lowBandState = (1 - coefficient) * value + coefficient * lowBandState
                lowBand.append(lowBandState)
            }
            absoluteSampleIndex += 1
        }
        totalSamples += samples.count
        return drainCompletedFrames()
    }

    private mutating func drainCompletedFrames() -> [PitchFrame] {
        var produced: [PitchFrame] = []
        while nextFrameStart + frameSize <= reduced.count {
            let frame = analyzeFrame(at: nextFrameStart, index: frames.count)
            frames.append(frame)
            produced.append(frame)
            nextFrameStart += hopSize
        }
        return produced
    }

    /// Every raw frame so far.
    public var rawFrames: [PitchFrame] { frames }

    /// Close the take and post-process: octave repair, median smoothing, then normalization
    /// to semitones against the take's own median.
    public func finish() -> PitchTake {
        Self.take(from: frames, totalSamples: totalSamples, sampleRate: sampleRate)
    }

    /// One-shot analysis, for reference audio and fixtures.
    public static func analyze(samples: [Float], sampleRate: Double) -> PitchTake {
        var analyzer = PitchFrameAnalyzer(sampleRate: sampleRate)
        analyzer.push(samples)
        return analyzer.finish()
    }

    // MARK: - Frame analysis

    private func analyzeFrame(at start: Int, index: Int) -> PitchFrame {
        let frame = Array(reduced[start..<(start + frameSize)])
        let mean = frame.reduce(0.0, +) / Double(frame.count)
        let centered = frame.map { $0 - mean }
        let rms = (centered.reduce(0) { $0 + $1 * $1 } / Double(centered.count)).squareRoot()
        guard rms >= Self.rmsFloor else { return PitchFrame(hz: nil, rms: rms, index: index) }

        // Voicing is decided on the low-band probe, not the raw frame.
        //
        // Measuring zero crossings on the raw signal was the port's one real defect: crossing
        // rate follows whichever part of the spectrum carries the energy, so a bright vowel
        // crosses zero far more than 440 times a second even at a 150 Hz pitch. On the
        // reference corpus that gate was discarding almost every voiced frame — three
        // references, including one of only two human recordings, produced no contour at all.
        // Lowpassing first makes the crossing rate reflect f0, which is what it was always
        // meant to test.
        let probe = Array(lowBand[start..<(start + frameSize)])
        let probeMean = probe.reduce(0.0, +) / Double(probe.count)
        let probeCentered = probe.map { $0 - probeMean }
        let probeRMS = (probeCentered.reduce(0) { $0 + $1 * $1 } / Double(probeCentered.count)).squareRoot()
        // Autocorrelation can mistake a subharmonic of an out-of-band pure tone for a valid
        // pitch. A voice keeps most of its energy under the cutoff; such a tone does not.
        guard rms > 0, probeRMS / rms >= Self.lowBandShareFloor else {
            return PitchFrame(hz: nil, rms: rms, index: index)
        }
        let zeroCrossings = zip(probeCentered, probeCentered.dropFirst()).count { first, second in
            (first < 0 && second >= 0) || (first >= 0 && second < 0)
        }
        let zeroCrossingFrequency = Double(zeroCrossings) * reducedRate / (2 * Double(probeCentered.count))
        guard zeroCrossingFrequency <= Self.zeroCrossingCeiling else {
            return PitchFrame(hz: nil, rms: rms, index: index)
        }

        var bestLag = minimumLag
        var bestCorrelation = -1.0
        for lag in minimumLag...maximumLag {
            var product = 0.0
            var energyA = 0.0
            var energyB = 0.0
            for offset in 0..<(frameSize - lag) {
                let a = centered[offset]
                let b = centered[offset + lag]
                product += a * b
                energyA += a * a
                energyB += b * b
            }
            let denominator = (energyA * energyB).squareRoot()
            let correlation = denominator > 0 ? product / denominator : 0
            if correlation > bestCorrelation + 0.005
                || (abs(correlation - bestCorrelation) <= 0.005 && lag < bestLag) {
                bestCorrelation = correlation
                bestLag = lag
            }
        }
        let hz = bestCorrelation >= Self.correlationFloor ? reducedRate / Double(bestLag) : nil
        return PitchFrame(hz: hz, rms: rms, index: index)
    }

    // MARK: - Post-processing

    static func take(from frames: [PitchFrame], totalSamples: Int, sampleRate: Double) -> PitchTake {
        let raw = frames.map(\.hz)
        let smoothed = medianSmooth(repairOctaveJumps(raw))
        let voiced = smoothed.compactMap { $0 }.sorted()
        let normalized: [Double?]
        if voiced.count >= 3 {
            let median = voiced[voiced.count / 2]
            normalized = smoothed.map { hz in
                hz.map { min(12, max(-12, 12 * log2($0 / median))) }
            }
        } else {
            normalized = smoothed.map { _ in nil }
        }
        return PitchTake(
            frames: normalized,
            contour: resample(trimmedToVoicedSpan(normalized), to: ToneNumerics.analysisPoints),
            rms: frames.map(\.rms),
            durationSeconds: sampleRate > 0 ? Double(totalSamples) / sampleRate : 0,
            voicedSeconds: Double(raw.compactMap { $0 }.count) * hopSeconds,
            longestVoicingGapMs: longestInteriorGapMs(in: raw)
        )
    }

    /// Drop leading and trailing unvoiced frames, keeping the utterance and any interior
    /// gaps inside it. Silence at the edges carries no tone and must not consume the axis.
    static func trimmedToVoicedSpan(_ values: [Double?]) -> [Double?] {
        let voicedIndices = values.indices.filter { values[$0] != nil }
        guard let first = voicedIndices.first, let last = voicedIndices.last else { return values }
        return Array(values[first...last])
    }

    /// Longest run of unvoiced frames with voiced frames on both sides. Leading and trailing
    /// silence is not a glottal break and must not read as one.
    static func longestInteriorGapMs(in values: [Double?]) -> Double {
        let voicedIndices = values.indices.filter { values[$0] != nil }
        guard let first = voicedIndices.first, let last = voicedIndices.last, first < last else {
            return 0
        }
        var longest = 0
        var current = 0
        for index in first...last {
            if values[index] == nil {
                current += 1
                longest = max(longest, current)
            } else {
                current = 0
            }
        }
        return Double(longest) * hopSeconds * 1000
    }

    /// Pull frames that landed a whole octave off their neighbours back into line, in Hz,
    /// before anything downstream sees them.
    ///
    /// The lag search prefers the shorter lag on a near tie, which is the classic invitation
    /// to a doubled estimate on the creaky, low-energy tail of a falling tone. A single bad
    /// frame the 5-frame median already handles; a run of three or four survives it, and
    /// after normalization one such frame can sit near the ±12 semitone clamp — wide enough
    /// on its own to stretch the drawn axis until a real two-semitone fall renders flat.
    ///
    /// A frame is only moved when it disagrees with the median of its voiced neighbours AND
    /// halving or doubling brings it into agreement, so a genuine wide glissando (whose
    /// neighbours track it) is left alone.
    static func repairOctaveJumps(
        _ values: [Double?], window: Int = 13, tolerance: Double = 0.12
    ) -> [Double?] {
        guard values.count > 2 else { return values }
        let half = max(1, window / 2)
        return values.indices.map { index in
            guard let value = values[index], value > 0 else { return nil }
            let low = max(0, index - half)
            let high = min(values.count - 1, index + half)
            let neighbors = (low...high).filter { $0 != index }.compactMap { values[$0] }.sorted()
            guard neighbors.count >= 3 else { return value }
            let reference = neighbors[neighbors.count / 2]
            guard reference > 0 else { return value }
            let agrees = { (candidate: Double) in
                abs(candidate - reference) / reference <= tolerance
            }
            guard !agrees(value) else { return value }
            if agrees(value / 2) { return value / 2 }
            if agrees(value * 2) { return value * 2 }
            return value
        }
    }

    /// Median over the up-to-5-frame voiced neighbourhood of each voiced frame.
    /// Deterministic, shape-preserving for real contours (a monotone rise stays a rise),
    /// spike-killing for one-frame tracker errors.
    static func medianSmooth(_ values: [Double?], window: Int = 5) -> [Double?] {
        guard values.count > 2 else { return values }
        let half = window / 2
        return values.indices.map { index in
            guard values[index] != nil else { return nil }
            let low = max(0, index - half)
            let high = min(values.count - 1, index + half)
            let neighbors = (low...high).compactMap { values[$0] }.sorted()
            guard !neighbors.isEmpty else { return values[index] }
            return neighbors[neighbors.count / 2]
        }
    }

    /// Linear resample onto a fixed point count.
    ///
    /// Nearest-neighbour here aliases: ~200 hop frames down to 64 points samples every third
    /// frame, and the terminal plunge of a falling tone lives in the last few frames, so it
    /// could be skipped entirely. Both bracketing frames unvoiced means the point is
    /// unvoiced, which keeps syllable gaps breaking the drawn path.
    static func resample(_ values: [Double?], to count: Int) -> [Double?] {
        guard count > 0, !values.isEmpty else { return Array(repeating: nil, count: count) }
        guard values.count > 1 else { return Array(repeating: values[0], count: count) }
        return (0..<count).map { destination in
            let position = Double(destination) * Double(values.count - 1) / Double(max(count - 1, 1))
            let lowIndex = min(values.count - 1, max(0, Int(position.rounded(.down))))
            let highIndex = min(values.count - 1, lowIndex + 1)
            let fraction = position - Double(lowIndex)
            switch (values[lowIndex], values[highIndex]) {
            case let (low?, high?): return low + (high - low) * fraction
            case let (low?, nil): return low
            case let (nil, high?): return high
            default: return nil
            }
        }
    }
}
