import DauCore
import Foundation

enum LearnerPath: String, Codable, CaseIterable {
    case beginner
    case heritage

    var title: String { self == .beginner ? "Start with the essentials" : "I grew up around Vietnamese" }
}

struct ListeningObservation: Codable, Equatable {
    let correct: Bool
    let assisted: Bool
    let review: Bool
    let timestamp: Date
}

struct QuestSnapshot: Codable, Equatable {
    static let currentVersion = 1

    var version = currentVersion
    var learnerPath: LearnerPath = .beginner
    var cafeStep = 0
    var cafeCompletedAt: Date?
    var cafeCompletionCount = 0
    var reviewCount = 0
    var reviewDueAt: Date?
    var listeningChoices = 0
    var listeningObservations: [ListeningObservation] = []
    var speakingAttempts = 0
    var cafeSession: CafeQuestSession?

    init() {}

    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: CodingKeys.self)
        version = try box.decodeIfPresent(Int.self, forKey: .version) ?? Self.currentVersion
        learnerPath = try box.decodeIfPresent(LearnerPath.self, forKey: .learnerPath) ?? .beginner
        cafeStep = try box.decodeIfPresent(Int.self, forKey: .cafeStep) ?? 0
        cafeCompletedAt = try box.decodeIfPresent(Date.self, forKey: .cafeCompletedAt)
        cafeCompletionCount = try box.decodeIfPresent(Int.self, forKey: .cafeCompletionCount) ?? (cafeCompletedAt == nil ? 0 : 1)
        reviewCount = try box.decodeIfPresent(Int.self, forKey: .reviewCount) ?? 0
        reviewDueAt = try box.decodeIfPresent(Date.self, forKey: .reviewDueAt)
        listeningChoices = try box.decodeIfPresent(Int.self, forKey: .listeningChoices) ?? 0
        listeningObservations = try box.decodeIfPresent([ListeningObservation].self, forKey: .listeningObservations) ?? []
        speakingAttempts = try box.decodeIfPresent(Int.self, forKey: .speakingAttempts) ?? 0
        if let decoded = try box.decodeIfPresent(CafeQuestSession.self, forKey: .cafeSession),
           let data = try? JSONEncoder().encode(decoded) {
            // Restore validates the episode revision and invariants. A stale in-flight turn
            // is discarded without losing durable completion or review history.
            cafeSession = try? CafeQuestSession.restore(from: data)
        } else {
            cafeSession = nil
        }
        guard version <= Self.currentVersion else { throw CocoaError(.coderReadCorrupt) }
        cafeStep = min(max(0, cafeStep), CafeLessonStep.allCases.count)
    }
}

@Observable
final class QuestProgressStore {
    private(set) var snapshot = QuestSnapshot()
    private(set) var saveError: String?
    private let fileURL: URL

    init(directory: URL? = nil) {
        let base = directory ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        fileURL = base.appending(path: "vietquest-progress-v1.json")
        if LaunchArguments.resetQuestProgress { try? FileManager.default.removeItem(at: fileURL) }
        load()
    }

    var isStarted: Bool { snapshot.cafeStep > 0 }
    var hasActiveRun: Bool { snapshot.cafeStep > 0 && snapshot.cafeStep < CafeLessonStep.allCases.count }
    var isCompleted: Bool { snapshot.cafeCompletedAt != nil }
    var hasReviewDue: Bool { snapshot.reviewDueAt.map { $0 <= Date() } ?? false }

    func choosePath(_ path: LearnerPath) {
        snapshot.learnerPath = path
        save()
    }

    func saveStep(_ step: Int) {
        snapshot.cafeStep = min(max(0, step), CafeLessonStep.allCases.count)
        save()
    }

    func recordListeningChoice(correct: Bool, assisted: Bool, review: Bool) {
        snapshot.listeningChoices += 1
        snapshot.listeningObservations.append(.init(correct: correct, assisted: assisted, review: review, timestamp: Date()))
        if snapshot.listeningObservations.count > 5_000 {
            snapshot.listeningObservations.removeFirst(snapshot.listeningObservations.count - 5_000)
        }
        save()
    }

    func recordSpeakingAttempt() {
        snapshot.speakingAttempts += 1
        save()
    }

    func saveSession(_ session: CafeQuestSession) {
        snapshot.cafeSession = session
        save()
    }

    func completeCafe() {
        let now = Date()
        snapshot.cafeStep = CafeLessonStep.allCases.count
        snapshot.cafeCompletedAt = now
        snapshot.cafeCompletionCount += 1
        snapshot.reviewDueAt = Calendar.current.date(byAdding: .day, value: 1, to: now)
        save()
    }

    func completeReview() {
        snapshot.reviewCount += 1
        snapshot.reviewDueAt = Calendar.current.date(byAdding: .day, value: 2, to: Date())
        save()
    }

    func restartCafe() {
        snapshot.cafeStep = 0
        snapshot.cafeSession = nil
        save()
    }

    private func load() {
        guard let data = try? Data(contentsOf: fileURL) else { return }
        do {
            snapshot = try JSONDecoder().decode(QuestSnapshot.self, from: data)
        } catch {
            let stamp = ISO8601DateFormatter().string(from: Date())
            let parked = fileURL.deletingLastPathComponent().appending(path: "vietquest-progress-v1.corrupt-\(stamp).json")
            try? FileManager.default.moveItem(at: fileURL, to: parked)
        }
    }

    private func save() {
        do {
            let data = try JSONEncoder().encode(snapshot)
            try data.write(to: fileURL, options: .atomic)
            saveError = nil
        } catch {
            saveError = "Your progress could not be saved. Free up space on this iPhone and try again."
        }
    }
}
