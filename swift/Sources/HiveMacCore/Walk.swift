import Foundation

public let studsPerTile = 4.0

/// Key and mouse output. The real one posts CGEvents; tests use a fake.
public protocol Actuator: AnyObject {
    func keyDown(_ key: String)
    func keyUp(_ key: String)
    func tap(_ key: String, holdS: Double)
    func mouseDown()
    func mouseUp()
    func releaseAll()
}

public protocol Clock: AnyObject {
    func now() -> Double
    func sleep(_ seconds: Double)
}

public final class RealClock: Clock {
    public init() {}
    public func now() -> Double { ProcessInfo.processInfo.systemUptime }
    public func sleep(_ seconds: Double) { if seconds > 0 { Thread.sleep(forTimeInterval: seconds) } }
}

/// A thread safe on/off flag, used for stop and pause.
public final class Signal: @unchecked Sendable {
    private let lock = NSLock()
    private var flag = false
    public init(_ initial: Bool = false) { flag = initial }
    public var isSet: Bool { lock.lock(); defer { lock.unlock() }; return flag }
    public func set() { lock.lock(); flag = true; lock.unlock() }
    public func clear() { lock.lock(); flag = false; lock.unlock() }
}

/// Walk speed in studs per second: base from settings times a live multiplier.
public struct SpeedModel {
    public var baseSpeed: Double
    public var multiplier: () -> Double

    public init(baseSpeed: Double = 28, multiplier: @escaping () -> Double = { 1.0 }) {
        self.baseSpeed = baseSpeed; self.multiplier = multiplier
    }

    public func current() -> Double {
        var m = multiplier()
        if m <= 0 { m = 1 }
        return max(1, baseSpeed) * m
    }

    public func secondsForTiles(_ tiles: Double) -> Double { max(0, tiles) * studsPerTile / current() }
}

/// Open loop walking, the Natro way: hold a key for `4 * tiles / speed` seconds, in small
/// slices so a stop or pause interrupts within `slice` seconds. Keys are always released.
public final class Walker {
    public var speed: SpeedModel
    private let act: Actuator
    private let clock: Clock
    private let stop: Signal
    private let pause: Signal?
    private let slice: Double

    public init(actuator: Actuator, speed: SpeedModel, clock: Clock = RealClock(), stop: Signal = Signal(),
                pause: Signal? = nil, slice: Double = 0.05) {
        self.act = actuator; self.speed = speed; self.clock = clock; self.stop = stop; self.pause = pause; self.slice = slice
    }

    public var stopped: Bool { stop.isSet }

    /// Hold keys for `seconds` of effective (unpaused) time. Returns how long they were held.
    @discardableResult
    public func hold(_ keys: [String], _ seconds: Double) -> Double {
        var held = 0.0
        if stop.isSet { return held }
        keys.forEach(act.keyDown)
        defer { keys.forEach(act.keyUp) }
        var remaining = seconds
        while remaining > 0 && !stop.isSet {
            if let pause, pause.isSet {
                keys.forEach(act.keyUp)
                while pause.isSet && !stop.isSet { clock.sleep(slice) }
                if stop.isSet { return held }
                keys.forEach(act.keyDown)
            }
            let step = min(slice, remaining)
            let t0 = clock.now()
            clock.sleep(step)
            var dt = clock.now() - t0
            if dt <= 0 { dt = step }
            held += dt
            remaining -= dt
        }
        return held
    }

    /// Natro's nm_Walk.
    @discardableResult
    public func walk(_ keys: [String], tiles: Double) -> Double { hold(keys, speed.secondsForTiles(tiles)) }

    public func wait(_ seconds: Double) {
        let end = clock.now() + seconds
        while !stop.isSet {
            let left = end - clock.now()
            if left <= 0 { return }
            clock.sleep(min(slice, left))
        }
    }

    public func taps(_ key: String, count: Int, gap: Double = 0.06) {
        for _ in 0..<count {
            if stop.isSet { return }
            act.tap(key, holdS: 0.03)
            clock.sleep(gap)
        }
    }

    /// Camera yaw: one tap of , or . is 45 degrees in Roblox.
    public func rotate(_ direction: String, taps n: Int, leftKey: String = ",", rightKey: String = ".") {
        taps(direction == "left" ? leftKey : rightKey, count: n)
    }

    public enum WalkError: Error { case unknownStep(String) }

    /// Execute path or pattern steps. Returns false if interrupted by stop.
    @discardableResult
    public func run(_ steps: [Step], keymap: [String: String] = [:]) throws -> Bool {
        func mapped(_ k: String) -> String { keymap[k] ?? k }
        for s in steps {
            if stop.isSet { return false }
            switch s.type {
            case "walk": walk(s.keys.map(mapped), tiles: s.tiles)
            case "hold": hold(s.keys.map(mapped), s.seconds)
            case "rotate": rotate(s.direction, taps: s.count, leftKey: keymap["rot_left"] ?? ",", rightKey: keymap["rot_right"] ?? ".")
            case "tap": taps(mapped(s.key), count: s.count)
            case "wait": wait(s.seconds)
            case "zoom": taps(s.direction == "out" ? (keymap["zoom_out"] ?? "o") : (keymap["zoom_in"] ?? "i"), count: s.count)
            case "mouse": s.direction == "down" ? act.mouseDown() : act.mouseUp()
            default: throw WalkError.unknownStep(s.type)
            }
        }
        return !stop.isSet
    }
}
