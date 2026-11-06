import Foundation

/// The settings file, read and written as JSON with dotted paths ("game.walk_speed"). It is the
/// same file and key names the Python app uses, so both can share one data folder. Missing keys
/// fall back to the defaults file; unknown keys are kept when saving.
public final class ConfigStore {
    public private(set) var values: [String: Any]
    private let defaults: [String: Any]
    private let url: URL?
    private let lock = NSLock()

    public init(defaults: [String: Any], url: URL?) {
        self.defaults = defaults; self.url = url
        values = Self.merge(defaults, with: [:])
        load()
    }

    public convenience init(defaultsURL: URL, url: URL?) throws {
        let data = try Data(contentsOf: defaultsURL)
        let obj = (try JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        self.init(defaults: obj, url: url)
    }

    private static func merge(_ base: [String: Any], with over: [String: Any]) -> [String: Any] {
        var out = base
        for (k, v) in over {
            if let b = out[k] as? [String: Any], let o = v as? [String: Any] { out[k] = merge(b, with: o) } else { out[k] = v }
        }
        return out
    }

    public func load() {
        lock.lock(); defer { lock.unlock() }
        guard let url, let data = try? Data(contentsOf: url),
              let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return }
        values = Self.merge(defaults, with: obj)
    }

    public func save() throws {
        lock.lock(); defer { lock.unlock() }
        guard let url else { return }
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        let data = try JSONSerialization.data(withJSONObject: values, options: [.prettyPrinted, .sortedKeys])
        try data.write(to: url, options: .atomic)
    }

    public func get(_ path: String) -> Any? {
        lock.lock(); defer { lock.unlock() }
        var cur: Any? = values
        for part in path.split(separator: ".") { cur = (cur as? [String: Any])?[String(part)] }
        return cur
    }

    public func double(_ path: String, _ fallback: Double = 0) -> Double { (get(path) as? NSNumber)?.doubleValue ?? fallback }
    public func int(_ path: String, _ fallback: Int = 0) -> Int { (get(path) as? NSNumber)?.intValue ?? fallback }
    public func bool(_ path: String, _ fallback: Bool = false) -> Bool { (get(path) as? NSNumber)?.boolValue ?? fallback }
    public func string(_ path: String, _ fallback: String = "") -> String { (get(path) as? String) ?? fallback }

    public func set(_ path: String, _ value: Any) {
        lock.lock(); defer { lock.unlock() }
        let parts = path.split(separator: ".").map(String.init)
        func put(_ dict: [String: Any], _ i: Int) -> [String: Any] {
            var d = dict
            if i == parts.count - 1 { d[parts[i]] = value } else { d[parts[i]] = put((d[parts[i]] as? [String: Any]) ?? [:], i + 1) }
            return d
        }
        values = put(values, 0)
    }

    /// The game section as typed settings, taking Python's key names.
    public func gameSettings() -> GameSettings {
        var s = GameSettings()
        s.walkSpeed = double("game.walk_speed", s.walkSpeed)
        s.hiveSlot = int("game.hive_slot", s.hiveSlot)
        s.sprinklerType = string("game.sprinkler_type", s.sprinklerType)
        s.sprinklerSlotKey = string("game.sprinkler_slot_key", s.sprinklerSlotKey)
        s.travel = string("game.travel", s.travel)
        s.windowMode = string("game.window_mode", s.windowMode)
        s.titleBarHeight = int("game.title_bar_height", s.titleBarHeight)
        s.zoomOutTaps = int("game.zoom_out_taps", s.zoomOutTaps)
        s.resetWaitS = double("game.reset_wait_s", s.resetWaitS)
        s.deathExtraWaitS = double("game.death_extra_wait_s", s.deathExtraWaitS)
        s.resetAttempts = int("game.reset_attempts", s.resetAttempts)
        s.respawnTimeoutS = double("game.respawn_timeout_s", s.respawnTimeoutS)
        s.convertTimeoutS = double("game.convert_timeout_s", s.convertTimeoutS)
        s.convertPressRetryS = double("game.convert_press_retry_s", s.convertPressRetryS)
        s.cameraSearchTaps = int("game.camera_search_taps", s.cameraSearchTaps)
        s.cameraAfterFoundTaps = int("game.camera_after_found_taps", s.cameraAfterFoundTaps)
        s.useTool = bool("game.use_tool", s.useTool)
        s.backpackSampleS = double("game.backpack_sample_s", s.backpackSampleS)
        s.lostScreenS = double("game.lost_screen_s", s.lostScreenS)
        s.keyGapS = double("game.key_gap_s", s.keyGapS)
        s.rotLeft = string("game.rot_left", s.rotLeft)
        s.rotRight = string("game.rot_right", s.rotRight)
        s.zoomIn = string("game.zoom_in", s.zoomIn)
        s.zoomOut = string("game.zoom_out", s.zoomOut)
        if let mp = get("game.mouse_park") as? [NSNumber], mp.count == 2 { s.mousePark = (mp[0].doubleValue, mp[1].doubleValue) }
        return s
    }
}
