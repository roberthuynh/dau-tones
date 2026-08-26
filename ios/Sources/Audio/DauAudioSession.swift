import AVFoundation
import Foundation

/// The single owner of `AVAudioSession` for the app.
///
/// Ported from nghe's `AudioSessionCoordinator`, trimmed to the three modes Dấu needs. Two
/// behaviours are carried over verbatim because they were paid for in bugs:
///
///  - **No `.allowBluetoothHFP`.** Routing capture to a Bluetooth headset drops the mic to an
///    8 kHz HFP path, which starves the RMS gate and produces contours that look like a quiet
///    monotone. Tone capture stays on the built-in mic even when AirPods are connected.
///    (nghe `44beca63`.)
///  - **A live take wins the session.** Playback finishing must not tear down a session that a
///    recording is currently using, so restoring to ambient is debounced and skipped outright
///    while the mic is live. (nghe `0227fbf5`.)
@MainActor
final class DauAudioSession {
    enum Mode {
        case ambient
        case referencePlayback
        case toneRecording
    }

    static let shared = DauAudioSession()

    private(set) var mode: Mode = .ambient
    /// True from the moment a take is armed until it is fully finished.
    private(set) var micIsLive = false
    private var restoreWorkItem: DispatchWorkItem?

    private init() {}

    func activate(_ mode: Mode) {
        // A live take owns the session; nothing else may take it away mid-recording.
        if micIsLive, mode != .toneRecording { return }
        restoreWorkItem?.cancel()
        restoreWorkItem = nil

        let session = AVAudioSession.sharedInstance()
        do {
            switch mode {
            case .ambient:
                try session.setCategory(.ambient, mode: .default, options: [.mixWithOthers])
            case .referencePlayback:
                try session.setCategory(.playback, mode: .spokenAudio, options: [])
            case .toneRecording:
                // Deliberately no .allowBluetoothHFP — see the type comment.
                try session.setCategory(
                    .playAndRecord, mode: .spokenAudio,
                    options: [.defaultToSpeaker, .duckOthers]
                )
            }
            try session.setActive(true, options: [])
            self.mode = mode
        } catch {
            // A session that will not configure is not fatal: the recorder surfaces it as a
            // take that could not be read, which is already an honest state.
        }
    }

    func beginTake() {
        micIsLive = true
        activate(.toneRecording)
    }

    func endTake() {
        micIsLive = false
        scheduleRestore()
    }

    /// Debounced so a rapid play/record alternation does not thrash the session.
    private func scheduleRestore() {
        restoreWorkItem?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self, !self.micIsLive else { return }
            self.activate(.ambient)
        }
        restoreWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4, execute: work)
    }

    /// Ask for microphone access, and report whether it was granted.
    ///
    /// Called from the privacy card on first run rather than at the moment of recording, so
    /// the very first hold records into an already-live route instead of losing its opening
    /// syllable to the permission sheet. (nghe's warm-up, same reason.)
    func requestPermission() async -> Bool {
        await withCheckedContinuation { continuation in
            AVAudioApplication.requestRecordPermission { granted in
                continuation.resume(returning: granted)
            }
        }
    }

    var permission: AVAudioApplication.recordPermission {
        AVAudioApplication.shared.recordPermission
    }
}
