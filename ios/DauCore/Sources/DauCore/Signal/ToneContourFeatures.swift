import Foundation

/// The contour-derived half of `dấu`'s feature block. Computed over a contour resampled to
/// 64 points against an x axis normalized to [0, 1], so every slope is in semitones per
/// whole syllable.
///
/// These nine fields correspond 1:1 with the Python `ContourFeatures` pitch fields, and the
/// golden tests assert they agree to 1e-4. Do not add fields here — energy-derived evidence
/// lives in `ToneEnergyFeatures` precisely so that comparison stays exact.
public struct ToneContourFeatures: Equatable, Sendable, Codable {
    /// Median of the first tenth of the contour.
    public let start: Double
    /// Median of the last tenth.
    public let end: Double
    /// Least-squares slope across the whole syllable.
    public let slope: Double
    /// Second-half slope minus first-half slope: positive means it turned upward.
    public let curvature: Double
    /// 95th minus 5th percentile. Percentiles, not min/max, so one bad frame does not decide
    /// whether a take was flat.
    public let pitchRange: Double
    public let minimum: Double
    /// Where the lowest point sits, 0 at the start and 1 at the end.
    public let dipPosition: Double
    /// How far it climbed back from its lowest point.
    public let recovery: Double
    /// Slope over the last third alone.
    public let finalRise: Double
    /// Points used, after interpolating across unvoiced frames.
    public let sampleCount: Int

    public init(
        start: Double, end: Double, slope: Double, curvature: Double, pitchRange: Double,
        minimum: Double, dipPosition: Double, recovery: Double, finalRise: Double,
        sampleCount: Int
    ) {
        self.start = start
        self.end = end
        self.slope = slope
        self.curvature = curvature
        self.pitchRange = pitchRange
        self.minimum = minimum
        self.dipPosition = dipPosition
        self.recovery = recovery
        self.finalRise = finalRise
        self.sampleCount = sampleCount
    }

    /// Compute the nine pitch features from a speaker-relative contour (semitones against
    /// the take's own median F0), where nil marks an unvoiced frame.
    ///
    /// Returns nil when there is not enough voiced signal to say anything — the caller must
    /// surface that as "try again", never as a flat take.
    public static func of(contour: [Double?]) -> ToneContourFeatures? {
        let voiced = contour.compactMap { $0 }
        guard voiced.count >= minimumVoicedPoints else { return nil }
        let filled = ToneNumerics.interpolatingGaps(in: contour)
        let points = ToneNumerics.resampled(filled, to: ToneNumerics.analysisPoints)
        guard points.count == ToneNumerics.analysisPoints else { return nil }
        return of(resampledPoints: points, sampleCount: voiced.count)
    }

    /// Compute from an already-resampled 64-point contour with no unvoiced frames — the
    /// shape the stored reference targets arrive in.
    public static func of(resampledPoints points: [Double], sampleCount: Int) -> ToneContourFeatures? {
        let count = ToneNumerics.analysisPoints
        guard points.count == count else { return nil }

        let axis = (0..<count).map { Double($0) / Double(count - 1) }
        let edge = max(3, count / 10)
        let midpoint = count / 2
        let tailStart = Int(Double(count) * 0.68)

        let firstHalfSlope = ToneNumerics.slope(x: Array(axis[..<midpoint]), y: Array(points[..<midpoint]))
        let secondHalfSlope = ToneNumerics.slope(x: Array(axis[midpoint...]), y: Array(points[midpoint...]))
        // First occurrence on a tie, matching numpy's argmin.
        let lowestIndex = points.enumerated().min { $0.element < $1.element }?.offset ?? 0
        let lowest = points[lowestIndex]
        let endValue = ToneNumerics.median(Array(points.suffix(edge)))

        return ToneContourFeatures(
            start: ToneNumerics.median(Array(points.prefix(edge))),
            end: endValue,
            slope: ToneNumerics.slope(x: axis, y: points),
            curvature: secondHalfSlope - firstHalfSlope,
            pitchRange: ToneNumerics.percentile(points, 95) - ToneNumerics.percentile(points, 5),
            minimum: lowest,
            dipPosition: Double(lowestIndex) / Double(count - 1),
            recovery: endValue - lowest,
            finalRise: ToneNumerics.slope(x: Array(axis[tailStart...]), y: Array(points[tailStart...])),
            sampleCount: sampleCount
        )
    }

    /// Fewest voiced points worth reading. Below this the contour is noise dressed as a shape.
    public static let minimumVoicedPoints = 8
}

/// The energy-derived half of the feature block.
///
/// The rule table cannot judge nặng or Southern hỏi/ngã on pitch alone: nặng needs duration
/// and a terminal energy drop, and the merged Southern dipping family needs creak evidence.
/// Together those cover 4 of the 19 shipped words, so this is not optional work.
public struct ToneEnergyFeatures: Equatable, Sendable, Codable {
    public let durationSeconds: Double
    /// Share of frames that carried pitch.
    public let voicedFraction: Double
    /// Longest run of unvoiced frames, in milliseconds — a glottal interruption.
    public let longestVoicingGapMs: Double
    /// How far the middle of the syllable dips in energy relative to its flanks, 0...1.
    /// Creak shows up here.
    public let centralRmsDip: Double
    /// How far energy falls away at the very end, 0...1.
    public let terminalEnergyDrop: Double

    public init(
        durationSeconds: Double, voicedFraction: Double, longestVoicingGapMs: Double,
        centralRmsDip: Double, terminalEnergyDrop: Double
    ) {
        self.durationSeconds = durationSeconds
        self.voicedFraction = voicedFraction
        self.longestVoicingGapMs = longestVoicingGapMs
        self.centralRmsDip = centralRmsDip
        self.terminalEnergyDrop = terminalEnergyDrop
    }

    /// Neutral evidence — used where no energy contour is available. Deliberately the values
    /// a flat unit envelope produces, so `dấu`'s default path is reproduced exactly.
    public static let neutral = ToneEnergyFeatures(
        durationSeconds: 0.5,
        voicedFraction: 1.0,
        longestVoicingGapMs: 0.0,
        centralRmsDip: 0.0,
        terminalEnergyDrop: 0.0
    )
}

/// Everything the judge and the rule table need about one take.
public struct ToneTakeFeatures: Equatable, Sendable, Codable {
    public let contour: ToneContourFeatures
    public let energy: ToneEnergyFeatures

    public init(contour: ToneContourFeatures, energy: ToneEnergyFeatures = .neutral) {
        self.contour = contour
        self.energy = energy
    }
}
