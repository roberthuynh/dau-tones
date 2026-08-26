import DauCore
import Foundation
import Speech

/// Small, durable preferences. UserDefaults is the right home: a handful of values, backed
/// up with the device, and cheap to read at launch.
@Observable
final class DauSettings {
    private enum Key {
        static let accent = "dau.accent"
        static let onboarded = "dau.onboarded"
        static let reminderHour = "dau.reminderHour"
        static let onDeviceASR = "dau.onDeviceVietnameseASR"
    }

    private let defaults: UserDefaults

    var accent: Accent {
        didSet { defaults.set(accent.rawValue, forKey: Key.accent) }
    }
    var hasOnboarded: Bool {
        didSet { defaults.set(hasOnboarded, forKey: Key.onboarded) }
    }
    /// Whether this device can recognize Vietnamese **on-device**.
    ///
    /// Probed in Phase A so the answer is known long before free-speech captions are built on
    /// it, and re-probed rather than cached forever: it flips to true when someone adds
    /// Vietnamese under Settings › General › Keyboard › Dictation Languages.
    private(set) var supportsOnDeviceVietnamese: Bool

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        let stored = defaults.string(forKey: Key.accent).flatMap(Accent.init(rawValue:))
        self.accent = stored ?? .south
        self.hasOnboarded = defaults.bool(forKey: Key.onboarded)
        self.supportsOnDeviceVietnamese = defaults.bool(forKey: Key.onDeviceASR)
        if LaunchArguments.resetProgress { reset() }
        if LaunchArguments.skipOnboarding { hasOnboarded = true }
    }

    func reset() {
        accent = .south
        hasOnboarded = false
    }

    /// Cheap, and worth doing on every Settings appearance — the capability is user-mutable.
    func probeOnDeviceRecognition() {
        let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "vi-VN"))
        let supported = recognizer?.supportsOnDeviceRecognition ?? false
        supportsOnDeviceVietnamese = supported
        defaults.set(supported, forKey: Key.onDeviceASR)
    }
}
