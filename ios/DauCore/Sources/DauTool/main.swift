import DauCore
import Foundation

// dau-tool — build-time CLI. Never shipped in the app.
// Subcommands land as the pipeline needs them: build-content, calibrate-match, tune-dipping.

let args = Array(CommandLine.arguments.dropFirst())
guard let command = args.first else {
    print("usage: dau-tool <build-content|calibrate-match|tune-dipping>")
    exit(2)
}

switch command {
case "build-content", "calibrate-match", "tune-dipping":
    FileHandle.standardError.write(Data("dau-tool \(command): not implemented yet\n".utf8))
    exit(3)
default:
    FileHandle.standardError.write(Data("dau-tool: unknown command '\(command)'\n".utf8))
    exit(2)
}
