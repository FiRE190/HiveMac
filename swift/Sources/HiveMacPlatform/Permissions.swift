import Foundation
import CoreGraphics
import ApplicationServices
import AppKit

/// The two permissions the macro needs, read with the real macOS calls. The stop key needs
/// neither: it is a Carbon hot key, which works without Input Monitoring.
public struct PermissionStatus: Equatable {
    public var screenRecording: Bool
    public var accessibility: Bool
    public init(screenRecording: Bool, accessibility: Bool) { self.screenRecording = screenRecording; self.accessibility = accessibility }
    public var allGranted: Bool { screenRecording && accessibility }

    /// Plain reasons for what is missing, empty when everything is granted.
    public var problems: [String] {
        var out: [String] = []
        if !screenRecording { out.append("Screen Recording is off: HiveMac cannot read the game. Turn it on for HiveMac.") }
        if !accessibility { out.append("Accessibility is off: macOS silently drops every key press. Turn it on for HiveMac.") }
        return out
    }
}

public enum Permissions {
    public static func current() -> PermissionStatus {
        PermissionStatus(screenRecording: CGPreflightScreenCaptureAccess(), accessibility: AXIsProcessTrusted())
    }

    /// Triggers the system prompts for whatever is missing.
    public static func request() {
        if !CGPreflightScreenCaptureAccess() { _ = CGRequestScreenCaptureAccess() }
        if !AXIsProcessTrusted() {
            let key = kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String
            _ = AXIsProcessTrustedWithOptions([key: true] as CFDictionary)
        }
    }

    public enum Pane: String {
        case screenRecording = "Privacy_ScreenCapture"
        case accessibility = "Privacy_Accessibility"
    }

    public static func openSettings(_ pane: Pane) {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?\(pane.rawValue)") {
            NSWorkspace.shared.open(url)
        }
    }
}
