import Foundation

/// One instruction in a recorded walk. Same JSON as the Python app (`config/paths/**/*.json`),
/// so both apps read the same files. Fields that do not apply to a step type are absent.
public struct Step: Codable, Equatable, Sendable {
    public var type: String
    public var keys: [String] = []
    public var tiles: Double = 0
    public var seconds: Double = 0
    public var direction: String = ""
    public var key: String = ""
    public var count: Int = 1

    public init(type: String) { self.type = type }

    public static func walk(_ keys: [String], tiles: Double) -> Step {
        var s = Step(type: "walk"); s.keys = keys; s.tiles = tiles; return s
    }
    public static func hold(_ keys: [String], seconds: Double) -> Step {
        var s = Step(type: "hold"); s.keys = keys; s.seconds = seconds; return s
    }
    public static func wait(_ seconds: Double) -> Step {
        var s = Step(type: "wait"); s.seconds = seconds; return s
    }
    public static func tap(_ key: String, count: Int = 1) -> Step {
        var s = Step(type: "tap"); s.key = key; s.count = count; return s
    }
    public static func rotate(_ direction: String, count: Int = 1) -> Step {
        var s = Step(type: "rotate"); s.direction = direction; s.count = count; return s
    }

    enum CodingKeys: String, CodingKey { case type, keys, tiles, seconds, direction, key, count }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = try c.decode(String.self, forKey: .type)
        keys = try c.decodeIfPresent([String].self, forKey: .keys) ?? []
        tiles = try c.decodeIfPresent(Double.self, forKey: .tiles) ?? 0
        seconds = try c.decodeIfPresent(Double.self, forKey: .seconds) ?? 0
        direction = try c.decodeIfPresent(String.self, forKey: .direction) ?? ""
        key = try c.decodeIfPresent(String.self, forKey: .key) ?? ""
        count = try c.decodeIfPresent(Int.self, forKey: .count) ?? 1
    }

    /// Writes only the fields that matter, like the Python `to_dict`.
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(type, forKey: .type)
        if !keys.isEmpty { try c.encode(keys, forKey: .keys) }
        if tiles != 0 { try c.encode(tiles, forKey: .tiles) }
        if seconds != 0 { try c.encode(seconds, forKey: .seconds) }
        if !direction.isEmpty { try c.encode(direction, forKey: .direction) }
        if !key.isEmpty { try c.encode(key, forKey: .key) }
        if count != 1 { try c.encode(count, forKey: .count) }
    }
}

public struct PathFile: Codable, Equatable, Sendable {
    public var name: String
    public var steps: [Step]
    public var source: String = ""
    /// Walk speed the `hold` steps were recorded at.
    public var walkSpeed: Double = 28
    public var notes: String = ""

    public init(name: String, steps: [Step]) { self.name = name; self.steps = steps }

    enum CodingKeys: String, CodingKey {
        case name, steps, source, notes
        case walkSpeed = "walk_speed"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = try c.decode(String.self, forKey: .name)
        steps = try c.decodeIfPresent([Step].self, forKey: .steps) ?? []
        source = try c.decodeIfPresent(String.self, forKey: .source) ?? ""
        walkSpeed = try c.decodeIfPresent(Double.self, forKey: .walkSpeed) ?? 28
        notes = try c.decodeIfPresent(String.self, forKey: .notes) ?? ""
    }

    public static func load(_ url: URL) throws -> PathFile {
        try JSONDecoder().decode(PathFile.self, from: Data(contentsOf: url))
    }
}

public enum Paths {
    /// Natro's nm_gotoRamp: forward 5 tiles, then right 9.2 * slot - 4 tiles (slot 1 to 6).
    public static func gotoRampSteps(hiveSlot: Int) -> [Step] {
        let slot = Double(min(6, max(1, hiveSlot)))
        return [.walk(["w"], tiles: 5), .walk(["d"], tiles: 9.2 * slot - 4)]
    }

    /// Replaces the symbolic `gotoramp` step with walks for the player's hive slot.
    public static func expand(_ steps: [Step], hiveSlot: Int) -> [Step] {
        steps.flatMap { $0.type == "gotoramp" ? gotoRampSteps(hiveSlot: hiveSlot) : [$0] }
    }

    /// Natro nm_GoGather: TC = toward centre, AFC = away from centre.
    public static func bindPatternKeys(invertFB: Bool = false, invertLR: Bool = false) -> [String: String] {
        [
            "tc_fb": invertFB ? "s" : "w",
            "afc_fb": invertFB ? "w" : "s",
            "tc_lr": invertLR ? "d" : "a",
            "afc_lr": invertLR ? "a" : "d",
        ]
    }

    /// Scales a hold recorded at one walk speed to another (t * 28 / speed).
    public static func keyDuration(_ secondsAtReference: Double, referenceSpeed: Double, actualSpeed: Double) -> Double {
        actualSpeed <= 0 ? secondsAtReference : secondsAtReference * referenceSpeed / actualSpeed
    }

    /// Rescales `hold` steps that move the character; `walk` steps are in tiles and scale when run.
    public static func scaleHolds(_ steps: [Step], recordedSpeed: Double, actualSpeed: Double) -> [Step] {
        let movement: Set<String> = ["w", "a", "s", "d"]
        return steps.map { s in
            guard s.type == "hold", !Set(s.keys).isDisjoint(with: movement) else { return s }
            return .hold(s.keys, seconds: keyDuration(s.seconds, referenceSpeed: recordedSpeed, actualSpeed: actualSpeed))
        }
    }

    /// Rough duration for logging and timeouts.
    public static func totalSeconds(_ steps: [Step], speed: Double) -> Double {
        steps.reduce(0) { t, s in
            switch s.type {
            case "walk": return t + s.tiles * 4.0 / max(1, speed)
            case "hold", "wait": return t + s.seconds
            case "rotate", "tap", "zoom": return t + 0.06 * Double(s.count)
            default: return t
            }
        }
    }

    public static func fieldSlug(_ name: String) -> String {
        let lower = name.trimmingCharacters(in: .whitespaces).lowercased()
        var out = "", lastUnderscore = true
        for ch in lower {
            if ch.isASCII && (ch.isLetter || ch.isNumber) { out.append(ch); lastUnderscore = false }
            else if !lastUnderscore { out.append("_"); lastUnderscore = true }
        }
        while out.hasSuffix("_") { out.removeLast() }
        return out
    }
}
