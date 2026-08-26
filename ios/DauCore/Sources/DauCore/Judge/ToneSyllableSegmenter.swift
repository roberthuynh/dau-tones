import Foundation

/// Splits a pitch contour into syllable-sized voiced runs so a phrase can be read one tone at
/// a time.
///
/// Ported verbatim from nghe's `ToneMirror.swift`. This is what makes screen 05's prompted
/// captions possible **without any speech recognition**: for a phrase whose words are already
/// known, segmentation supplies the timing and the per-syllable shape, and the rule table
/// supplies the per-word verdict. No ASR, no permission prompt, no device-availability risk.
///
/// The input is the raw 10 ms-hop semitone series (`PitchTake.frames`) — NOT the display
/// contour, which is resampled to a fixed point count and loses exactly the gap structure
/// this depends on. In Vietnamese speech the silence between syllables is a run of unvoiced
/// frames; a run long enough (~120 ms) is a boundary, while the brief consonant closures
/// inside a syllable are shorter and get bridged.
public enum ToneSyllableSegmenter {
    /// Voiced runs of the contour, in order. A nil-run of at least `minimumGapFrames`
    /// separates syllables; shorter gaps are internal and stay inside their run. Runs
    /// carrying fewer than `minimumVoicedFrames` voiced frames are discarded as noise — the
    /// same floor below which `ToneShapeJudge` refuses to read a shape.
    public static func syllableRanges(
        in contour: [Double?],
        minimumGapFrames: Int = 12,
        minimumVoicedFrames: Int = 8
    ) -> [Range<Int>] {
        var runs: [Range<Int>] = []
        var runStart: Int?
        var lastVoiced = 0
        for index in contour.indices {
            if contour[index] != nil {
                if let start = runStart {
                    // Inside a run: a gap shorter than the boundary length is bridged; a
                    // longer one closes the run behind it.
                    if index - lastVoiced - 1 >= minimumGapFrames {
                        runs.append(start..<(lastVoiced + 1))
                        runStart = index
                    }
                } else {
                    runStart = index
                }
                lastVoiced = index
            }
        }
        if let start = runStart {
            runs.append(start..<(lastVoiced + 1))
        }
        return runs.filter { range in
            contour[range].count(where: { $0 != nil }) >= minimumVoicedFrames
        }
    }
}

/// What a whole phrase looked like, one reading per syllable. `syllables` and
/// `syllableRanges` are parallel.
public struct PhraseToneReading: Equatable, Sendable {
    public let syllables: [ToneShapeReading]
    public let syllableRanges: [Range<Int>]
    /// Voiced runs that could NOT be read. Surfaced so an 8-word phrase that reads as 6 says
    /// so, instead of silently looking like a clean 6-word take — the caption's honest
    /// "we read 6 of your 8 words" line comes from here.
    public let discardedSyllables: Int

    public init(
        syllables: [ToneShapeReading],
        syllableRanges: [Range<Int>],
        discardedSyllables: Int = 0
    ) {
        self.syllables = syllables
        self.syllableRanges = syllableRanges
        self.discardedSyllables = discardedSyllables
    }
}

public enum PhraseToneReader {
    /// A run with at least this many voiced frames is a syllable the speaker attempted — if
    /// it still can't be read, that is reported as discarded rather than silently dropped.
    /// Shorter runs are noise and stay silent.
    static let attemptedSyllableFloor = 3

    /// Read a multi-syllable contour: segment, then judge each slice on its own. Every
    /// `ToneShapeJudge` feature is relative (end minus start, slopes over a normalized axis),
    /// so a slice needs no re-normalization against the whole take.
    ///
    /// Returns nil when nothing in the take was readable — surface that as "try again",
    /// never as a flat phrase.
    public static func read(
        contour: [Double?],
        maximumSyllables: Int = 12
    ) -> PhraseToneReading? {
        // Segment twice: once at the attempted floor (what the speaker tried to say) and once
        // at the readable floor (what the judge can read). The difference is the honest
        // "read 6 of your 8" count.
        let attempted = ToneSyllableSegmenter.syllableRanges(
            in: contour, minimumVoicedFrames: Self.attemptedSyllableFloor
        )
        let readable = ToneSyllableSegmenter.syllableRanges(in: contour)
        var discarded = attempted.count - readable.count
        let ranges = readable.prefix(maximumSyllables)
        discarded += readable.count - ranges.count
        var syllables: [ToneShapeReading] = []
        var kept: [Range<Int>] = []
        for range in ranges {
            guard let reading = ToneShapeJudge.read(contour: Array(contour[range]))
            else { discarded += 1; continue }
            syllables.append(reading)
            kept.append(range)
        }
        guard !syllables.isEmpty else { return nil }
        return PhraseToneReading(
            syllables: syllables, syllableRanges: kept, discardedSyllables: max(0, discarded)
        )
    }
}
