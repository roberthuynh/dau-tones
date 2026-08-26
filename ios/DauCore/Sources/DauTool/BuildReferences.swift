import AVFoundation
import DauCore
import Foundation

/// Recomputes every shipped reference contour with the **Swift** analyzer, and reports how
/// far each one sits from the Python contour stored in the generation report.
///
/// This is not a nicety. The stored contours came from a librosa-based extractor; learner
/// contours come from `PitchFrameAnalyzer`. Drawing one against the other — and, now, feeding
/// the difference into the shape-match percentage — would read estimator disagreement as
/// learner error and put that number in front of the learner as if it were their mistake.
///
/// So the app ships Swift-derived targets, the Python contours stay test fixtures, and the
/// deviation between them is printed here rather than assumed.
enum BuildReferences {
    struct ReferenceContour: Codable {
        let wordID: String
        let accent: String
        let tone: String
        /// 64-point speaker-relative semitones, computed by PitchFrameAnalyzer.
        let contour: [Double]
        let durationSeconds: Double
        let voicedFraction: Double
    }

    static func run(repoRoot: String, outputDirectory: String, fixtures: String?) throws {
        let root = URL(fileURLWithPath: repoRoot, isDirectory: true)
        let outputURL = URL(fileURLWithPath: outputDirectory, isDirectory: true)
        try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)

        let stored = try storedContours(path: fixtures)
        var results: [ReferenceContour] = []
        var deviations: [(String, Double)] = []
        var unreadable: [String] = []

        for accent in Accent.allCases {
            let directory = root.appending(path: "targets/\(accent.rawValue)")
            let files = (try? FileManager.default.contentsOfDirectory(atPath: directory.path)) ?? []
            for file in files.sorted() where file.hasSuffix(".wav") {
                let wordID = String(file.dropLast(4))
                let url = directory.appending(path: file)
                guard let (samples, rate) = try? decode(url: url) else {
                    unreadable.append("\(accent.rawValue)/\(wordID)")
                    continue
                }
                let take = PitchFrameAnalyzer.analyze(samples: samples, sampleRate: rate)
                // An unvoiced or unreadable reference is a bad reference — better to know at
                // build time than to draw a target line the app's own judge disagrees with.
                guard let contour = filled(take.contour) else {
                    let voiced = take.contour.compactMap { $0 }.count
                    unreadable.append(
                        "\(accent.rawValue)/\(wordID) (voiced \(voiced)/64 points, "
                        + "voicedFraction \(String(format: "%.2f", take.voicedFraction)), "
                        + "\(String(format: "%.2f", take.durationSeconds))s)"
                    )
                    continue
                }
                let key = "\(accent.rawValue)/\(wordID)"
                if let pythonContour = stored[key] {
                    deviations.append((key, rms(contour, pythonContour)))
                }
                results.append(ReferenceContour(
                    wordID: wordID,
                    accent: accent.rawValue,
                    tone: take.contourFeatures.map { _ in "" } ?? "",
                    contour: contour,
                    durationSeconds: take.durationSeconds,
                    voicedFraction: take.voicedFraction
                ))
            }
        }

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let destination = outputURL.appending(path: "reference-contours-v1.json")
        try encoder.encode(results).write(to: destination, options: Data.WritingOptions.atomic)
        print("wrote \(destination.path) — \(results.count) Swift-computed reference contours")

        if !unreadable.isEmpty {
            print("\nunreadable references (excluded):")
            unreadable.forEach { print("  \($0)") }
        }

        guard !deviations.isEmpty else { return }
        deviations.sort { $0.1 > $1.1 }
        let values = deviations.map(\.1).sorted()
        print("""

        Cross-estimator deviation, Swift vs Python (semitones RMS over 64 points)
          n=\(values.count)  median=\(String(format: "%.2f", values[values.count / 2]))  \
        p90=\(String(format: "%.2f", values[min(values.count - 1, 9 * values.count / 10)]))  \
        max=\(String(format: "%.2f", values.last!))

        Worst five — a reference far from its own Python contour is a reference worth
        re-cutting, not a threshold worth moving:
        """)
        for (key, deviation) in deviations.prefix(5) {
            print(String(format: "  %-28s %.2f st", (key as NSString).utf8String!, deviation))
        }
        // Broken, not merely different. Two estimators disagreeing by more than a musical
        // third on average means something is actually wrong.
        if let worst = values.last, worst > 3.0 {
            print("\nNOTE: \(deviations.filter { $0.1 > 3.0 }.count) reference(s) exceed 3 st — inspect before shipping them.")
        }
    }

    /// Decode any AVFoundation-readable file to mono Float samples.
    private static func decode(url: URL) throws -> ([Float], Double) {
        let file = try AVAudioFile(forReading: url)
        let format = file.processingFormat
        guard let buffer = AVAudioPCMBuffer(
            pcmFormat: format, frameCapacity: AVAudioFrameCount(file.length)
        ) else { throw CocoaError(.fileReadCorruptFile) }
        try file.read(into: buffer)
        guard let channel = buffer.floatChannelData?.pointee else {
            throw CocoaError(.fileReadCorruptFile)
        }
        let samples = Array(UnsafeBufferPointer(start: channel, count: Int(buffer.frameLength)))
        return (samples, format.sampleRate)
    }

    /// A reference must be fully voiced across the analysis axis to be drawn as a target.
    /// `PitchTake.contour` is already trimmed to the utterance, so this only has to bridge
    /// interior gaps.
    private static func filled(_ contour: [Double?]) -> [Double]? {
        guard contour.compactMap({ $0 }).count >= ToneContourFeatures.minimumVoicedPoints
        else { return nil }
        let interpolated = ToneNumerics.interpolatingGaps(in: contour)
        guard interpolated.count == contour.count else { return nil }
        return ToneNumerics.resampled(interpolated, to: ToneNumerics.analysisPoints)
    }

    private static func storedContours(path: String?) throws -> [String: [Double]] {
        guard let path else { return [:] }
        struct Fixtures: Decodable {
            struct Take: Decodable {
                let wordID: String
                let accent: String
                let contour: [Double]
            }
            let takes: [Take]
        }
        let data = try Data(contentsOf: URL(fileURLWithPath: path))
        let fixtures = try JSONDecoder().decode(Fixtures.self, from: data)
        return Dictionary(
            uniqueKeysWithValues: fixtures.takes.map { ("\($0.accent)/\($0.wordID)", $0.contour) }
        )
    }

    private static func rms(_ a: [Double], _ b: [Double]) -> Double {
        guard a.count == b.count, !a.isEmpty else { return .infinity }
        return (zip(a, b).map { ($0 - $1) * ($0 - $1) }.reduce(0, +) / Double(a.count)).squareRoot()
    }
}
