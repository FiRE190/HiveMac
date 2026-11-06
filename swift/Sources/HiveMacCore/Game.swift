import Foundation

/// What the macro can see. The real one reads small screen regions; tests use a simulated world.
/// Optional answers (`Bool?`) mean "no check is set up", and the loop then assumes the best.
public protocol Sensors: AnyObject {
    func robloxPresent() -> Bool
    func backpackPercent() -> Int
    func backpackUnreadableStreak() -> Int
    func resetBackpackFilter()
    func healthGrey() -> Bool
    func hivePromptVisible() -> Bool?
    func hiveViewVisible() -> Bool?
    func cannonPromptVisible() -> Bool?
    func deathTextVisible() -> Bool?
}

public struct GameSettings: Equatable, Sendable {
    public var walkSpeed = 28.0
    public var hiveSlot = 1
    public var sprinklerType = "none"
    public var sprinklerSlotKey = "1"
    public var travel = "walk"              // default path variant: walk or cannon
    public var windowMode = "windowed"
    public var titleBarHeight = 28
    public var zoomOutTaps = 6
    public var resetWaitS = 2.0             // minimum time between reset and the next walk
    public var deathExtraWaitS = 18.0       // the death screen is longer than a plain reset
    public var resetAttempts = 5
    public var respawnTimeoutS = 12.0
    public var convertTimeoutS = 300.0
    public var convertPressRetryS = 6.0
    public var cameraSearchTaps = 2         // yaw step while looking for the hive view
    public var cameraAfterFoundTaps = 4     // Natro: 180 degrees once the hive is in view
    public var useTool = true               // hold the mouse button while gathering
    public var backpackSampleS = 1.0
    public var lostScreenS = 60.0           // unreadable backpack this long means we are lost
    public var keyGapS = 0.3                // between Esc, R, Enter
    public var rotLeft = ","
    public var rotRight = "."
    public var zoomIn = "i"
    public var zoomOut = "o"
    public var mousePark: (x: Double, y: Double) = (0.25, 0.2)   // fraction of the window

    public init() {}

    public static func == (a: GameSettings, b: GameSettings) -> Bool {
        a.walkSpeed == b.walkSpeed && a.hiveSlot == b.hiveSlot && a.travel == b.travel
            && a.zoomOutTaps == b.zoomOutTaps && a.resetWaitS == b.resetWaitS
            && a.mousePark.x == b.mousePark.x && a.mousePark.y == b.mousePark.y
    }
}

public struct FieldConfig: Equatable, Sendable {
    public var name: String
    public var pattern = "corner_x_snake"
    public var size = "m"
    public var width = 4
    public var invertFB = false
    public var invertLR = false
    public var camera = "none"              // none, left, right
    public var turns = 1
    public var minutes = 10.0
    public var backpackPercent = 95
    public var sprinklerLocation = "center"
    public var sprinklerDistance = 1
    public var shiftLock = false
    public var travel = "default"           // default, walk, cannon
    /// walk: Natro's default (walk to the hive and convert there). reset: Esc R Enter instead.
    public var returnMethod = "walk"
    public var enabled = true

    /// True when the field turns the camera after arriving (and back before leaving).
    public var rotatesCamera: Bool { (camera == "left" || camera == "right") && turns > 0 }

    /// Natro's defaults for the field, with the fields given in `overrides` replacing them.
    public init(name: String) {
        let lower = name.lowercased()
        self.name = lower
        if let d = FieldDefaults.table[lower] {
            pattern = d.pattern; size = d.size; width = d.width; camera = d.camera; turns = d.turns
            sprinklerLocation = d.sprinkler; sprinklerDistance = d.distance
            invertFB = d.invertFB; invertLR = d.invertLR
        }
    }
}

public struct GatherResult: Equatable, Sendable {
    public var reason: String       // backpack, time, death, lost, stopped
    public var seconds: Double = 0
    public var backpack: Int = 0
    public init(reason: String, seconds: Double = 0, backpack: Int = 0) {
        self.reason = reason; self.seconds = seconds; self.backpack = backpack
    }
}

public typealias PathLookup = (_ kind: String, _ field: String, _ variant: String) -> PathFile?

/// The Natro style game actions, written against `Sensors` and `Actuator` so the whole loop
/// runs in tests with fakes. Every action is interruptible through the walker's stop and
/// pause signals and leaves no key held when it returns.
public final class Game {
    public let actuator: Actuator
    public let sensors: Sensors
    public var settings: GameSettings
    public let clock: Clock
    public let stop: Signal
    public let pause: Signal
    public let walker: Walker
    public var speed: SpeedModel { walker.speed }
    public var status: (_ state: String, _ detail: String) -> Void
    public var windowSize: () -> (left: Int, top: Int, width: Int, height: Int)?
    public var pathLookup: PathLookup

    public private(set) var shiftLocked = false
    public var died = false

    public init(actuator: Actuator, sensors: Sensors, settings: GameSettings, clock: Clock,
                stop: Signal = Signal(), pause: Signal = Signal(),
                speedMultiplier: @escaping () -> Double = { 1.0 },
                status: @escaping (String, String) -> Void = { _, _ in },
                windowSize: @escaping () -> (left: Int, top: Int, width: Int, height: Int)? = { nil },
                pathLookup: @escaping PathLookup = { _, _, _ in nil }) {
        self.actuator = actuator; self.sensors = sensors; self.settings = settings; self.clock = clock
        self.stop = stop; self.pause = pause; self.status = status
        self.windowSize = windowSize; self.pathLookup = pathLookup
        self.walker = Walker(actuator: actuator, speed: SpeedModel(baseSpeed: settings.walkSpeed, multiplier: speedMultiplier),
                             clock: clock, stop: stop, pause: pause)
    }

    public var stopped: Bool { stop.isSet }

    private func wait(_ s: Double) { walker.wait(s) }
    private func tap(_ key: String) { actuator.tap(key, holdS: 0.03) }

    public func keymap() -> [String: String] {
        ["rot_left": settings.rotLeft, "rot_right": settings.rotRight,
         "zoom_in": settings.zoomIn, "zoom_out": settings.zoomOut]
    }

    private func run(_ steps: [Step], _ km: [String: String]? = nil) {
        _ = try? walker.run(steps, keymap: km ?? keymap())
    }

    private func iterSteps(_ pf: PathFile) -> [Step] {
        Paths.scaleHolds(Paths.expand(pf.steps, hiveSlot: settings.hiveSlot),
                         recordedSpeed: pf.walkSpeed, actualSpeed: speed.current())
    }

    public func parkMouse() {
        guard let ws = windowSize() else { return }
        actuator.moveMouse(ws.left + Int(Double(ws.width) * settings.mousePark.x),
                           ws.top + Int(Double(ws.height) * settings.mousePark.y))
    }

    public func setShiftLock(_ on: Bool) {
        if on != shiftLocked { tap("shift"); shiftLocked = on; wait(0.2) }
    }

    public func releaseEverything() { actuator.releaseAll() }

    // MARK: Reset

    /// Esc, R, Enter; wait for the respawn; confirm the hive; fix the camera.
    public func resetToHive(afterDeath: Bool = false) -> Bool {
        let s = settings
        releaseEverything()
        setShiftLock(false)
        for attempt in 1...max(1, s.resetAttempts) {
            if stopped { return false }
            status("resetting", "attempt \(attempt)")
            parkMouse()
            tap("esc"); wait(s.keyGapS)
            tap("r"); wait(s.keyGapS)
            tap("enter")
            waitForRespawn()
            let extra = (afterDeath || died) ? s.deathExtraWaitS : 0
            died = false
            wait(s.resetWaitS + extra)
            if stopped { return false }
            sensors.resetBackpackFilter()
            let atHive = sensors.hivePromptVisible()
            if atHive == false {
                status("resetting", "hive prompt not seen, retrying")
                continue
            }
            if atHive == nil { status("resetting", "no hive prompt template, assuming at hive") }
            _ = fixCamera()
            return true
        }
        status("error", "could not confirm the hive after reset")
        return false
    }

    /// Natro: the health bar goes grey (dead) then comes back. Falls back to a fixed wait.
    private func waitForRespawn() {
        let t0 = clock.now()
        var seenGrey = false
        while !stopped && clock.now() - t0 < settings.respawnTimeoutS {
            if sensors.healthGrey() { seenGrey = true } else if seenGrey { return }
            wait(0.1)
        }
        if !seenGrey { wait(1.0) }
    }

    /// Rotate until the hive is in view (when a check exists), face away, zoom out.
    @discardableResult
    public func fixCamera() -> Bool {
        let s = settings
        var found = sensors.hiveViewVisible()
        if found != nil {
            var taps = 0
            while found == false && taps < 16 && !stopped {
                walker.rotate("right", taps: s.cameraSearchTaps, leftKey: s.rotLeft, rightKey: s.rotRight)
                taps += s.cameraSearchTaps
                wait(0.25)
                found = sensors.hiveViewVisible()
            }
            if found == true {
                walker.rotate("right", taps: s.cameraAfterFoundTaps, leftKey: s.rotLeft, rightKey: s.rotRight)
            } else {
                status("warning", "hive view not found while rotating")
            }
        }
        walker.taps(s.zoomOut, count: s.zoomOutTaps)
        return found ?? true
    }

    // MARK: Convert

    /// Press E at the hive and wait until the backpack reads empty (Natro's nm_convert).
    public func convert() -> Bool {
        let s = settings
        if stopped { return false }
        status("converting", "")
        let t0 = clock.now()
        var lastPress = -1e9
        var emptyReads = 0
        var lastPct: Int?
        while !stopped && clock.now() - t0 < s.convertTimeoutS {
            let pct = sensors.backpackPercent()
            if lastPct == nil || (clock.now() - lastPress > s.convertPressRetryS && pct >= lastPct! && pct > 0) {
                tap("e")
                lastPress = clock.now()
                lastPct = pct
            }
            if pct <= 0 {
                emptyReads += 1
                if emptyReads >= 3 { status("converting", "done"); return true }
            } else {
                emptyReads = 0
                lastPct = lastPct.map { min($0, pct) } ?? pct
            }
            wait(s.backpackSampleS)
        }
        return false
    }

    // MARK: Travel

    public func travelTo(_ f: FieldConfig) -> Bool {
        let s = settings
        let variant = f.travel == "default" ? s.travel : f.travel
        var pf = pathLookup("to_field", f.name, variant)
        if pf == nil && variant != "walk" {
            status("traveling", "no \(variant) path for \(f.name), walking")
            pf = pathLookup("to_field", f.name, "walk")
        }
        guard let path = pf else { status("error", "no path to \(f.name)"); return false }
        status("traveling", f.name)
        setShiftLock(false)
        parkMouse()
        for step in iterSteps(path) {
            if stopped { return false }
            if step.type == "gotocannon" {
                if !goToCannon() { return false }
                continue
            }
            run([step])
        }
        run(Sprinkler.startLocationSteps(field: f.name, location: f.sprinklerLocation,
                                         distance: f.sprinklerDistance, speed: speed.current()), [:])
        run(Sprinkler.placementSteps(type: s.sprinklerType, location: f.sprinklerLocation,
                                     slotKey: s.sprinklerSlotKey, speed: speed.current()), [:])
        if f.rotatesCamera {
            walker.rotate(f.camera, taps: f.turns, leftKey: s.rotLeft, rightKey: s.rotRight)
        }
        return !stopped
    }

    /// Natro nm_gotoCannon, simplified: jump right onto the pad, then creep right until the
    /// cannon prompt shows (when a check exists).
    public func goToCannon() -> Bool {
        for _ in 0..<3 {
            if stopped { return false }
            actuator.keyDown("space"); actuator.keyDown("d")
            wait(0.1)
            actuator.keyUp("space")
            walker.walk(["d"], tiles: 2)
            walker.walk(["w", "d"], tiles: 1.5)
            actuator.keyUp("d")
            var seen = sensors.cannonPromptVisible()
            if seen == nil { return true }
            let t0 = clock.now()
            actuator.keyDown("d")
            while seen != true && clock.now() - t0 < 2.0 && !stopped {
                wait(0.1)
                seen = sensors.cannonPromptVisible()
            }
            actuator.keyUp("d")
            if seen == true { return true }
            status("traveling", "cannon not found, resetting")
            if !resetToHive() { return false }
            run(iterSteps(PathFile(name: "ramp", steps: [Step(type: "gotoramp")])))
        }
        return false
    }

    // MARK: Gather

    public func gather(_ f: FieldConfig) -> GatherResult {
        let s = settings
        var km = keymap()
        km.merge(Paths.bindPatternKeys(invertFB: f.invertFB, invertLR: f.invertLR)) { _, new in new }
        let steps = (try? Patterns.build(f.pattern, size: f.size, width: f.width)) ?? []
        status("gathering", "\(f.name) \(f.pattern) \(f.size) w\(f.width) until \(f.backpackPercent)% or \(f.minutes) min")
        let t0 = clock.now()
        var lastSample = -1e9
        var greyStreak = 0
        var reason = "stopped"
        var pct = sensors.backpackPercent()
        setShiftLock(f.shiftLock)
        parkMouse()
        if s.useTool { actuator.mouseDown() }
        defer {
            if s.useTool { actuator.mouseUp() }
            setShiftLock(false)
        }
        if steps.isEmpty { return GatherResult(reason: "stopped", seconds: 0, backpack: pct) }
        outer: while !stopped {
            for step in steps {
                if stopped { break outer }
                let now = clock.now()
                if now - lastSample >= s.backpackSampleS {
                    lastSample = now
                    pct = sensors.backpackPercent()
                    greyStreak = sensors.healthGrey() ? greyStreak + 1 : 0
                    let deadText = sensors.deathTextVisible() == true
                    if greyStreak >= 2 || deadText { died = true; reason = "death"; break outer }
                    if pct >= f.backpackPercent { reason = "backpack"; break outer }
                    if Double(sensors.backpackUnreadableStreak()) * s.backpackSampleS >= s.lostScreenS {
                        reason = "lost"; break outer
                    }
                }
                if now - t0 >= f.minutes * 60 { reason = "time"; break outer }
                run([step], km)
            }
        }
        if stopped { reason = "stopped" }
        return GatherResult(reason: reason, seconds: clock.now() - t0, backpack: pct)
    }

    // MARK: Walk back

    /// Walk from the field to the hive pad (Natro's wf-* routes), then slide left until the hive prompt shows.
    public func walkBack(_ f: FieldConfig) -> Bool {
        let s = settings
        guard let pf = pathLookup("to_hive", f.name, "walk") else { return false }
        status("traveling", "hive")
        if f.rotatesCamera {
            walker.rotate(f.camera == "left" ? "right" : "left", taps: f.turns, leftKey: s.rotLeft, rightKey: s.rotRight)
        }
        setShiftLock(false)
        for step in iterSteps(pf) {
            if stopped { return false }
            run([step])
        }
        let t0 = clock.now()
        var seen = sensors.hivePromptVisible()
        if seen == nil { return true }
        actuator.keyDown("a")
        while seen != true && clock.now() - t0 < 15 && !stopped {
            wait(0.1)
            seen = sensors.hivePromptVisible()
        }
        actuator.keyUp("a")
        return seen == true
    }
}
