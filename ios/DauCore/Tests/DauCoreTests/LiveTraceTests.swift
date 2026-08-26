import Foundation
import Testing
@testable import DauCore

@Suite("live trace")
struct LiveTraceTests {
    /// The trap this exists to avoid: a rolling median chases a rising pitch, so a clean sắc
    /// would draw flat. Accumulate-then-freeze must draw a rise as a rise.
    @Test("a rising take draws as rising while it is still being spoken")
    func risingDrawsRisingLive() {
        let signal = TestSignal.glide(from: 120, to: 170, seconds: 0.6)
        var analyzer = PitchFrameAnalyzer(sampleRate: TestSignal.sampleRate)
        var normalizer = TakeNormalizer()
        var drawn: [Double] = []
        var offset = 0
        while offset < signal.count {
            let end = min(offset + 1024, signal.count)
            for frame in analyzer.push(Array(signal[offset..<end])) {
                if let value = normalizer.normalize(frame) { drawn.append(value) }
            }
            offset = end
        }
        #expect(normalizer.isSettled, "the baseline should have frozen well before the end")
        #expect(drawn.count > 20)

        // The settled render is the honest one: it must rise.
        let settled = normalizer.settledContour()
        let head = settled.prefix(settled.count / 4).reduce(0, +) / Double(settled.count / 4)
        let tail = settled.suffix(settled.count / 4).reduce(0, +) / Double(settled.count / 4)
        #expect(tail > head + 2, "a 5-semitone glide must draw as a clear rise, not flat")
    }

    /// The live baseline and the final one have to converge, or the line jumps to a different
    /// shape than the verdict was computed from.
    @Test("the live baseline agrees with the analyzer's final normalization")
    func liveBaselineMatchesFinal() {
        let signal = TestSignal.steady(150, seconds: 0.6)
        var analyzer = PitchFrameAnalyzer(sampleRate: TestSignal.sampleRate)
        var normalizer = TakeNormalizer()
        for frame in analyzer.push(signal) { _ = normalizer.normalize(frame) }

        let take = analyzer.finish()
        let liveBaseline = normalizer.finalBaselineHz()
        #expect(liveBaseline != nil)

        // Both normalize a steady tone to ~0 semitones.
        let liveSettled = normalizer.settledContour()
        let liveMean = liveSettled.reduce(0, +) / Double(liveSettled.count)
        let finalVoiced = take.frames.compactMap { $0 }
        let finalMean = finalVoiced.reduce(0, +) / Double(finalVoiced.count)
        #expect(abs(liveMean - finalMean) < 0.5)
    }

    @Test("unvoiced frames draw nothing")
    func unvoicedDrawsNothing() {
        var normalizer = TakeNormalizer()
        #expect(normalizer.normalize(PitchFrame(hz: nil, rms: 0, index: 0)) == nil)
        #expect(normalizer.isSettled == false)
    }
}

@Suite("phrase segmentation")
struct PhraseSegmentationTests {
    /// Screen 05's prompted mode, end to end, with no speech recognition anywhere: three
    /// spoken syllables separated by real pauses come back as three readable runs.
    @Test("a three-syllable phrase segments into three readable syllables")
    func phraseSegmentsIntoSyllables() {
        let phrase = TestSignal.steady(140, seconds: 0.30)          // level
            + TestSignal.silence(seconds: 0.18)
            + TestSignal.glide(from: 120, to: 165, seconds: 0.30)   // rising
            + TestSignal.silence(seconds: 0.18)
            + TestSignal.glide(from: 165, to: 120, seconds: 0.30)   // falling
        let take = PitchFrameAnalyzer.analyze(samples: phrase, sampleRate: TestSignal.sampleRate)

        let reading = PhraseToneReader.read(contour: take.frames)
        #expect(reading != nil)
        guard let reading else { return }
        #expect(reading.syllables.count == 3, "got \(reading.syllables.count)")
        #expect(reading.discardedSyllables == 0)
        #expect(reading.syllables[0].family == .level)
        #expect(reading.syllables[1].family == .rising)
        #expect(reading.syllables[2].family == .falling)
    }

    @Test("a short internal closure does not split a syllable")
    func shortClosureDoesNotSplit() {
        // ~50 ms is a consonant closure, not a word boundary.
        let single = TestSignal.steady(140, seconds: 0.25)
            + TestSignal.silence(seconds: 0.05)
            + TestSignal.steady(140, seconds: 0.25)
        let take = PitchFrameAnalyzer.analyze(samples: single, sampleRate: TestSignal.sampleRate)
        let ranges = ToneSyllableSegmenter.syllableRanges(in: take.frames)
        #expect(ranges.count == 1, "a 50 ms closure must be bridged, got \(ranges.count) runs")
    }

    @Test("nothing readable returns nil rather than a flat phrase")
    func nothingReadableReturnsNil() {
        let take = PitchFrameAnalyzer.analyze(
            samples: TestSignal.silence(seconds: 0.6), sampleRate: TestSignal.sampleRate
        )
        #expect(PhraseToneReader.read(contour: take.frames) == nil)
    }
}
