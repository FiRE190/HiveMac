import Foundation

/// Where things are on screen, as fractions of the Roblox window, so a moved or resized
/// window still works and each spot only has to be recorded once.
public struct WindowBounds: Codable, Equatable, Sendable {
    public var left: Int, top: Int, width: Int, height: Int
    public init(left: Int, top: Int, width: Int, height: Int) {
        self.left = left; self.top = top; self.width = width; self.height = height
    }
}

public struct RelPoint: Codable, Equatable, Sendable {
    public var fx: Double, fy: Double
    public init(fx: Double, fy: Double) { self.fx = fx; self.fy = fy }

    public func absolute(in w: WindowBounds) -> (x: Int, y: Int) {
        (w.left + Int((fx * Double(w.width)).rounded()), w.top + Int((fy * Double(w.height)).rounded()))
    }

    public static func from(x: Int, y: Int, in w: WindowBounds) -> RelPoint {
        RelPoint(fx: Double(x - w.left) / Double(max(1, w.width)), fy: Double(y - w.top) / Double(max(1, w.height)))
    }
}

public struct RelRegion: Codable, Equatable, Sendable {
    public var fx: Double, fy: Double, fw: Double, fh: Double
    public init(fx: Double, fy: Double, fw: Double, fh: Double) { self.fx = fx; self.fy = fy; self.fw = fw; self.fh = fh }

    public func absolute(in w: WindowBounds) -> WindowBounds {
        WindowBounds(left: w.left + Int((fx * Double(w.width)).rounded()),
                     top: w.top + Int((fy * Double(w.height)).rounded()),
                     width: max(1, Int((fw * Double(w.width)).rounded())),
                     height: max(1, Int((fh * Double(w.height)).rounded())))
    }
}

public enum Layout {
    /// Starting guesses for the HUD spots from Natro's constants (client coordinates, 1x scale).
    public struct Defaults: Equatable {
        public var backpackPixel: RelPoint
        public var healthPixel: RelPoint
        public var hivePromptRegion: RelRegion
        public var hiveViewRegion: RelRegion
        public var hiveStripRegion: RelRegion
        public var mousePark: RelPoint
    }

    public static func natroDefaults(_ w: WindowBounds, offsetY: Int = 0) -> Defaults {
        let width = Double(max(1, w.width)), height = Double(max(1, w.height)), oy = Double(offsetY)
        return Defaults(
            backpackPixel: RelPoint(fx: (width / 2 + 62) / width, fy: (oy + 6) / height),
            healthPixel: RelPoint(fx: (width - 75) / width, fy: 36 / height),
            hivePromptRegion: RelRegion(fx: (width / 2 - 200) / width, fy: oy / height, fw: 400 / width, fh: 125 / height),
            hiveViewRegion: RelRegion(fx: 0, fy: 0.75, fw: 1, fh: 0.25),
            hiveStripRegion: RelRegion(fx: (width / 2 - 100) / width, fy: (height - 10) / height, fw: 200 / width, fh: 10 / height),
            mousePark: RelPoint(fx: 350 / width, fy: (oy + 100) / height))
    }

    /// Window rect to the rect the macro reads: windowed removes the title bar.
    public static func contentRect(_ window: WindowBounds, mode: String, titleBar: Int) -> WindowBounds {
        if mode == "fullscreen" { return window }
        let t = max(0, min(titleBar, window.height / 4))
        return WindowBounds(left: window.left, top: window.top + t, width: window.width, height: window.height - t)
    }

    public static func clamp(_ r: WindowBounds, to w: WindowBounds) -> WindowBounds {
        let left = max(w.left, r.left), top = max(w.top, r.top)
        let right = min(w.left + w.width, r.left + r.width), bottom = min(w.top + w.height, r.top + r.height)
        return WindowBounds(left: left, top: top, width: max(1, right - left), height: max(1, bottom - top))
    }

    public struct WindowInfo: Equatable {
        public var owner: String
        public var layer: Int
        public var bounds: WindowBounds
        public init(owner: String, layer: Int, bounds: WindowBounds) { self.owner = owner; self.layer = layer; self.bounds = bounds }
    }

    /// Largest normal (layer 0) window whose owner name contains the hint.
    public static func pickWindow(_ infos: [WindowInfo], ownerHint: String = "roblox") -> WindowBounds? {
        var best: WindowBounds?, bestArea = 0
        for w in infos where w.owner.lowercased().contains(ownerHint.lowercased()) && w.layer == 0 {
            guard w.bounds.width >= 100, w.bounds.height >= 100 else { continue }
            let area = w.bounds.width * w.bounds.height
            if area > bestArea { bestArea = area; best = w.bounds }
        }
        return best
    }
}
