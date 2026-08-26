import XCTest

/// App-target smoke. DauCore carries the real engine tests (`swift test` in DauCore/).
final class DauAppTests: XCTestCase {
    func testAppTargetBuildsAndLinks() {
        XCTAssertNotNil(Bundle.main.bundleIdentifier)
    }
}
