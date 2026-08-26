import XCTest

final class DauSmokeUITests: XCTestCase {
    /// Launches past onboarding and asserts the tab shell is up. Every screenshot test in
    /// this target guards its capture on a behavioral assertion the same way — an attachment
    /// should only exist when its named screen is actually on screen.
    func testLaunchesIntoTabShell() {
        let app = XCUIApplication()
        app.launchArguments = ["-skipOnboarding", "-resetProgress"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Practice"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.tabBars.buttons["Words"].exists)
        XCTAssertTrue(app.tabBars.buttons["You"].exists)
    }
}
