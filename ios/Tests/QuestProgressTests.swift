import DauCore
import XCTest
@testable import Dau

final class QuestProgressTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory
            .appending(path: "QuestProgressTests-\(UUID().uuidString)", directoryHint: .isDirectory)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
        directory = nil
    }

    func testStartingQuestDoesNotReplaceExistingDauProgress() {
        let fixedDate = Date(timeIntervalSince1970: 1_788_768_000)
        let dau = ProgressStore(directory: directory, clock: { fixedDate })
        dau.completeToday()
        let before = dau.progress

        _ = QuestProgressStore(directory: directory)

        XCTAssertEqual(ProgressStore(directory: directory, clock: { fixedDate }).progress, before)
        XCTAssertTrue(FileManager.default.fileExists(atPath: directory.appending(path: "dau-progress-v1.json").path))
    }

    func testReloadRestoresCurrentLessonAndCoreSession() {
        let store = QuestProgressStore(directory: directory)
        var session = CafeQuestSession(availableItems: [.water])
        session.submit(.start)
        session.submit(.request(.coffee))
        store.saveStep(CafeLessonStep.changedOrder.rawValue)
        store.saveSession(session)

        let restored = QuestProgressStore(directory: directory)
        XCTAssertEqual(restored.snapshot.cafeStep, CafeLessonStep.changedOrder.rawValue)
        XCTAssertEqual(restored.snapshot.cafeSession, session)
        XCTAssertEqual(restored.snapshot.cafeSession?.phase, .awaitAlternative)
    }

    func testCompletedHistorySurvivesReplayRestartAndReload() {
        let store = QuestProgressStore(directory: directory)
        store.completeCafe()
        let completedAt = store.snapshot.cafeCompletedAt
        store.restartCafe()

        let restored = QuestProgressStore(directory: directory)
        XCTAssertEqual(restored.snapshot.cafeCompletionCount, 1)
        XCTAssertEqual(restored.snapshot.cafeCompletedAt, completedAt)
        XCTAssertEqual(restored.snapshot.cafeStep, 0)
        XCTAssertNil(restored.snapshot.cafeSession)
    }

    func testCompletingReviewPreservesCompletionAndReschedulesDueDate() {
        let store = QuestProgressStore(directory: directory)
        store.completeCafe()
        let completion = store.snapshot.cafeCompletedAt
        let firstDue = try! XCTUnwrap(store.snapshot.reviewDueAt)
        let beforeReview = Date()

        store.completeReview()

        XCTAssertEqual(store.snapshot.cafeCompletedAt, completion)
        XCTAssertEqual(store.snapshot.cafeCompletionCount, 1)
        XCTAssertEqual(store.snapshot.reviewCount, 1)
        let nextDue = try! XCTUnwrap(store.snapshot.reviewDueAt)
        XCTAssertGreaterThan(nextDue, firstDue)
        XCTAssertEqual(nextDue.timeIntervalSince(beforeReview), 2 * 86_400, accuracy: 2)
        XCTAssertEqual(QuestProgressStore(directory: directory).snapshot.reviewDueAt, nextDue)
    }

    func testCorruptProgressIsParkedAndNotTrusted() throws {
        let save = directory.appending(path: "vietquest-progress-v1.json")
        try Data("not-json".utf8).write(to: save)

        let restored = QuestProgressStore(directory: directory)

        XCTAssertEqual(restored.snapshot, QuestSnapshot())
        XCTAssertFalse(FileManager.default.fileExists(atPath: save.path))
        XCTAssertTrue(try FileManager.default.contentsOfDirectory(atPath: directory.path).contains {
            $0.hasPrefix("vietquest-progress-v1.corrupt-")
        })
    }

    func testUnknownSnapshotVersionIsParkedAndNotTrusted() throws {
        let save = directory.appending(path: "vietquest-progress-v1.json")
        let data = try JSONSerialization.data(withJSONObject: ["version": QuestSnapshot.currentVersion + 1, "cafeStep": 7])
        try data.write(to: save)

        let restored = QuestProgressStore(directory: directory)

        XCTAssertEqual(restored.snapshot, QuestSnapshot())
        XCTAssertFalse(FileManager.default.fileExists(atPath: save.path))
    }

    func testSaveFailureIsVisibleInsteadOfPretendingProgressWasSaved() throws {
        let notADirectory = directory.appending(path: "blocked")
        try Data("existing file".utf8).write(to: notADirectory)
        let store = QuestProgressStore(directory: notADirectory)
        store.choosePath(.heritage)
        XCTAssertNotNil(store.saveError)
        XCTAssertEqual(try Data(contentsOf: notADirectory), Data("existing file".utf8))
    }

    func testIncompatibleCoreSessionIsNotTrusted() throws {
        var sessionObject = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(CafeQuestSession())) as? [String: Any]
        )
        sessionObject["episodeRevision"] = CafeEpisode.content.revision + 1
        let save = directory.appending(path: "vietquest-progress-v1.json")
        let snapshot = try JSONSerialization.data(withJSONObject: [
            "version": QuestSnapshot.currentVersion,
            "cafeStep": CafeLessonStep.changedOrder.rawValue,
            "cafeSession": sessionObject,
        ])
        try snapshot.write(to: save)

        let restored = QuestProgressStore(directory: directory)

        XCTAssertNil(restored.snapshot.cafeSession)
        XCTAssertEqual(restored.snapshot.cafeStep, CafeLessonStep.changedOrder.rawValue)
    }
}
