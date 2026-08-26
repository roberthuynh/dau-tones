import Foundation
@testable import DauCore

/// The 36 accepted reference takes from `targets/generation-report.json`, carried as test
/// fixtures only — they are never shipped. Each holds the Python-derived 64-point contour
/// plus the feature block `dấu` computed from it, which is what pins the Swift port.
struct GoldenTake: Decodable {
    let wordID: String
    let surface: String
    let tone: String
    let accent: String
    let sourceMode: String
    let model: String?
    let sha256: String
    let accentFamilyVerified: Bool
    let contour: [Double]
    let features: StoredFeatures
    let energy: StoredEnergy

    struct StoredFeatures: Decodable {
        let start, end, slope, curvature, pitchRange: Double
        let minimum, dipPosition, recovery, finalRise: Double
    }

    struct StoredEnergy: Decodable {
        let durationSeconds, voicedFraction, longestVoicingGapMs: Double
        let centralRmsDip, terminalEnergyDrop: Double
    }

    var toneMark: ToneMark { ToneMark(rawValue: toneKey)! }
    /// Fixture tones are spelled `hoi`/`nga`/`sac`/... which already match ToneMark's raw
    /// values; `ngang`, `huyen`, `nang` likewise.
    private var toneKey: String { tone }
    var accentValue: Accent { Accent(rawValue: accent)! }
    /// A shorthand naming one take, used in failure messages: "south ma-ghost".
    var label: String { "\(accent) \(wordID)" }

    var takeFeatures: ToneTakeFeatures {
        ToneTakeFeatures(
            contour: ToneContourFeatures.of(
                resampledPoints: contour, sampleCount: contour.count
            )!,
            energy: ToneEnergyFeatures(
                durationSeconds: energy.durationSeconds,
                voicedFraction: energy.voicedFraction,
                longestVoicingGapMs: energy.longestVoicingGapMs,
                centralRmsDip: energy.centralRmsDip,
                terminalEnergyDrop: energy.terminalEnergyDrop
            )
        )
    }
}

enum GoldenFixtures {
    struct File: Decodable {
        let schemaVersion: Int
        let source: String
        let takes: [GoldenTake]
    }

    static let all: [GoldenTake] = {
        let url = Bundle.module.url(
            forResource: "dau-golden-contours-v1", withExtension: "json",
            subdirectory: "Fixtures"
        )!
        let file = try! JSONDecoder().decode(File.self, from: Data(contentsOf: url))
        precondition(file.takes.count == 36, "expected 36 accepted takes")
        return file.takes
    }()
}
