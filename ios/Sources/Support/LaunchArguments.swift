import Foundation

/// Launch-argument test hooks for Dấu.
///
/// UITests pass these to `XCUIApplication.launchArguments`; the `@main` App reads them at
/// startup and forwards to `ProgressStore.applyLaunchArguments(_:)`. Keep them working
/// from day 1 — the smoke + marketing UITests drive the app through them.
///
/// General hooks:  `-resetProgress`   `-skipOnboarding`   `-seedContent`
/// Dấu hooks:     `-uiTestTakeFixture <id>`   `-uiTestClock <iso8601>`
///
/// `-uiTestTakeFixture` is the important one: it feeds a bundled reference wav through the
/// identical analyzer instead of the microphone, which makes the whole verdict path
/// deterministically testable in the simulator and unblocks screens 03/04/05 before live
/// capture exists.
enum LaunchArguments {
    private static let args = ProcessInfo.processInfo.arguments

    static func has(_ flag: String) -> Bool { args.contains(flag) }

    /// Value following a flag, e.g. `value(after: "-seedContent")` → "deck-a".
    static func value(after flag: String) -> String? {
        guard let i = args.firstIndex(of: flag), i + 1 < args.count else { return nil }
        return args[i + 1]
    }

    static var resetProgress: Bool { has("-resetProgress") }
    static var resetQuestProgress: Bool { has("-resetQuestProgress") || resetProgress }
    static var skipOnboarding: Bool { has("-skipOnboarding") }
    /// Seed deterministic sample content for screenshots + UITests.
    static var seedContent: Bool { has("-seedContent") }

    /// Bundled take to analyze instead of opening the microphone, e.g. "north-ma-mother".
    static var takeFixture: String? { value(after: "-uiTestTakeFixture") }
    /// Fixed ISO-8601 instant for the injected clock, so streaks and "Today" are stable.
    static var fixedClock: String? { value(after: "-uiTestClock") }
}
