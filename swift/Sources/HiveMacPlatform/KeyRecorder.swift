import Foundation
import AppKit
import HiveMacCore

/// Listens to your key presses in any app while you walk, with timestamps. Needs Input Monitoring.
public final class KeyRecorder {
    private var monitor: Any?
    private var events: [KeyEvent] = []
    private let lock = NSLock()

    public init() {}
    public var isRecording: Bool { monitor != nil }

    public func start() {
        events = []
        monitor = NSEvent.addGlobalMonitorForEvents(matching: [.keyDown, .keyUp]) { [weak self] e in
            guard let self, !e.isARepeat, let name = KeyCodes.name(for: e.keyCode) else { return }
            self.lock.lock()
            self.events.append(KeyEvent(t: ProcessInfo.processInfo.systemUptime, key: name, down: e.type == .keyDown))
            self.lock.unlock()
        }
    }

    public func stop() -> [KeyEvent] {
        if let m = monitor { NSEvent.removeMonitor(m) }
        monitor = nil
        lock.lock(); defer { lock.unlock() }
        return events
    }
}
