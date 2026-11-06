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

    var label: String { self == .error ? "Stopped" : rawValue.capitalized }
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
    @Published var runs: [RunEntry] = []
    @Published var mobTimers = MobTimers()
    @Published var recording = false
    @Published var calibMessage: String?
    let keyRecorder = KeyRecorder()
    @Published var remoteOn = false
    @Published var remoteURL = ""
    @Published var remoteMessage: String?
    var remote: RemoteServer?
    let beatLock = NSLock()
    var watchdog = Watchdog(now: Date().timeIntervalSince1970)
    func beat() { beatLock.lock(); watchdog.beat(at: Date().timeIntervalSince1970); beatLock.unlock() }
    func stalled() -> Bool { beatLock.lock(); defer { beatLock.unlock() }; return watchdog.isStalled(now: Date().timeIntervalSince1970, running: running, paused: paused) }
    @Published var activeRunFile = "default_profile.json"
    @Published var hive = HiveProfile()
    @Published var stopKeyName = "f9"
    @Published var stopKeyMessage: String?
    @Published var settingsVersion = 0

    // MARK: Engine
    let dirs: AppDirs
    let store: ConfigStore
    let stopSignal = Signal()
    let pauseSignal = Signal()
    var game: Game?
    let input = KeyInput()
    let capture = ScreenCapture()
    let hotKey = StopHotKey()
    var runtimeTimer: Timer?
    var pollTimer: DispatchSourceTimer?
    let pollQueue = DispatchQueue(label: "hivemac.poll", qos: .utility)
    let builtInPaths: URL
    var logFile: FileHandle?

    init() {
        dirs = AppDirs.standard()
        try? dirs.ensure()
        builtInPaths = AppModel.findBuiltInPaths()
        let defaults = AppModel.findDefaultConfig()
        store = (try? ConfigStore(defaultsURL: defaults, url: dirs.settings)) ?? ConfigStore(defaults: [:], url: dirs.settings)
        activeRunFile = store.string("app.active_run_file", "default_profile.json")
        if !FileManager.default.fileExists(atPath: dirs.profiles.appendingPathComponent(activeRunFile).path) { activeRunFile = "default_profile.json" }
        profile = (try? Profile.load(dirs.profiles.appendingPathComponent(activeRunFile))) ?? Profile()
        hive = HiveProfile(store: store)
        refreshRuns()
        mobTimers = MobTimers.load(dirs.data.appendingPathComponent("mob_timers.json"))
        if store.bool("remote.enabled", false) && ProcessInfo.processInfo.environment["HIVEMAC_DEMO"] == nil { DispatchQueue.main.async { self.setRemote(true) } }
        logFile = AppModel.openLog(dirs.logs.appendingPathComponent("hivemac.log"))
        stopKeyName = store.string("app.emergency_stop_key", "f9")
        hotKey.onPress = { [weak self] in self?.stop() }
        if case .success(let code) = KeyCodes.validateStopKey(stopKeyName) { hotKey.register(keyCode: UInt32(code)) }
        else { setStopKey("f9") }
        append("HiveMac started. Data folder: \(dirs.data.path)")
        if ProcessInfo.processInfo.environment["HIVEMAC_DEMO"] != nil { applyDemo() } else { startPolling() }
    }


    /// The Roblox window content right now, using the window mode and title bar from the settings.
    static func bounds(_ store: ConfigStore) -> WindowBounds? {
        WindowFinder.contentBounds(mode: store.string("game.window_mode", "windowed"),
                                   titleBar: store.int("game.title_bar_height", 28))
    }
    var robloxBounds: WindowBounds? { Self.bounds(store) }

    // MARK: Resources
    static func resource(_ relative: String, dev: String) -> URL {
        if let r = Bundle.main.resourceURL?.appendingPathComponent(relative), FileManager.default.fileExists(atPath: r.path) { return r }
        // Running from the build folder (swift run): the repo is a few folders up from this file.
        let repo = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        return repo.appendingPathComponent(dev)
    }

    static func findBuiltInPaths() -> URL { resource("paths", dev: "config/paths/natro") }
    static func findDefaultConfig() -> URL { resource("default_config.json", dev: "config/default_config.json") }

    static func openLog(_ url: URL) -> FileHandle? {
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
        guard robloxBounds != nil else {
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
        let screenSensors = ScreenSensors(screen: capture, window: { [store] in Self.bounds(store) }, config: hud)
        let sensors = ReportingSensors(screenSensors)
        sensors.onBackpack = { [weak self] p in self?.beat(); DispatchQueue.main.async { self?.backpack = p } }

        let builtIn = builtInPaths, dirs = self.dirs
        let g = Game(actuator: input, sensors: sensors, settings: settings, clock: RealClock(),
                     stop: stopSignal, pause: pauseSignal,
                     status: { [weak self] s, d in self?.beat(); DispatchQueue.main.async { self?.setStatus(RunState(rawValue: s) ?? .warning, d) } },
                     windowSize: { [store] in Self.bounds(store).map { ($0.left, $0.top, $0.width, $0.height) } },
                     pathLookup: { kind, field, variant in
                         dirs.findPath(kind: kind, field: field, variant: variant, builtIn: builtIn).flatMap { try? PathFile.load($0) }
                     })
        game = g
        let loop = FarmLoop(g, fields: profile.fields)
        loop.onStats = { [weak self] s in DispatchQueue.main.async { self?.stats = s } }

        watchdog = Watchdog(timeout: store.double("timing.watchdog_timeout_sec", 90), now: Date().timeIntervalSince1970)
        running = true; paused = false; runtimeSeconds = 0; stats = LoopStats()
        setStatus(.resetting, "Starting")
        runtimeTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self, self.running else { return }
                if !self.paused { self.runtimeSeconds += 1 }
                if self.stalled() { self.append("Watchdog: nothing happened for a while, stopping."); self.setStatus(.error, "Stopped: the macro stopped responding"); self.stop() }
            }
        }
        WindowFinder.focusRoblox()
        Thread.detachNewThread { [weak self] in
            let why = loop.run()
            g.releaseEverything()
            DispatchQueue.main.async { self?.finished(why: why) }
        }
    }

    func finished(why: String) {
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

    func setStatus(_ s: RunState, _ d: String) {
        if running && paused && s != .paused { return }       // a late status must not hide the pause
        state = s; detail = d
        if s == .gathering || s == .traveling { currentField = d.split(separator: " ").first.map(String.init) ?? currentField }
        if !d.isEmpty { append("\(s.label): \(d)") }
    }

}
