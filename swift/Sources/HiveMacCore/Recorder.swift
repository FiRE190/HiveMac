import Foundation

public struct KeyEvent: Equatable, Sendable {
    public var t: Double
    public var key: String
    public var down: Bool
    public init(t: Double, key: String, down: Bool) { self.t = t; self.key = key; self.down = down }
}

/// Turns timestamped key presses into path steps (same rules as the Python recorder).
/// Movement keys held together become one walk, in tiles, so the route replays at any speed.
public enum Recorder {
    static let move: Set<String> = ["w", "a", "s", "d"]
    static let rotate = [",": "left", ".": "right"]
    static let zoom = ["i": "in", "o": "out"]
    static let taps: Set<String> = ["space", "e", "1", "2", "3", "4", "5", "6", "7"]

    public static func steps(from events: [KeyEvent], walkSpeed: Double, minGap: Double = 0.25) -> [Step] {
        var out: [Step] = []
        var held: [String: Double] = [:]
        var lastEnd: Double?
        let order = "wasd"

        func addWait(_ now: Double) {
            if let e = lastEnd, now - e >= minGap, held.isEmpty { out.append(.wait(((now - e) * 1000).rounded() / 1000)) }
        }
        func close(_ now: Double) {
            guard !held.isEmpty else { return }
            let start = held.values.max() ?? now
            let dur = now - start
            if dur > 0.01 {
                let tiles = (dur * walkSpeed / studsPerTile * 1000).rounded() / 1000
                let keys = held.keys.sorted { order.firstIndex(of: Character($0))! < order.firstIndex(of: Character($1))! }
                if let last = out.last, last.type == "walk", last.keys == keys {
                    out[out.count - 1].tiles = ((last.tiles + tiles) * 1000).rounded() / 1000
                } else {
                    out.append(.walk(keys, tiles: tiles))
                }
            }
            for k in held.keys { held[k] = now }
            lastEnd = now
        }

        let sorted = events.sorted { $0.t < $1.t }
        for e in sorted {
            let k = e.key.lowercased()
            if move.contains(k) {
                if e.down {
                    if held[k] != nil { continue }
                    if !held.isEmpty { close(e.t) } else { addWait(e.t) }
                    held[k] = e.t
                } else {
                    guard held[k] != nil else { continue }
                    close(e.t)
                    held[k] = nil
                }
                continue
            }
            guard e.down else { continue }
            if !held.isEmpty { close(e.t) } else { addWait(e.t) }
            if let d = rotate[k] {
                if let last = out.last, last.type == "rotate", last.direction == d { out[out.count - 1].count += 1 }
                else { out.append(.rotate(d, count: 1)) }
            } else if let d = zoom[k] {
                if let last = out.last, last.type == "zoom", last.direction == d { out[out.count - 1].count += 1 }
                else { var s = Step(type: "zoom"); s.direction = d; s.count = 1; out.append(s) }
            } else if taps.contains(k) {
                out.append(.tap(k, count: 1))
            } else { continue }
            lastEnd = e.t
        }
        if !held.isEmpty { close(sorted.last?.t ?? 0) }
        return out
    }
}

public extension PathFile {
    func save(to url: URL) throws {
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        let enc = JSONEncoder(); enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        try enc.encode(self).write(to: url, options: .atomic)
    }
}
