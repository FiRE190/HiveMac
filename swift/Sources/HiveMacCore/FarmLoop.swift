import Foundation

public struct LoopStats: Equatable, Sendable {
    public var cycles = 0
    public var converts = 0
    public var deaths = 0
    public var resets = 0
    public var failedResets = 0
    public var lastResult = ""
    public var history: [GatherResult] = []
    public init() {}
}

/// The farming loop: reset to the hive, convert, travel, gather, walk back (or reset), repeat,
/// rotating through the enabled fields. A death or a lost screen falls back to the reset.
public final class FarmLoop {
    public let game: Game
    public let fields: [FieldConfig]
    public private(set) var stats = LoopStats()
    public var onStats: (LoopStats) -> Void = { _ in }
    private let maxCycles: Int?
    private let maxFailed: Int
    private var index = 0

    public init(_ game: Game, fields: [FieldConfig], maxCycles: Int? = nil, maxFailedResets: Int = 3) {
        self.game = game
        self.fields = fields.filter(\.enabled)
        self.maxCycles = maxCycles
        self.maxFailed = maxFailedResets
    }

    private func nextField() -> FieldConfig {
        let f = fields[index % fields.count]
        index += 1
        return f
    }

    /// Returns why the loop ended: stopped, no_fields, reset_failed, cycles_done.
    public func run() -> String {
        let g = game
        if fields.isEmpty { g.status("error", "no enabled fields"); return "no_fields" }
        var afterDeath = false
        while !g.stopped {
            if let m = maxCycles, stats.cycles >= m { return "cycles_done" }
            let f = nextField()
            stats.resets += 1
            if !g.resetToHive(afterDeath: afterDeath) {
                if g.stopped { break }
                stats.failedResets += 1
                onStats(stats)
                if stats.failedResets >= maxFailed {
                    g.status("error", "giving up after repeated reset failures")
                    g.releaseEverything()
                    return "reset_failed"
                }
                continue
            }
            stats.failedResets = 0
            afterDeath = false
            if g.convert() { stats.converts += 1 }
            if g.stopped { break }
            if !g.travelTo(f) { continue }
            let result = g.gather(f)
            stats.cycles += 1
            stats.lastResult = result.reason
            stats.history.append(result)
            if result.reason == "death" { stats.deaths += 1; afterDeath = true }
            onStats(stats)
            if (result.reason == "backpack" || result.reason == "time") && f.returnMethod == "walk" {
                if g.walkBack(f), g.convert() { stats.converts += 1 }
                // the loop still resets before the next field: that keeps the camera and position known
            }
        }
        g.releaseEverything()
        return "stopped"
    }
}
