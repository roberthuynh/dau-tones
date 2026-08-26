import XCTest

/// Turns the product's central claim into a build gate.
///
/// "Your voice never leaves this iPhone" is the whole positioning, and prose cannot enforce it.
/// These tests read the app's own source and fail if anything that could send audio — or any
/// data — off the device appears. Following the fleet's rule for the no-assist-behind-an-ad
/// invariant: enforce it in code, not in a document nobody re-reads.
final class InfraAuditTests: XCTestCase {
    /// `Sources/` in the repo, found by walking up from this file.
    private var sourceRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // Tests/
            .deletingLastPathComponent()   // ios/
            .appending(path: "Sources")
    }

    private func swiftFiles() throws -> [(url: URL, text: String)] {
        let enumerator = FileManager.default.enumerator(at: sourceRoot, includingPropertiesForKeys: nil)
        var files: [(URL, String)] = []
        while let url = enumerator?.nextObject() as? URL {
            guard url.pathExtension == "swift" else { continue }
            files.append((url, try String(contentsOf: url, encoding: .utf8)))
        }
        return files
    }

    /// Guards the guards. Every test below loops over the source files, so a walk that finds
    /// nothing would make all of them pass while checking nothing at all.
    func testTheAuditActuallyReadsSources() throws {
        let files = try swiftFiles()
        XCTAssertGreaterThan(files.count, 10, "the source walk found almost nothing — the audit is vacuous")
        XCTAssertTrue(
            files.contains { $0.url.lastPathComponent == "LiveToneAnalyzer.swift" },
            "the audio capture file must be in scope of the audit"
        )
        // And the scan detects what it is looking for when it is genuinely present.
        XCTAssertTrue(files.contains { $0.text.contains("AVAudioEngine") })
    }

    func testNoNetworkClientExists() throws {
        // Anything here would mean audio, or anything else, could leave the device.
        let banned = [
            "URLSession", "URLRequest", "NWConnection", "CFStream",
            "Network.framework", "WKWebView", "NSURLConnection",
        ]
        for file in try swiftFiles() {
            for symbol in banned {
                XCTAssertFalse(
                    file.text.contains(symbol),
                    "\(file.url.lastPathComponent) references \(symbol) — the app must make no network requests"
                )
            }
        }
    }

    /// Server-side recognition would upload the learner's voice. On-device is not a preference
    /// here; it is the only acceptable setting, and the degradation path exists for devices
    /// that cannot do it.
    func testSpeechRecognitionIsPinnedOnDevice() throws {
        for file in try swiftFiles() {
            XCTAssertFalse(
                file.text.contains("requiresOnDeviceRecognition = false"),
                "\(file.url.lastPathComponent) disables on-device recognition"
            )
        }
    }

    func testNoAnalyticsSDK() throws {
        let banned = ["TelemetryDeck", "FirebaseAnalytics", "Amplitude", "Mixpanel", "AppsFlyer", "Adjust"]
        for file in try swiftFiles() {
            for symbol in banned {
                XCTAssertFalse(file.text.contains(symbol), "\(file.url.lastPathComponent) references \(symbol)")
            }
        }
    }

    /// A missing privacy manifest is a submission blocker, and a manifest that starts
    /// declaring collected data means the claim above has quietly changed.
    func testPrivacyManifestDeclaresNoCollectionOrTracking() throws {
        let manifest = sourceRoot.deletingLastPathComponent()
            .appending(path: "Resources/PrivacyInfo.xcprivacy")
        let text = try String(contentsOf: manifest, encoding: .utf8)
        XCTAssertTrue(text.contains("<key>NSPrivacyTracking</key>"))
        XCTAssertTrue(
            text.contains("<key>NSPrivacyTracking</key>\n\t<false/>"),
            "tracking must be declared false"
        )
        XCTAssertTrue(
            text.contains("<key>NSPrivacyCollectedDataTypes</key>\n\t<array/>"),
            "collected data types must be empty"
        )
        XCTAssertTrue(text.contains("CA92.1"), "UserDefaults access needs its required reason")
    }

    /// The bundled reference audio is mostly synthesized, and the app says so. If the credits
    /// stop disclosing it, that is a claim regression.
    func testGeneratedAudioIsDisclosed() throws {
        let notes = sourceRoot.deletingLastPathComponent()
            .appending(path: "docs/appstore/review-notes.md")
        let text = try String(contentsOf: notes, encoding: .utf8)
        XCTAssertTrue(text.lowercased().contains("synthesized"), "generated audio must stay disclosed")
    }
}
