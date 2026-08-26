import AVFoundation
import DauCore
import Foundation

/// Holds the streaming analyzer and the live normalizer. Touched only from the analysis
/// queue, never from the audio thread and never from the main actor.
private final class AnalysisPipeline: @unchecked Sendable {
    struct Snapshot {
        let contour: [Double]
        let isSettled: Bool
        let seconds: Double
    }

    private var analyzer: PitchFrameAnalyzer
    private var normalizer = TakeNormalizer()

    init(sampleRate: Double) {
        analyzer = PitchFrameAnalyzer(sampleRate: sampleRate)
    }

    func push(_ samples: [Float]) -> Snapshot {
        for frame in analyzer.push(samples) {
            _ = normalizer.normalize(frame)
        }
        return snapshot()
    }

    func snapshot() -> Snapshot {
        Snapshot(
            contour: normalizer.settledContour(),
            isSettled: normalizer.isSettled,
            seconds: Double(analyzer.rawFrames.count) * 0.010
        )
    }

    func finish() -> PitchTake { analyzer.finish() }
}

/// Captures a take and drives the live trace.
///
/// One `AVAudioEngine` with a single input tap serves both jobs — the streaming analyzer that
/// draws the line, and the file write that backs "hear yours". An `AVAudioRecorder` cannot run
/// alongside an engine tap, so this owns both.
///
/// The tap callback does the least possible work: copy the samples and hand them to a serial
/// queue. Analysis happens there; the main actor only ever receives a finished snapshot, at
/// most every 16 ms. Publishing 100 frames a second straight into SwiftUI hitches the very
/// trace it is trying to draw.
@Observable
@MainActor
final class LiveToneAnalyzer {
    /// Semitone values to draw, in order.
    private(set) var drawnContour: [Double] = []
    private(set) var isRecording = false
    /// False until enough voiced frames exist to freeze a baseline — the design's
    /// "listening…" state, which now has a technical meaning.
    private(set) var isBaselineSettled = false
    private(set) var elapsedSeconds: Double = 0
    private(set) var failure: String?
    private(set) var recordedURL: URL?

    /// Shortest take worth judging. Below this a contour is noise dressed as a shape.
    static let minimumSeconds = 0.4
    static let maximumWordSeconds = 3.0
    static let maximumPhraseSeconds = 8.0

    private let engine = AVAudioEngine()
    private let queue = DispatchQueue(label: "com.ninthtile.dau.analysis")
    private var pipeline: AnalysisPipeline?
    private var recordingFile: AVAudioFile?
    private var lastPublish = Date.distantPast

    // MARK: - Lifecycle

    func start(maximumSeconds: Double = LiveToneAnalyzer.maximumWordSeconds) {
        guard !isRecording else { return }
        reset()

        if case .bundledFixture(let name) = TakeSource.current {
            startFixture(named: name)
            return
        }

        DauAudioSession.shared.beginTake()
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0 else {
            failure = "No microphone input is available."
            DauAudioSession.shared.endTake()
            return
        }

        let pipeline = AnalysisPipeline(sampleRate: format.sampleRate)
        self.pipeline = pipeline
        let url = FileManager.default.temporaryDirectory
            .appending(path: "dau-take-\(UUID().uuidString).caf")
        recordedURL = url
        recordingFile = try? AVAudioFile(forWriting: url, settings: format.settings)

        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            guard let self, let channel = buffer.floatChannelData?.pointee else { return }
            let samples = Array(UnsafeBufferPointer(start: channel, count: Int(buffer.frameLength)))
            // The only two things the audio thread does: persist, and hand off.
            try? self.recordingFile?.write(from: buffer)
            self.queue.async {
                let snapshot = pipeline.push(samples)
                Task { @MainActor [weak self] in self?.publish(snapshot) }
            }
        }

        do {
            engine.prepare()
            try engine.start()
            isRecording = true
        } catch {
            failure = "The microphone could not start."
            input.removeTap(onBus: 0)
            DauAudioSession.shared.endTake()
        }
    }

    /// Close the take and return the finished analysis.
    @discardableResult
    func stop() -> PitchTake? {
        guard isRecording else { return nil }
        isRecording = false
        if TakeSource.current == .microphone {
            engine.inputNode.removeTap(onBus: 0)
            engine.stop()
            DauAudioSession.shared.endTake()
        }
        recordingFile = nil
        guard let pipeline else { return nil }
        let take = queue.sync { pipeline.finish() }
        // Re-render against the final baseline: the line locks in as the verdict lands, and
        // from here the drawn contour and the judged contour are the same contour.
        let voiced = take.frames.compactMap { $0 }
        if !voiced.isEmpty { drawnContour = voiced }
        isBaselineSettled = true
        return take
    }

    func cancel() {
        if isRecording { _ = stop() }
        reset()
    }

    private func reset() {
        drawnContour = []
        isBaselineSettled = false
        elapsedSeconds = 0
        failure = nil
        pipeline = nil
        recordedURL = nil
        lastPublish = .distantPast
    }

    // MARK: - Publishing

    private func publish(_ snapshot: AnalysisPipeline.Snapshot) {
        elapsedSeconds = snapshot.seconds
        isBaselineSettled = snapshot.isSettled
        // Coalesce to roughly one update per frame of animation.
        let now = Date()
        guard now.timeIntervalSince(lastPublish) >= 1.0 / 60 else { return }
        lastPublish = now
        drawnContour = snapshot.contour
    }

    /// Deterministic path for UITests and screenshots: a bundled reference is pushed through
    /// the identical analyzer, so nothing about the verdict path is special-cased.
    private func startFixture(named name: String) {
        guard let (samples, rate) = FixtureAudio.samples(named: name) else {
            failure = "Fixture '\(name)' is not bundled."
            return
        }
        let pipeline = AnalysisPipeline(sampleRate: rate)
        let snapshot = pipeline.push(samples)
        self.pipeline = pipeline
        publish(snapshot)
        drawnContour = snapshot.contour
        isBaselineSettled = true
        isRecording = true
    }
}
