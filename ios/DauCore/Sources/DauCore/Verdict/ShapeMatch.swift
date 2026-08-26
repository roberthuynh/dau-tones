import Foundation

/// How closely a take's contour followed the target it was aiming at.
///
/// This is the one number Dấu shows, and it is a **measurement, not a classification**. When
/// the learner is drilling a known target, distance to that target is observed fact; that is
/// what separates it from the "94% class confidence" the design originally carried, which
/// came from a 72%-accurate template classifier and is not shipped.
///
/// Rules for using it, enforced by `VerdictPolicy` and its tests:
///  - It is called "shape match" in the UI. Never "score", "accuracy", or "confidence".
///  - It is `nil` whenever the signal will not support it. No number beats a soft one.
///  - It never leads. The rule verdict is primary; this sits underneath as "how close".
public struct ShapeMatch: Equatable, Sendable {
    /// 0...100, rounded. Shown as a percentage.
    public let percent: Int
    /// The underlying RMS deviation in semitones, kept for history and coaching.
    public let rmsDeviationSemitones: Double

    public init(percent: Int, rmsDeviationSemitones: Double) {
        self.percent = percent
        self.rmsDeviationSemitones = rmsDeviationSemitones
    }

    /// Semitone RMS deviation at which the match reads 0%.
    ///
    /// Calibrated 2026-08-26 from the 36-take corpus (`dau-tool calibrate-match` recomputes
    /// it): within-accent pairs of the *same* tone differ by a median of 1.90 semitones RMS,
    /// pairs of *different* tones by 4.98. A scale of 8 puts a same-tone take at about 76%
    /// and a different-tone take at about 38% — separation a learner can read, without
    /// implying a precision the signal does not have.
    ///
    /// Note the corpus pairs are different *words* sharing a tone, which varies more than one
    /// learner repeating one word against its own reference, so real drilling should sit
    /// above these numbers.
    public static let scaleSemitones = 8.0

    /// Compare a learner contour against a reference, both 64-point speaker-relative
    /// semitone contours.
    ///
    /// Both sides must come from the **same** pitch estimator. The shipped references are
    /// recomputed with `PitchFrameAnalyzer` at build time for exactly this reason: measuring
    /// a Swift-derived learner line against a librosa-derived target line would read
    /// estimator disagreement as learner error and put that difference in this number.
    public static func between(learner: [Double], reference: [Double]) -> ShapeMatch? {
        guard learner.count == reference.count, !learner.isEmpty else { return nil }
        let squares = zip(learner, reference).map { ($0 - $1) * ($0 - $1) }
        let deviation = (squares.reduce(0, +) / Double(squares.count)).squareRoot()
        let ratio = 1.0 - deviation / scaleSemitones
        let percent = Int((max(0.0, min(1.0, ratio)) * 100).rounded())
        return ShapeMatch(percent: percent, rmsDeviationSemitones: deviation)
    }
}
