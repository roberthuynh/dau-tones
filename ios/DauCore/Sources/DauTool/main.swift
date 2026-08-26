import DauCore
import Foundation

// dau-tool — build-time CLI. Never shipped inside the app.
//
//   swift run dau-tool build-content   <repo-root> <output-dir>
//   swift run dau-tool calibrate-match <fixtures.json>
//
// build-content narrows api/data/inventory.json into the app's bundled resource and reports
// which reference recordings exist, so a missing pair is a visible build fact rather than a
// runtime surprise.

let arguments = Array(CommandLine.arguments.dropFirst())

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data("dau-tool: \(message)\n".utf8))
    exit(1)
}

guard let command = arguments.first else {
    print("usage: dau-tool <build-content|build-references|calibrate-match> [args]")
    exit(2)
}

switch command {
case "build-content":
    guard arguments.count >= 3 else { fail("build-content <repo-root> <output-dir>") }
    try BuildContent.run(repoRoot: arguments[1], outputDirectory: arguments[2])
case "build-references":
    guard arguments.count >= 3 else { fail("build-references <repo-root> <output-dir> [fixtures.json]") }
    try BuildReferences.run(
        repoRoot: arguments[1], outputDirectory: arguments[2],
        fixtures: arguments.count > 3 ? arguments[3] : nil
    )
case "calibrate-match":
    guard arguments.count >= 2 else { fail("calibrate-match <fixtures.json>") }
    try CalibrateMatch.run(fixtures: arguments[1])
default:
    fail("unknown command '\(command)'")
}
