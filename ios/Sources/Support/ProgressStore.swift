import DauCore
import Foundation

/// One take, as recorded in history.
struct TakeRecord: Codable, Equatable, Sendable {
    let wordID: String
    let accent: Accent
    let tone: ToneMark
    /// True only when the target's acceptance rule passed and the shape agreed.
    let passed: Bool
    /// Nil whenever the signal did not support a number.
    let shapeMatchPercent: Int?
    let dayKey: String
    let timestamp: Date
}

/// Everything the app remembers. One versioned Codable blob, written atomically.
///
/// Shape follows `maple-hollow/templates/swift/ProgressStore.swift`: `decodeIfPresent`
/// everywhere so a new field cannot wipe an existing save, and a blob that will not decode is
/// parked rather than deleted.
struct DauProgress: Codable, Equatable {
    static let currentVersion = 1

    var version: Int = DauProgress.currentVersion
    var takes: [TakeRecord] = []
    var currentStreak: Int = 0
    var longestStreak: Int = 0
    var lastCompletedDayKey: String?
    var completedDayKeys: [String] = []

    /// Roughly four and a half years of daily practice. Older takes fold away; the rollups
    /// the screens actually read are derived, never stored.
    static let maximumTakes = 5_000

    init() {}

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        version = try container.decodeIfPresent(Int.self, forKey: .version) ?? Self.currentVersion
        takes = try container.decodeIfPresent([TakeRecord].self, forKey: .takes) ?? []
        currentStreak = try container.decodeIfPresent(Int.self, forKey: .currentStreak) ?? 0
        longestStreak = try container.decodeIfPresent(Int.self, forKey: .longestStreak) ?? 0
        lastCompletedDayKey = try container.decodeIfPresent(String.self, forKey: .lastCompletedDayKey)
        completedDayKeys = try container.decodeIfPresent([String].self, forKey: .completedDayKeys) ?? []
    }
}

@Observable
final class ProgressStore {
    private(set) var progress = DauProgress()
    private let fileURL: URL
    private let clock: () -> Date

    /// How many recent takes of a word define its mastery. Deliberately small and stated in
    /// the UI as "8 of your last 10" — an observed tally, not a model's opinion.
    static let masteryWindow = 10

    init(directory: URL? = nil, clock: @escaping () -> Date = Date.init) {
        let base = directory ?? FileManager.default.urls(
            for: .applicationSupportDirectory, in: .userDomainMask
        )[0]
        try? FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        self.fileURL = base.appending(path: "dau-progress-v1.json")
        self.clock = LaunchArguments.fixedClock.flatMap { iso in
            ISO8601DateFormatter().date(from: iso).map { fixed in { fixed } }
        } ?? clock
        if LaunchArguments.resetProgress {
            try? FileManager.default.removeItem(at: fileURL)
        }
        load()
    }

    // MARK: - Recording

    func record(verdict: ToneVerdict, wordID: String) {
        let now = clock()
        let record = TakeRecord(
            wordID: wordID,
            accent: verdict.accent,
            tone: verdict.target,
            passed: verdict.isMatch,
            shapeMatchPercent: verdict.shapeMatch?.percent,
            dayKey: Self.dayKey(for: now),
            timestamp: now
        )
        progress.takes.append(record)
        if progress.takes.count > DauProgress.maximumTakes {
            progress.takes.removeFirst(progress.takes.count - DauProgress.maximumTakes)
        }
        save()
    }

    /// Called when the day's three words are done.
    func completeToday() {
        let today = Self.dayKey(for: clock())
        guard progress.lastCompletedDayKey != today else { return }
        let yesterday = Self.dayKey(for: clock().addingTimeInterval(-86_400))
        let dayBefore = Self.dayKey(for: clock().addingTimeInterval(-2 * 86_400))
        // Forgiving on purpose: one missed day does not reset the streak. There are no
        // hearts, no energy, and nothing to buy back — the habit is the pull.
        if progress.lastCompletedDayKey == yesterday || progress.lastCompletedDayKey == dayBefore {
            progress.currentStreak += 1
        } else {
            progress.currentStreak = 1
        }
        progress.longestStreak = max(progress.longestStreak, progress.currentStreak)
        progress.lastCompletedDayKey = today
        progress.completedDayKeys.append(today)
        save()
    }

    // MARK: - Derived

    func takes(forWord wordID: String) -> [TakeRecord] {
        progress.takes.filter { $0.wordID == wordID }
    }

    /// Mastery as an observed tally over the last N takes — "8 of your last 10", never a
    /// model's confidence. Nil when there is nothing to report yet.
    func mastery(forWord wordID: String) -> (passed: Int, total: Int)? {
        let recent = takes(forWord: wordID).suffix(Self.masteryWindow)
        guard !recent.isEmpty else { return nil }
        return (recent.filter(\.passed).count, recent.count)
    }

    func mastery(forTone tone: ToneMark) -> (passed: Int, total: Int)? {
        let recent = progress.takes.filter { $0.tone == tone }.suffix(Self.masteryWindow * 2)
        guard !recent.isEmpty else { return nil }
        return (recent.filter(\.passed).count, recent.count)
    }

    var takesToday: [TakeRecord] {
        let today = Self.dayKey(for: clock())
        return progress.takes.filter { $0.dayKey == today }
    }

    var didCompleteToday: Bool {
        progress.lastCompletedDayKey == Self.dayKey(for: clock())
    }

    /// Weakest tones first — what tomorrow's set should lean on.
    func weakestTones() -> [ToneMark] {
        ToneMark.allCases
            .map { tone -> (ToneMark, Double) in
                guard let mastery = mastery(forTone: tone), mastery.total > 0 else {
                    return (tone, -1)  // never practised sorts to the front
                }
                return (tone, Double(mastery.passed) / Double(mastery.total))
            }
            .sorted { $0.1 < $1.1 }
            .map(\.0)
    }

    static func dayKey(for date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.calendar = Calendar.current
        formatter.timeZone = TimeZone.current
        return formatter.string(from: date)
    }

    var now: Date { clock() }

    // MARK: - Persistence

    private func load() {
        guard let data = try? Data(contentsOf: fileURL) else { return }
        do {
            progress = try JSONDecoder().decode(DauProgress.self, from: data)
        } catch {
            // Park, never wipe. A save that cannot be read is still the only copy of
            // someone's history, and a future build may be able to recover it.
            let stamp = ISO8601DateFormatter().string(from: Date())
            let parked = fileURL.deletingLastPathComponent()
                .appending(path: "dau-progress-v1.corrupt-\(stamp).json")
            try? FileManager.default.moveItem(at: fileURL, to: parked)
            progress = DauProgress()
        }
    }

    private func save() {
        guard let data = try? JSONEncoder().encode(progress) else { return }
        try? data.write(to: fileURL, options: .atomic)
    }
}
