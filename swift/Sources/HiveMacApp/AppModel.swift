import SwiftUI
import AppKit
import HiveMacCore
import HiveMacPlatform

/// Forwards every sensor read to the real sensors and reports the backpack reading, so the
/// window can show it live while the macro runs.
final class ReportingSensors: Sensors {
    let inner: Sensors
    var onBackpack: (Int) -> Void = { _ in }
    init(_ inner: Sensors) { self.inner = inner }
    func robloxPresent() -> Bool { inner.robloxPresent() }
    func backpackPercent() -> Int { let p = inner.backpackPercent(); onBackpack(p); return p }
    func backpackUnreadableStreak() -> Int { inner.backpackUnreadableStreak() }
    func resetBackpackFilter() { inner.resetBackpackFilter() }
    func healthGrey() -> Bool { inner.healthGrey() }
    func hivePromptVisible() -> Bool? { inner.hivePromptVisible() }
    func hiveViewVisible() -> Bool? { inner.hiveViewVisible() }
    func cannonPromptVisible() -> Bool? { inner.cannonPromptVisible() }
    func deathTextVisible() -> Bool? { inner.deathTextVisible() }
}

enum RunState: String {
    case idle, resetting, converting, traveling, gathering, paused, warning, error

    var label: String {
        switch self {
        case .idle: return "Idle"
        case .resetting: return "Resetting"
        case .converting: return "Converting"
        case .traveling: return "Traveling"
        case .gathering: return "Gathering"
        case .paused: return "Paused"
        case .warning: return "Warning"
        case .error: return "Stopped with an error"
        }
    }
}

struct LiveReadings: Equatable {
    var windowFound = false
    var windowText = "Roblox not found"
    var backpack: Int?
    var backpackRGB: String?
    var healthGrey: Bool?
    var hivePrompt: Bool?
    var calibrated = false
}

@MainActor
final class AppModel: ObservableObject {
    // MARK: Published state
    @Published var state: RunState = .idle
    @Published var detail = ""
    @Published var running = false
    @Published var paused = false
    @Published var runtimeSeconds = 0
    @Published var stats = LoopStats()
    @Published var backpack: Int?
    @Published var currentField = ""
    @Published var log: [String] = []
    @Published var permissions = Permissions.current()
    @Published var live = LiveReadings()
    @Published var profile = Profile()
    @Published var hive = HiveProfile()
    @Published var stopKeyName = "f9"
    @Published var stopKeyMessage: String?
    @Published var settingsVersion = 0

    // MARK: Engine
    let dirs: AppDirs
    let store: ConfigStore
    private let stopSignal = Signal()
    private let pauseSignal = Signal()
    private var game: Game?
    private let input = KeyInput()
    private let capture = ScreenCapture()
    private let hotKey = StopHotKey()
    private var runtimeTimer: Timer?
    private var pollTimer: DispatchSourceTimer?
    private let pollQueue = DispatchQueue(label: "hivemac.poll", qos: .utility)
    private let builtInPaths: URL
    private var logFile: FileHandle?

    init() {
        dirs = AppDirs.standard()
        try? dirs.ensure()
        builtInPaths = AppModel.findBuiltInPaths()
        let defaults = AppModel.findDefaultConfig()
        store = (try? ConfigStore(defaultsURL: defaults, url: dirs.settings)) ?? ConfigStore(defaults: [:], url: dirs.settings)
        profile = (try? Profile.load(dirs.profiles.appendingPathComponent("default_profile.json"))) ?? Profile()
        hive = HiveProfile(store: store)
        logFile = AppModel.openLog(dirs.logs.appendingPathComponent("hivemac.log"))
        stopKeyName = store.string("app.emergency_stop_key", "f9")
        hotKey.onPress = { [weak self] in self?.stop() }
        if case .success(let code) = KeyCodes.validateStopKey(stopKeyName) { hotKey.register(keyCode: UInt32(code)) }
        else { setStopKey("f9") }
        append("HiveMac started. Data folder: \(dirs.data.path)")
        if ProcessInfo.processInfo.environment["HIVEMAC_DEMO"] != nil { applyDemo() } else { startPolling() }
    }

    /// Made-up numbers for pictures and for trying the layout. Nothing here reads the game or the
    /// real settings; run it with HIVEMAC_HOME pointing at a scratch folder.
    var isDemo: Bool { ProcessInfo.processInfo.environment["HIVEMAC_DEMO"] != nil }

    private func applyDemo() {
        state = .gathering; detail = "sunflower corner_x_snake m w4"
        running = true; runtimeSeconds = 2538; backpack = 72; currentField = "sunflower"
        var s = LoopStats(); s.cycles = 14; s.converts = 13; s.deaths = 1; stats = s
        permissions = PermissionStatus(screenRecording: true, accessibility: true)
        live = LiveReadings(windowFound: true, windowText: "Roblox found, 1440 by 900", backpack: 70,
                            backpackRGB: "rgb(146, 126, 78)", healthGrey: false, hivePrompt: true, calibrated: true)
        var f2 = FieldConfig(name: "pine tree"); f2.minutes = 12; f2.backpackPercent = 90
        var f3 = FieldConfig(name: "bamboo"); f3.returnMethod = "reset"
        var f4 = FieldConfig(name: "stump"); f4.enabled = false
        profile = Profile(name: "demo", fields: [FieldConfig(name: "sunflower"), f2, f3, f4])
        hive.color = "blue"; hive.cubBuddy = true
        ["Resetting: attempt 1", "Converting: done", "Traveling: sunflower", "Gathering: sunflower corner_x_snake m w4 until 95% or 10 min",
         "Traveling: hive", "Converting: done"].forEach(append)
    }

    // MARK: Resources
    private static func resource(_ relative: String, dev: String) -> URL {
        if let r = Bundle.main.resourceURL?.appendingPathComponent(relative), FileManager.default.fileExists(atPath: r.path) { return r }
        // Running from the build folder (swift run): the repo is a few folders up from this file.
        let repo = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        return repo.appendingPathComponent(dev)
    }

    static func findBuiltInPaths() -> URL { resource("paths", dev: "config/paths/natro") }
    static func findDefaultConfig() -> URL { resource("default_config.json", dev: "config/default_config.json") }

    private static func openLog(_ url: URL) -> FileHandle? {
        if !FileManager.default.fileExists(atPath: url.path) { FileManager.default.createFile(atPath: url.path, contents: nil) }
        let h = try? FileHandle(forWritingTo: url)
        _ = try? h?.seekToEnd()
        return h
    }

    // MARK: Log
    func append(_ line: String) {
        let stamp = DateFormatter.localizedString(from: Date(), dateStyle: .none, timeStyle: .medium)
        let text = "\(stamp)  \(line)"
        log.append(text)
        if log.count > 400 { log.removeFirst(log.count - 400) }
        logFile?.write(Data((text + "\n").utf8))
    }

    // MARK: Start, pause, stop
    func start() {
        guard !running else { return }
        permissions = Permissions.current()
        if !permissions.allGranted {
            setStatus(.error, permissions.problems.first ?? "Permissions are missing")
            permissions.problems.forEach(append)
            return
        }
        let mode = store.string("game.window_mode", "windowed"), bar = store.int("game.title_bar_height", 28)
        guard WindowFinder.contentBounds(mode: mode, titleBar: bar) != nil else {
            setStatus(.error, "Roblox is not open in a window. Open it, then press Start.")
            return
        }
        guard !profile.fields.filter(\.enabled).isEmpty else {
            setStatus(.error, "No field is switched on. Turn one on in Fields.")
            return
        }
        let settings = store.gameSettings()
        stopSignal.clear(); pauseSignal.clear()

        let hud = HudConfig(store: store) { name in ScreenCapture.loadPNG(self.dirs.templates.appendingPathComponent(name)) }
        let screenSensors = ScreenSensors(screen: capture, window: { [store] in
            WindowFinder.contentBounds(mode: store.string("game.window_mode", "windowed"), titleBar: store.int("game.title_bar_height", 28))
        }, config: hud)
        let sensors = ReportingSensors(screenSensors)
        sensors.onBackpack = { [weak self] p in DispatchQueue.main.async { self?.backpack = p } }

        let builtIn = builtInPaths, dirs = self.dirs
        let g = Game(actuator: input, sensors: sensors, settings: settings, clock: RealClock(),
                     stop: stopSignal, pause: pauseSignal,
                     status: { [weak self] s, d in DispatchQueue.main.async { self?.setStatus(RunState(rawValue: s) ?? .warning, d) } },
                     windowSize: { [store] in
                         WindowFinder.contentBounds(mode: store.string("game.window_mode", "windowed"), titleBar: store.int("game.title_bar_height", 28))
                             .map { ($0.left, $0.top, $0.width, $0.height) }
                     },
                     pathLookup: { kind, field, variant in
                         dirs.findPath(kind: kind, field: field, variant: variant, builtIn: builtIn).flatMap { try? PathFile.load($0) }
                     })
        game = g
        let loop = FarmLoop(g, fields: profile.fields)
        loop.onStats = { [weak self] s in DispatchQueue.main.async { self?.stats = s } }

        running = true; paused = false; runtimeSeconds = 0; stats = LoopStats()
        setStatus(.resetting, "Starting")
        runtimeTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            Task { @MainActor in if let self, self.running, !self.paused { self.runtimeSeconds += 1 } }
        }
        WindowFinder.focusRoblox()
        Thread.detachNewThread { [weak self] in
            let why = loop.run()
            g.releaseEverything()
            DispatchQueue.main.async { self?.finished(why: why) }
        }
    }

    private func finished(why: String) {
        running = false; paused = false
        runtimeTimer?.invalidate(); runtimeTimer = nil
        game = nil
        let text: String
        switch why {
        case "stopped": text = "Stopped"
        case "no_fields": text = "No field is switched on"
        case "reset_failed": text = "Could not reach the hive after several resets"
        default: text = why
        }
        setStatus(why == "reset_failed" ? .error : .idle, text)
    }

    func pause() {
        guard running, !paused else { return }
        pauseSignal.set(); paused = true
        setStatus(.paused, "Paused")
    }

    func resume() {
        guard running, paused else { return }
        pauseSignal.clear(); paused = false
        setStatus(.resetting, "Resuming")
    }

    func stop() {
        stopSignal.set(); pauseSignal.clear()
        input.releaseAll()
        if running { append("Stop requested") }
    }

    private func setStatus(_ s: RunState, _ d: String) {
        if running && paused && s != .paused { return }       // a late status must not hide the pause
        state = s; detail = d
        if s == .gathering || s == .traveling { currentField = d.split(separator: " ").first.map(String.init) ?? currentField }
        if !d.isEmpty { append("\(s.label): \(d)") }
    }

    // MARK: Stop key
    func setStopKey(_ name: String) {
        switch KeyCodes.validateStopKey(name) {
        case .failure(let e): stopKeyMessage = e.message
        case .success(let code):
            if hotKey.register(keyCode: UInt32(code)) {
                stopKeyName = name.lowercased(); stopKeyMessage = nil
                store.set("app.emergency_stop_key", stopKeyName); try? store.save()
            } else { stopKeyMessage = "macOS would not register that key. Try another." }
        }
    }

    // MARK: Profile and settings
    func saveProfile() {
        try? profile.save(to: dirs.profiles.appendingPathComponent("default_profile.json"))
    }

    func saveSettings() {
        hive.write(to: store)
        try? store.save()
        settingsVersion += 1
    }

    func set(_ path: String, _ value: Any) { store.set(path, value); try? store.save(); settingsVersion += 1 }

    // MARK: Calibration
    func requestPermissions() { Permissions.request(); refreshPermissions() }
    func refreshPermissions() { if !isDemo { permissions = Permissions.current() } }

    /// Finds Roblox and seeds the HUD spots with Natro's defaults where nothing is set yet.
    func detectRoblox() {
        let mode = store.string("game.window_mode", "windowed"), bar = store.int("game.title_bar_height", 28)
        guard let w = WindowFinder.contentBounds(mode: mode, titleBar: bar) else {
            append("Detect Roblox: no Roblox window found. Open it in a window first.")
            refreshLive(); return
        }
        let d = Layout.natroDefaults(w)
        func pt(_ p: RelPoint) -> [String: Any] { ["fx": p.fx, "fy": p.fy] }
        func rg(_ r: RelRegion) -> [String: Any] { ["fx": r.fx, "fy": r.fy, "fw": r.fw, "fh": r.fh] }
        let seeds: [(String, Any)] = [("backpack_pixel", pt(d.backpackPixel)), ("health_pixel", pt(d.healthPixel)),
                                      ("hive_prompt_region", rg(d.hivePromptRegion)), ("hive_view_region", rg(d.hiveViewRegion)),
                                      ("hive_strip_region", rg(d.hiveStripRegion))]
        for (key, value) in seeds where store.get("hud.\(key)") == nil || store.get("hud.\(key)") is NSNull {
            store.set("hud.\(key)", value)
        }
        store.set("hud.calibrated", true)
        try? store.save()
        append("Detect Roblox: window \(w.width) by \(w.height). HUD spots set from Natro's defaults.")
        refreshLive()
    }

    // MARK: Live readings (a light poll while idle, so the gauge and Calibrate tab show real values)
    private func startPolling() {
        let t = DispatchSource.makeTimerSource(queue: pollQueue)
        t.schedule(deadline: .now() + 1, repeating: 2, leeway: .milliseconds(500))
        t.setEventHandler { [weak self] in
            DispatchQueue.main.async { if let self, !self.running, NSApp.isActive { self.refreshLive() } }
        }
        t.activate()
        pollTimer = t
    }

    func refreshLive() {
        if isDemo { return }
        permissions = Permissions.current()
        let mode = store.string("game.window_mode", "windowed"), bar = store.int("game.title_bar_height", 28)
        let store = self.store, capture = self.capture, dirs = self.dirs
        let allowed = permissions.screenRecording
        pollQueue.async { [weak self] in
            var r = LiveReadings()
            let win = WindowFinder.contentBounds(mode: mode, titleBar: bar)
            r.windowFound = win != nil
            r.windowText = win.map { "Roblox found, \($0.width) by \($0.height)" } ?? "Roblox not found"
            r.calibrated = store.bool("hud.calibrated")
            if allowed, let win, r.calibrated {
                let hud = HudConfig(store: store) { ScreenCapture.loadPNG(dirs.templates.appendingPathComponent($0)) }
                let s = ScreenSensors(screen: capture, window: { win }, config: hud)
                if let raw = s.backpackRaw() { r.backpack = raw }
                if let c = s.lastBackpackRGB { r.backpackRGB = "rgb(\(c.r), \(c.g), \(c.b))" }
                r.healthGrey = s.healthGrey()
                r.hivePrompt = s.hivePromptVisible()
            }
            DispatchQueue.main.async {
                guard let self else { return }
                self.live = r
                if !self.running { self.backpack = r.backpack }
            }
        }
    }
}
