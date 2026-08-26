import Foundation

/// Derives the energy-based evidence from a take's RMS envelope.
///
/// Ported from `api/dau/tones.py::extract_features` (the `rms` block). The window fractions
/// are load-bearing and match the Python exactly: centre 0.42–0.62 against flanks 0.18–0.38
/// and 0.66–0.86 for the creak dip, and terminal 0.86–end against 0.55–0.78 for the drop.
public enum RMSEnvelope {
    /// Build energy features from a per-frame RMS envelope.
    ///
    /// - Parameters:
    ///   - rms: per-frame energy, any length; resampled to 64 points like the pitch contour.
    ///   - durationSeconds: voiced-span duration of the take.
    ///   - voicedFraction: share of frames that carried pitch.
    ///   - longestVoicingGapMs: longest unvoiced run in the middle of the take.
    public static func features(
        rms: [Double],
        durationSeconds: Double,
        voicedFraction: Double,
        longestVoicingGapMs: Double
    ) -> ToneEnergyFeatures {
        let envelope = resampledEvidence(rms)
        let size = envelope.count

        func window(_ low: Double, _ high: Double) -> [Double] {
            let lower = Int(low * Double(size))
            let upper = Int(high * Double(size))
            guard lower < upper, lower >= 0, upper <= size else { return [] }
            return Array(envelope[lower..<upper])
        }

        let center = ToneNumerics.median(window(0.42, 0.62))
        let flanks = ToneNumerics.median(window(0.18, 0.38) + window(0.66, 0.86))
        let centralDip = clamp01(1.0 - center / max(flanks, 1e-8))

        let terminal = ToneNumerics.median(window(0.86, 1.0))
        let preceding = ToneNumerics.median(window(0.55, 0.78))
        let terminalDrop = clamp01(1.0 - terminal / max(preceding, 1e-8))

        return ToneEnergyFeatures(
            durationSeconds: durationSeconds,
            voicedFraction: voicedFraction,
            longestVoicingGapMs: longestVoicingGapMs,
            centralRmsDip: centralDip,
            terminalEnergyDrop: terminalDrop
        )
    }

    /// Matches `_resample_evidence`: an empty envelope is neutral (all ones), not zeros —
    /// zeros would read as a total energy collapse and fire the nặng rule on every take.
    static func resampledEvidence(_ values: [Double]) -> [Double] {
        guard !values.isEmpty else {
            return Array(repeating: 1.0, count: ToneNumerics.analysisPoints)
        }
        return ToneNumerics.resampled(values, to: ToneNumerics.analysisPoints)
    }

    private static func clamp01(_ value: Double) -> Double {
        min(max(value, 0.0), 1.0)
    }
}
