import Foundation
@testable import DauCore

/// Hand-built contours for tests that need a known shape rather than a real take.
///
/// All values are semitones relative to the take's own median, matching what the analyzer
/// produces, and all are 64 points so they enter the judge on the calibrated axis.
enum SyntheticContour {
    static func make(_ shape: (Double) -> Double) -> [Double] {
        (0..<ToneNumerics.analysisPoints).map { index in
            shape(Double(index) / Double(ToneNumerics.analysisPoints - 1))
        }
    }

    /// Dead flat.
    static let level = make { _ in 0 }
    /// A steady climb of `semitones` across the syllable.
    static func rise(_ semitones: Double) -> [Double] { make { $0 * semitones } }
    /// A steady drop of `semitones`.
    static func fall(_ semitones: Double) -> [Double] { make { -$0 * semitones } }
    /// A symmetric V bottoming out at `depth` semitones below the start, at position 0.5.
    static func dip(depth: Double) -> [Double] {
        make { position in
            let distance = abs(position - 0.5) * 2
            return -depth * (1 - distance)
        }
    }
    /// Gentle noise-like wobble that must never read as a real shape.
    static let wobble = make { position in 0.35 * sin(position * .pi * 4) }

    static func features(_ points: [Double], energy: ToneEnergyFeatures = .neutral) -> ToneTakeFeatures {
        ToneTakeFeatures(
            contour: ToneContourFeatures.of(resampledPoints: points, sampleCount: points.count)!,
            energy: energy
        )
    }
}
