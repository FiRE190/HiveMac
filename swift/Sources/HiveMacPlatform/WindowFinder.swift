import Foundation
import CoreGraphics
import AppKit
import HiveMacCore

/// Finds the Roblox window with Quartz. Unlike the AppleScript route this needs no Accessibility
/// permission, works for a full screen window, and costs about a millisecond.
public enum WindowFinder {
    public static func infos() -> [Layout.WindowInfo] {
        let opts: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
        guard let list = CGWindowListCopyWindowInfo(opts, kCGNullWindowID) as? [[String: Any]] else { return [] }
        return list.compactMap { d in
            guard let owner = d[kCGWindowOwnerName as String] as? String,
                  let layer = (d[kCGWindowLayer as String] as? NSNumber)?.intValue,
                  let b = d[kCGWindowBounds as String] as? [String: Any] else { return nil }
            func n(_ k: String) -> Int { (b[k] as? NSNumber)?.intValue ?? 0 }
            return Layout.WindowInfo(owner: owner, layer: layer,
                                     bounds: WindowBounds(left: n("X"), top: n("Y"), width: n("Width"), height: n("Height")))
        }
    }

    public static func robloxWindow() -> WindowBounds? { Layout.pickWindow(infos()) }

    /// The rect the macro reads: the window, minus the title bar when windowed.
    public static func contentBounds(mode: String, titleBar: Int) -> WindowBounds? {
        robloxWindow().map { Layout.contentRect($0, mode: mode, titleBar: titleBar) }
    }

    /// Brings Roblox to the front (works for a full screen Space too).
    @discardableResult
    public static func focusRoblox() -> Bool {
        guard let app = NSWorkspace.shared.runningApplications.first(where: { ($0.localizedName ?? "").lowercased().contains("roblox") }) else { return false }
        return app.activate()
    }
}
