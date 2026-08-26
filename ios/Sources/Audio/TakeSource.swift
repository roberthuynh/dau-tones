import AVFoundation
import DauCore
import Foundation

/// Where a take's audio comes from.
///
/// The fixture case is what makes screens 03/04/05 testable without a microphone: with
/// `-uiTestTakeFixture north-ma-mother` the app feeds a bundled reference recording through
/// the identical analyzer, so the whole verdict path can be driven deterministically in the
/// simulator — and could be built before live capture existed at all.
enum TakeSource: Equatable {
    case microphone
    case bundledFixture(String)

    static var current: TakeSource {
        if let fixture = LaunchArguments.takeFixture { return .bundledFixture(fixture) }
        return .microphone
    }
}

enum FixtureAudio {
    /// Decode a bundled reference, named "<accent>-<wordID>".
    static func samples(named fixture: String, bundle: Bundle = .main) -> ([Float], Double)? {
        let parts = fixture.split(separator: "-", maxSplits: 1).map(String.init)
        guard parts.count == 2 else { return nil }
        guard let url = bundle.url(
            forResource: parts[1], withExtension: "m4a",
            subdirectory: "Content/targets/\(parts[0])"
        ) else { return nil }
        return decode(url: url)
    }

    static func decode(url: URL) -> ([Float], Double)? {
        guard let file = try? AVAudioFile(forReading: url) else { return nil }
        let format = file.processingFormat
        guard let buffer = AVAudioPCMBuffer(
            pcmFormat: format, frameCapacity: AVAudioFrameCount(file.length)
        ), (try? file.read(into: buffer)) != nil,
        let channel = buffer.floatChannelData?.pointee else { return nil }
        let samples = Array(UnsafeBufferPointer(start: channel, count: Int(buffer.frameLength)))
        return (samples, format.sampleRate)
    }
}
