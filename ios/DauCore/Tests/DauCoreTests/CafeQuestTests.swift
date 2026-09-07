import XCTest
@testable import DauCore

final class CafeQuestTests: XCTestCase {
    func testCoreTranscriptsAreFrozen() {
        XCTAssertEqual(CafeEpisode.content.lines.map(\.id), ["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08"])
        XCTAssertEqual(CafeEpisode.content.lines.map(\.vietnamese), [
            "Con muốn nước hay cà phê?",
            "Dạ, cho con cà phê. Cảm ơn cô.",
            "Dạ, cho con nước. Cảm ơn cô.",
            "Cà phê hết rồi con. Con uống nước được không?",
            "Cô nói lại giùm con.",
            "Một ly nước, đúng không con?",
            "Một ly cà phê, đúng không con?",
            "Dạ, đúng rồi.",
        ])
        XCTAssertEqual(CafeEpisode.content.lines.compactMap(\.audioKey), ["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08"])
    }

    func testChangedExchangeRepeatsThenChoosesWaterAndConfirms() {
        var session = CafeQuestSession(availableItems: [.water])
        XCTAssertEqual(session.submit(.start).lineIDToPlay, "C01")
        XCTAssertEqual(session.submit(.request(.coffee)).lineIDToPlay, "C04")

        let repeatResult = session.submit(.repeatRequest(vietnamese: true))
        XCTAssertEqual(repeatResult.lineIDToPlay, "C04")
        XCTAssertEqual(session.phase, .awaitAlternative)
        XCTAssertEqual(session.requestedItem, .coffee)

        XCTAssertEqual(session.submit(.acceptOfferedWater).lineIDToPlay, "C06")
        XCTAssertEqual(session.submit(.confirm).phase, .completed)
        XCTAssertEqual(session.confirmedItem, .water)
        XCTAssertEqual(session.attempts[2].evidence, .independent)
    }

    func testUnavailableCoffeeRetryCannotServeCoffee() {
        var session = CafeQuestSession(availableItems: [.water])
        session.submit(.start)
        session.submit(.request(.coffee))
        let retry = session.submit(.request(.coffee))
        XCTAssertFalse(retry.accepted!)
        XCTAssertEqual(retry.lineIDToPlay, "C04")
        XCTAssertEqual(session.phase, .awaitAlternative)
        XCTAssertNil(session.confirmedItem)
    }

    func testAnswerRevealCreatesRehearsalAndIncorrectAnswerCanRetry() {
        var session = CafeQuestSession()
        session.submit(.start)
        XCTAssertEqual(session.revealAnswer().lineIDToPlay, "C02")
        let wrong = session.submit(.confirm)
        XCTAssertEqual(wrong.accepted, false)
        XCTAssertEqual(session.phase, .awaitRequest)
        XCTAssertEqual(session.attempts.last?.evidence, .rehearsal)
        XCTAssertEqual(session.submit(.request(.water)).accepted, true)
    }

    func testAssistanceAndUnassessedSpeechRemainDistinct() {
        var assisted = CafeQuestSession()
        assisted.submit(.start)
        assisted.useAssistance(.phraseHint)
        assisted.submit(.request(.coffee))
        XCTAssertEqual(assisted.attempts.last?.evidence, .assisted)

        var unassessed = CafeQuestSession()
        unassessed.submit(.start)
        unassessed.submit(.request(.coffee), modality: .spokenRecording)
        XCTAssertEqual(unassessed.attempts.last?.accepted, nil)
        XCTAssertEqual(unassessed.attempts.last?.evidence, .unassessed)
        XCTAssertEqual(unassessed.phase, .awaitRequest)

        unassessed.useAssistance(.intendedMeaningConfirmation)
        unassessed.submit(.request(.coffee), modality: .spokenRecording)
        XCTAssertEqual(unassessed.phase, .awaitConfirmation)
        XCTAssertEqual(unassessed.attempts.last?.evidence, .assisted)
    }

    func testSessionPersistenceRoundTrip() throws {
        var original = CafeQuestSession(availableItems: [.water])
        original.submit(.start)
        original.useAssistance(.transcript)
        original.submit(.request(.coffee))
        original.submit(.repeatRequest(vietnamese: false))

        let restored = try CafeQuestSession.restore(from: JSONEncoder().encode(original))
        XCTAssertEqual(restored, original)
        XCTAssertEqual(restored.phase, .awaitAlternative)
        XCTAssertEqual(restored.lastServerLineID, "C04")
    }

    func testTerminalStatesRejectFurtherRepeatWithoutPlayingAudio() {
        var completed = CafeQuestSession()
        completed.submit(.start)
        completed.submit(.request(.water))
        completed.submit(.confirm)

        let afterCompletion = completed.submit(.repeatRequest(vietnamese: true))
        XCTAssertEqual(afterCompletion.accepted, false)
        XCTAssertNil(afterCompletion.lineIDToPlay)
        XCTAssertEqual(completed.confirmedItem, .water)

        var declined = CafeQuestSession(availableItems: [.water])
        declined.submit(.start)
        declined.submit(.request(.coffee))
        declined.submit(.declineWater)
        let afterDecline = declined.submit(.repeatRequest(vietnamese: false))
        XCTAssertEqual(afterDecline.accepted, false)
        XCTAssertNil(afterDecline.lineIDToPlay)
    }

    func testValidatedInitializerRejectsInventoryWithoutOfferedWater() {
        XCTAssertThrowsError(try CafeQuestSession(validatedAvailableItems: [.coffee])) { error in
            XCTAssertEqual(error as? CafeQuestSessionError, .waterMustBeAvailable)
        }
    }

    func testRestoreRejectsDifferentContentRevision() throws {
        let data = try JSONEncoder().encode(CafeQuestSession())
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        object["episodeRevision"] = 99
        let incompatible = try JSONSerialization.data(withJSONObject: object)

        XCTAssertThrowsError(try CafeQuestSession.restore(from: incompatible)) { error in
            XCTAssertEqual(
                error as? CafeQuestSessionError,
                .incompatibleEpisode(expectedID: "cafe-01", expectedRevision: 1, actualID: "cafe-01", actualRevision: 99)
            )
        }
    }

    func testRestoreRejectsInventoryThatCannotFulfillChangedOrder() throws {
        let data = try JSONEncoder().encode(CafeQuestSession())
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        object["availableItems"] = [CafeDrink.coffee.rawValue]
        let invalid = try JSONSerialization.data(withJSONObject: object)

        XCTAssertThrowsError(try CafeQuestSession.restore(from: invalid)) { error in
            XCTAssertEqual(error as? CafeQuestSessionError, .invalidPersistedState)
        }
    }
}
