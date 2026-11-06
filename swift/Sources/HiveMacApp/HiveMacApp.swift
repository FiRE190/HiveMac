import SwiftUI
import AppKit

@main
struct HiveMacApp: App {
    @StateObject private var model = AppModel()
    @StateObject private var updates = UpdateChecker()

    init() {
        if ProcessInfo.processInfo.environment["HIVEMAC_APPEARANCE"] == "light" { NSApp?.appearance = NSAppearance(named: .aqua) }
    }

    var body: some Scene {
        WindowGroup("HiveMac") {
            MainView()
                .environmentObject(model)
                .environmentObject(updates)
                .task { if ProcessInfo.processInfo.environment["HIVEMAC_DEMO"] == nil { updates.checkOnLaunch() } }
                .frame(minWidth: 620, idealWidth: 640, minHeight: 700, idealHeight: 760)
                .background(WindowChrome())
        }
        .defaultSize(width: 640, height: 780)
        .windowResizability(.contentMinSize)
        .commands { CommandGroup(replacing: .newItem) {} }
    }
}

/// Lets the content run up under a transparent title bar, so the header is the top of the window.
struct WindowChrome: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let v = NSView()
        DispatchQueue.main.async {
            guard let w = v.window else { return }
            w.titlebarAppearsTransparent = true
            w.titleVisibility = .hidden
            w.styleMask.insert(.fullSizeContentView)
            w.isMovableByWindowBackground = true
            w.backgroundColor = NSColor(name: nil) { a in a.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
                ? NSColor(srgbRed: 0x1A / 255, green: 0x18 / 255, blue: 0x15 / 255, alpha: 1)
                : NSColor(srgbRed: 0xF3 / 255, green: 0xF1 / 255, blue: 0xEC / 255, alpha: 1) }
        }
        return v
    }
    func updateNSView(_ nsView: NSView, context: Context) {}
}
