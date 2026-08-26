import XCTest

/// Screenshot + flow coverage for the v1 screens.
///
/// Every capture is guarded by a behavioural assertion first, following nghe's pattern: an
/// attachment should only ever exist when the screen it claims to show is actually up.
/// Otherwise a green run quietly produces a folder of blank frames.
final class DauScreenshotUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func launch(_ arguments: [String]) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = arguments + ["-resetProgress"]
        app.launch()
        return app
    }

    private func capture(_ app: XCUIApplication, _ name: String) {
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = name
        shot.lifetime = .keepAlways
        add(shot)
    }

    func testFirstRun() {
        let app = launch([])
        XCTAssertTrue(app.buttons["startButton"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["accent-north"].exists)
        XCTAssertTrue(app.buttons["accent-south"].exists)
        capture(app, "01-first-run")
    }

    func testTodayAndWordsAndYou() {
        let app = launch(["-skipOnboarding"])
        XCTAssertTrue(app.buttons["continueButton"].waitForExistence(timeout: 10))
        capture(app, "02-today")

        app.tabBars.buttons["Words"].tap()
        XCTAssertTrue(app.otherElements["maGrid"].waitForExistence(timeout: 5))
        capture(app, "07-words")

        app.tabBars.buttons["You"].tap()
        XCTAssertTrue(app.staticTexts["Your tones"].waitForExistence(timeout: 5))
        capture(app, "06-you")
    }

    /// The core loop, driven by a bundled reference instead of a microphone.
    ///
    /// Feeding má's recording while the target is `ma` should produce the product's headline
    /// moment: the learner is told which word they actually said. That claim is only made
    /// where the produced family resolves to exactly one tone, so this exercises the honesty
    /// gate rather than just a happy path.
    func testPracticeProducesAVerdict() {
        let app = launch(["-skipOnboarding", "-uiTestTakeFixture", "north-ma-mother"])
        XCTAssertTrue(app.buttons["continueButton"].waitForExistence(timeout: 10))
        app.buttons["continueButton"].tap()

        XCTAssertTrue(app.otherElements["practiceWord"].waitForExistence(timeout: 5))
        capture(app, "03-practice")

        let record = app.buttons["recordButton"]
        XCTAssertTrue(record.waitForExistence(timeout: 5))
        // The thumb-zone target the design asks for.
        XCTAssertGreaterThanOrEqual(record.frame.height, 88)
        XCTAssertGreaterThan(
            record.frame.midY, app.frame.height * 0.6,
            "the record button must sit in the thumb zone"
        )
        record.tap()

        // The identifier lands on the header's Text elements, not a container.
        let verdict = app.staticTexts.matching(identifier: "verdictHeader").firstMatch
        XCTAssertTrue(
            verdict.waitForExistence(timeout: 10),
            "a take must always end in a verdict, even an abstention"
        )
        capture(app, "04-verdict")
        XCTAssertTrue(app.buttons["primaryAction"].exists)

        // Feeding má's recording against a `ma` target should name the word that was
        // actually said. Level resolves uniquely in both accents, so this claim is as solid
        // as the verdict itself — and it is the product's headline moment.
        XCTAssertTrue(
            app.staticTexts["You said má — mother"].exists,
            "the produced word should be named when its family resolves uniquely"
        )
        // Grading provenance is stated on every verdict.
        XCTAssertTrue(
            app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "on this iPhone")).firstMatch.exists
        )
        // A usable take must carry the shape-match number.
        XCTAssertTrue(app.staticTexts["shapeMatch"].exists, "a readable take should show its shape match")
    }
}
