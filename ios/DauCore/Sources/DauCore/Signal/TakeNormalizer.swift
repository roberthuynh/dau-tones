import Foundation

/// Converts live pitch frames into the semitone values the trace draws, while the take is
/// still in progress.
///
/// This is the piece that decides whether the live line tells the truth, and the obvious
/// implementation is wrong. Semitones are relative to the take's own median F0, which is not
/// known until the take ends. A **rolling** median looks like the natural answer and is a
/// trap: it chases a rising pitch, so a clean sắc draws flat — precisely the failure the whole
/// product exists to fix.
///
/// So: accumulate, then freeze.
///  1. Before `baselineFrameCount` voiced frames, draw provisionally against the first voiced
///     frame. The UI shows this as "listening…" — the design's state now has a technical
///     meaning.
///  2. At that count, take the median of those frames and **freeze it for the rest of the
///     take**, re-rendering the provisional segment against it in one animated settle.
///  3. On stop, recompute against the median of *all* voiced frames (the offline definition,
///     which is what the verdict used) and re-render once. The line locking in is the
///     design's "verdict lands the moment you stop" beat, not a compromise.
public struct TakeNormalizer: Sendable {
    /// Voiced frames required before the baseline is trustworthy — 15 frames at a 10 ms hop
    /// is 150 ms, about the point a syllable's pitch has settled.
    public static let baselineFrameCount = 15

    public private(set) var isSettled = false
    private var voicedHz: [Double] = []
    private var frozenBaseline: Double?

    public init() {}

    /// The baseline in Hz the trace is currently drawn against, if any.
    public var baselineHz: Double? { frozenBaseline }

    /// Add a raw frame and get the value to draw, or nil for unvoiced.
    ///
    /// The returned value is provisional until `isSettled` becomes true; the view should
    /// re-render its trailing segment when that flips.
    public mutating func normalize(_ frame: PitchFrame) -> Double? {
        guard let hz = frame.hz, hz > 0 else { return nil }
        voicedHz.append(hz)
        if frozenBaseline == nil {
            if voicedHz.count >= Self.baselineFrameCount {
                frozenBaseline = Self.median(voicedHz)
                isSettled = true
            } else {
                // Provisional: against the first voiced frame, so the line still moves in the
                // right direction before the baseline exists.
                frozenBaseline = nil
                return Self.semitones(hz, over: voicedHz[0])
            }
        }
        return Self.semitones(hz, over: frozenBaseline ?? voicedHz[0])
    }

    /// Re-render everything so far against the current baseline. Call when `isSettled` flips.
    public func settledContour() -> [Double] {
        let baseline = frozenBaseline ?? voicedHz.first ?? 0
        guard baseline > 0 else { return [] }
        return voicedHz.map { Self.semitones($0, over: baseline) }
    }

    /// The final normalization, matching what `PitchFrameAnalyzer.finish()` computes: the
    /// median of *all* voiced frames. Live and final must agree once the take is closed.
    public func finalBaselineHz() -> Double? {
        guard voicedHz.count >= 3 else { return nil }
        return Self.median(voicedHz)
    }

    static func semitones(_ hz: Double, over baseline: Double) -> Double {
        guard baseline > 0, hz > 0 else { return 0 }
        return min(12, max(-12, 12 * log2(hz / baseline)))
    }

    static func median(_ values: [Double]) -> Double {
        guard !values.isEmpty else { return 0 }
        let sorted = values.sorted()
        return sorted[sorted.count / 2]
    }
}
