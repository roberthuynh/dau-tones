import SwiftUI

@main
struct DauApp: App {
    @State private var content = ContentStore()
    @State private var settings = DauSettings()
    @State private var progress = ProgressStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(content)
                .environment(settings)
                .environment(progress)
                .preferredColorScheme(.dark)
                .task { settings.probeOnDeviceRecognition() }
        }
    }
}
