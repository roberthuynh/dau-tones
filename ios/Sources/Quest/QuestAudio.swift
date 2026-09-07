import AVFoundation
import Foundation
import UIKit

/// Ephemeral, local-only comparison audio. A recording is practice, never an assessment.
@MainActor
@Observable
final class QuestAudio: NSObject, AVAudioPlayerDelegate {
    private var player: AVAudioPlayer?
    private var recorder: AVAudioRecorder?
    private var meterTask: Task<Void, Never>?
    private(set) var isRecording = false
    private(set) var isPlaying = false
    private(set) var hasRecording = false
    private(set) var message: String?
    private var peakPower: Float = -160
    private var startedAt: Date?
    private let takeURL = FileManager.default.temporaryDirectory.appending(path: "vietquest-current-take.m4a")
    static let maximumRecordingSeconds: TimeInterval = 15

    override init() {
        super.init()
        try? FileManager.default.removeItem(at: takeURL)
        NotificationCenter.default.addObserver(self, selector: #selector(interrupted), name: AVAudioSession.interruptionNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(interrupted), name: UIApplication.didEnterBackgroundNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(interrupted), name: AVAudioSession.routeChangeNotification, object: nil)
    }

    func playClip(_ id: String, slow: Bool = false) {
        guard !isRecording else {
            message = "Finish your recording before playing the example."
            return
        }
        guard let url = Bundle.main.url(forResource: id, withExtension: "caf", subdirectory: "Content/quest/audio") else {
            message = "This example could not be found. You can continue with its written version."
            return
        }
        play(url, slow: slow)
    }

    func toggleRecording() async -> Bool {
        if isRecording {
            finishRecording()
            return hasRecording
        }
        player?.stop()
        isPlaying = false
        clearTake()
        if DauAudioSession.shared.permission == .undetermined {
            let granted = await DauAudioSession.shared.requestPermission()
            guard granted else {
                message = "Microphone access is off. Enable it in Settings, or continue with a meaning choice."
                return false
            }
        }
        guard DauAudioSession.shared.permission == .granted else {
            message = "Microphone access is off. Enable it in Settings, or continue with a meaning choice."
            return false
        }
        // The permission sheet can take the app out of the active state.
        guard UIApplication.shared.applicationState == .active else {
            message = "Return to the app and tap Record again."
            return false
        }
        do {
            DauAudioSession.shared.beginTake()
            let recording = try AVAudioRecorder(url: takeURL, settings: [
                AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
                AVSampleRateKey: 44_100,
                AVNumberOfChannelsKey: 1,
                AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
            ])
            recording.isMeteringEnabled = true
            guard recording.prepareToRecord(), recording.record() else {
                throw CocoaError(.fileWriteUnknown)
            }
            recorder = recording
            peakPower = -160
            startedAt = Date()
            isRecording = true
            message = "Recording on this iPhone. Stops after 15 seconds."
            meterTask = Task { [weak self] in
                while !Task.isCancelled {
                    try? await Task.sleep(for: .milliseconds(100))
                    guard !Task.isCancelled, let self, self.isRecording else { return }
                    self.recorder?.updateMeters()
                    self.peakPower = max(self.peakPower, self.recorder?.averagePower(forChannel: 0) ?? -160)
                    if let start = self.startedAt, Date().timeIntervalSince(start) >= Self.maximumRecordingSeconds {
                        self.finishRecording()
                        return
                    }
                }
            }
            return false
        } catch {
            recorder = nil
            DauAudioSession.shared.endTake()
            message = "Recording could not start. Try again, or continue with a meaning choice."
            return false
        }
    }

    func replayTake() {
        guard !isRecording, hasRecording else { return }
        play(takeURL)
    }

    /// Every new prompt discards the old take so its replay cannot be mistaken for this answer.
    func clearTake() {
        meterTask?.cancel()
        meterTask = nil
        if isRecording {
            recorder?.stop()
            DauAudioSession.shared.endTake()
        }
        recorder = nil
        isRecording = false
        hasRecording = false
        startedAt = nil
        try? FileManager.default.removeItem(at: takeURL)
    }

    func stop() {
        player?.stop()
        player = nil
        isPlaying = false
        clearTake()
    }

    private func play(_ url: URL, slow: Bool = false) {
        player?.stop()
        DauAudioSession.shared.activate(.referencePlayback)
        do {
            let playback = try AVAudioPlayer(contentsOf: url)
            playback.delegate = self
            playback.enableRate = true
            playback.rate = slow ? 0.8 : 1
            guard playback.prepareToPlay(), playback.play() else { throw CocoaError(.fileReadCorruptFile) }
            player = playback
            isPlaying = true
            message = nil
        } catch {
            isPlaying = false
            message = "That audio could not play. Try again or continue with the written version."
        }
    }

    private func finishRecording() {
        guard isRecording else { return }
        let duration = recorder?.currentTime ?? 0
        recorder?.updateMeters()
        peakPower = max(peakPower, recorder?.averagePower(forChannel: 0) ?? -160)
        meterTask?.cancel()
        meterTask = nil
        recorder?.stop()
        recorder = nil
        isRecording = false
        DauAudioSession.shared.endTake()
        hasRecording = duration >= 0.35 && peakPower > -45 && FileManager.default.fileExists(atPath: takeURL.path)
        if hasRecording {
            message = "Ready to replay. Compare with the example; your pronunciation has not been graded."
        } else {
            try? FileManager.default.removeItem(at: takeURL)
            message = "We couldn't hear a clear take. Try closer to the microphone, or continue without recording."
        }
    }

    @objc private func interrupted(_ notification: Notification) {
        // Category changes caused by our own setup are not route interruptions.
        if notification.name == AVAudioSession.routeChangeNotification {
            let raw = notification.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt
            guard raw == AVAudioSession.RouteChangeReason.oldDeviceUnavailable.rawValue else { return }
        }
        let wasRecording = isRecording
        stop()
        if wasRecording { message = "Recording interrupted. Tap Record to try again." }
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor [weak self] in
            self?.isPlaying = false
            if !flag { self?.message = "Playback was interrupted. Tap Listen to try again." }
        }
    }

    nonisolated func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        Task { @MainActor [weak self] in
            self?.isPlaying = false
            self?.message = "That audio could not be decoded. Try the example again or continue with its written version."
        }
    }
}
