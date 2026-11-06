import Foundation

/// What the sensors read pixels from. The real one captures small screen regions.
public protocol ScreenReading: AnyObject {
    /// One pixel at absolute screen coordinates (points), nil if the screen cannot be read.
    func pixel(x: Int, y: Int) -> (r: Int, g: Int, b: Int)?
    /// A small region at absolute screen coordinates (points), nil if the screen cannot be read.
    func grab(_ region: WindowBounds) -> RGBImage?
}

/// The calibrated HUD spots, read from the `hud` section of the settings.
public struct HudConfig {
    public var backpackPixel: RelPoint?
    public var healthPixel: RelPoint?
    public var hivePromptRegion: RelRegion?
    public var hiveViewRegion: RelRegion?
    public var hiveStripRegion: RelRegion?
    public var deathRegion: RelRegion?
    public var hiveStripEnabled = false
    public var hiveStripMinPixels = 40
    public var filterSize = 6
    public var tolerance = 12
    public var hivePromptTemplate: RGBImage?
    public var hiveViewTemplate: RGBImage?
    public var cannonPromptTemplate: RGBImage?
    public var deathTemplate: RGBImage?

    public init() {}

    static func point(_ any: Any?) -> RelPoint? {
        guard let d = any as? [String: Any], let fx = (d["fx"] as? NSNumber)?.doubleValue,
              let fy = (d["fy"] as? NSNumber)?.doubleValue else { return nil }
        return RelPoint(fx: fx, fy: fy)
    }

    static func region(_ any: Any?) -> RelRegion? {
        guard let d = any as? [String: Any], let fx = (d["fx"] as? NSNumber)?.doubleValue,
              let fy = (d["fy"] as? NSNumber)?.doubleValue, let fw = (d["fw"] as? NSNumber)?.doubleValue,
              let fh = (d["fh"] as? NSNumber)?.doubleValue else { return nil }
        return RelRegion(fx: fx, fy: fy, fw: fw, fh: fh)
    }

    /// `loadTemplate` turns a file name in the templates folder into an image (nil if absent).
    public init(store: ConfigStore, loadTemplate: (String) -> RGBImage?) {
        backpackPixel = Self.point(store.get("hud.backpack_pixel"))
        healthPixel = Self.point(store.get("hud.health_pixel"))
        hivePromptRegion = Self.region(store.get("hud.hive_prompt_region"))
        hiveViewRegion = Self.region(store.get("hud.hive_view_region"))
        hiveStripRegion = Self.region(store.get("hud.hive_strip_region"))
        deathRegion = Self.region(store.get("hud.death_region"))
        hiveStripEnabled = store.bool("hud.hive_strip_enabled")
        hiveStripMinPixels = store.int("hud.hive_strip_min_pixels", 40)
        filterSize = store.int("hud.backpack_filter_size", 6)
        tolerance = store.int("hud.template_tolerance", 12)
        func tpl(_ key: String) -> RGBImage? {
            let name = store.string(key)
            return name.isEmpty ? nil : loadTemplate(name)
        }
        hivePromptTemplate = tpl("hud.hive_prompt_template")
        hiveViewTemplate = tpl("hud.hive_view_template")
        cannonPromptTemplate = tpl("hud.cannon_prompt_template")
        deathTemplate = tpl("hud.death_template")
    }
}

/// Binds the calibrated layout to the screen and the pure decoders in `Hud`. The macro loop
/// only talks to the `Sensors` protocol, so tests use a fake world and never touch the screen.
public final class ScreenSensors: Sensors {
    private let screen: ScreenReading
    private let window: () -> WindowBounds?
    public var cfg: HudConfig
    private var filter: BackpackFilter
    public private(set) var lastBackpackRGB: (r: Int, g: Int, b: Int)?

    public init(screen: ScreenReading, window: @escaping () -> WindowBounds?, config: HudConfig) {
        self.screen = screen; self.window = window; self.cfg = config
        filter = BackpackFilter(size: config.filterSize)
    }

    private func bounds() -> WindowBounds? {
        guard let w = window(), w.width > 100, w.height > 100 else { return nil }
        return w
    }

    private func point(_ p: RelPoint?) -> (x: Int, y: Int)? {
        guard let w = bounds(), let p else { return nil }
        return p.absolute(in: w)
    }

    private func region(_ r: RelRegion?) -> RGBImage? {
        guard let w = bounds(), let r else { return nil }
        return screen.grab(r.absolute(in: w))
    }

    /// nil when no template is configured, otherwise whether the template is in the region.
    private func templateIn(_ r: RelRegion?, _ template: RGBImage?) -> Bool? {
        guard let template else { return nil }
        guard let img = region(r) else { return false }
        return ImageSearch.find(img, template: template, tolerance: cfg.tolerance, step: 2) != nil
    }

    public func robloxPresent() -> Bool { bounds() != nil }

    public func backpackRaw() -> Int? {
        guard let p = point(cfg.backpackPixel) else { return nil }
        let rgb = screen.pixel(x: p.x, y: p.y)
        lastBackpackRGB = rgb
        guard let c = rgb else { return nil }
        return Hud.backpackPercent(r: c.r, g: c.g, b: c.b)
    }

    public func backpackPercent() -> Int { filter.push(backpackRaw()) }
    public func backpackUnreadableStreak() -> Int { filter.unreadableStreak }
    public func resetBackpackFilter() { filter.reset() }

    public func healthGrey() -> Bool {
        guard let p = point(cfg.healthPixel), let c = screen.pixel(x: p.x, y: p.y) else { return false }
        return Hud.isGrey(r: c.r, g: c.g, b: c.b)
    }

    public func hivePromptVisible() -> Bool? { templateIn(cfg.hivePromptRegion, cfg.hivePromptTemplate) }

    public func hiveViewVisible() -> Bool? {
        if let r = templateIn(cfg.hiveViewRegion, cfg.hiveViewTemplate) { return r }
        guard cfg.hiveStripEnabled, let strip = region(cfg.hiveStripRegion) else { return nil }
        // Existance macro: white respawn pad or blue balloon colours in the bottom strip.
        let white = ImageSearch.countHLS(strip, low: (0, 40, 0), high: (40, 100, 30))
        let blue = ImageSearch.countHLS(strip, low: (105, 55, 82), high: (120, 86, 100))
        return white + blue >= cfg.hiveStripMinPixels
    }

    public func cannonPromptVisible() -> Bool? { templateIn(cfg.hivePromptRegion, cfg.cannonPromptTemplate) }
    public func deathTextVisible() -> Bool? { templateIn(cfg.deathRegion, cfg.deathTemplate) }
}
