// swift-tools-version: 6.0
import PackageDescription

// DauCore — the pure judging engine for Dấu.
//
// Zero external dependencies, and no AVFoundation / SwiftUI / Speech imports anywhere in
// Sources/DauCore. macOS is a supported platform purely so the golden tests run headless
// (no simulator, no signing) in a plain `swift test`.
let package = Package(
    name: "DauCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "DauCore", targets: ["DauCore"]),
        .executable(name: "dau-tool", targets: ["DauTool"]),
    ],
    targets: [
        .target(name: "DauCore"),
        .executableTarget(name: "DauTool", dependencies: ["DauCore"]),
        .testTarget(
            name: "DauCoreTests",
            dependencies: ["DauCore"],
            resources: [.copy("Fixtures")]
        ),
    ]
)
