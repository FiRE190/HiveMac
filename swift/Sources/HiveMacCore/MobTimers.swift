import Foundation

/// When each mob is back. A bug run only goes for a mob whose timer has run out.
/// Times are Unix seconds, so a restart of the app does not forget a kill.
/// Respawn times are Natro's (game facts). A mob with no entry has no timer and is always ready.
public struct MobTimers: Equatable, Sendable {
    public static let respawn: [String: TimeInterval] = [
        "ladybug": 330, "rhino beetle": 330, "spider": 1830, "mantis": 1230, "scorpion": 1230,
        "werewolf": 3630, "king beetle": 24 * 3600, "coconut crab": 36 * 3600,
        // Timed pickups (Natro's cooldowns): same timer logic, not mobs.
        "wealth clock": 3600, "honey dispenser": 3600, "treat dispenser": 3600,
        "blueberry dispenser": 4 * 3600, "strawberry dispenser": 4 * 3600, "coconut dispenser": 4 * 3600,
        "honeystorm": 4 * 3600, "ant pass": 2 * 3600, "robo pass": 22 * 3600,
    ]
    public static let pickups = ["wealth clock", "honey dispenser", "treat dispenser", "blueberry dispenser",
                                 "strawberry dispenser", "coconut dispenser", "honeystorm", "ant pass", "robo pass"]

    public private(set) var lastDone: [String: TimeInterval] = [:]

    public init(lastDone: [String: TimeInterval] = [:]) { self.lastDone = lastDone }

    /// Seconds until the mob is back. 0 means ready.
    public func remaining(_ mob: String, now: TimeInterval) -> TimeInterval {
        guard let wait = Self.respawn[mob], let done = lastDone[mob] else { return 0 }
        return max(0, done + wait - now)
    }

    public func isReady(_ mob: String, now: TimeInterval) -> Bool { remaining(mob, now: now) == 0 }

    /// The selected mobs that are back, in the order given.
    public func due(_ selected: [String], now: TimeInterval) -> [String] {
        selected.filter { isReady($0, now: now) }
    }

    public mutating func markDone(_ mob: String, at now: TimeInterval) { lastDone[mob] = now }

    public static func load(_ url: URL) -> MobTimers {
        guard let data = try? Data(contentsOf: url),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Double] else { return MobTimers() }
        return MobTimers(lastDone: obj)
    }

    public func save(to url: URL) {
        try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        if let data = try? JSONSerialization.data(withJSONObject: lastDone, options: [.sortedKeys]) { try? data.write(to: url, options: .atomic) }
    }

    /// "ready", "back in 4 min", "back in 3 h".
    public static func describeDuration(_ seconds: TimeInterval) -> String {
        seconds < 3600 ? "\(Int((seconds / 60).rounded(.up))) min" : String(format: "%.1f h", seconds / 3600)
    }

    public static func describe(remaining: TimeInterval, timed: Bool) -> String {
        if !timed { return "no timer" }
        if remaining <= 0 { return "ready" }
        if remaining < 3600 { return "back in \(Int((remaining / 60).rounded(.up))) min" }
        return String(format: "back in %.1f h", remaining / 3600)
    }
}
