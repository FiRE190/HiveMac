import Foundation

/// Gather patterns, ported from Natro Macro's patterns/*.ahk. Each pattern builds a list of
/// steps with abstract keys (tc_fb, afc_fb, tc_lr, afc_lr: toward or away from the field
/// centre). Sizes: xs 0.25, s 0.5, m 1, l 1.5, xl 2. `reps` is Natro's "width".
public enum Patterns {
    public static let abstractKeys = ["tc_fb", "afc_fb", "tc_lr", "afc_lr"]
    public static let sizeFactors: [String: Double] = ["xs": 0.25, "s": 0.5, "m": 1.0, "l": 1.5, "xl": 2.0]

    private static let tcFB = "tc_fb", afcFB = "afc_fb", tcLR = "tc_lr", afcLR = "afc_lr"

    public static func sizeFactor(_ size: String) -> Double { sizeFactors[size.lowercased()] ?? 1.0 }

    private static func w(_ k: String, _ t: Double) -> Step { .walk([k], tiles: t) }
    private static func w(_ k: [String], _ t: Double) -> Step { .walk(k, tiles: t) }

    public typealias Builder = (_ size: Double, _ reps: Int, _ facingCorner: Int) -> [Step]

    public static let all: [String: Builder] = [
        "snake": snake, "lines": lines, "squares": squares, "diamonds": diamonds, "slimline": slimline,
        "xsnake": xsnake, "corner_x_snake": cornerXSnake, "fork": fork, "e_lol": eLol,
        "supercat": supercat, "stationary": { _, _, _ in [.wait(10)] },
    ]

    public static var names: [String] { all.keys.sorted() }

    public static func build(_ name: String, size: String = "m", width: Int = 1, facingCorner: Int = 0) throws -> [Step] {
        let key = name.lowercased().replacingOccurrences(of: " ", with: "_").replacingOccurrences(of: "-", with: "_")
        guard let fn = all[key] else { throw PatternError.unknown(name) }
        return fn(sizeFactor(size), max(1, width), facingCorner)
    }

    public enum PatternError: Error { case unknown(String) }

    static func snake(_ size: Double, _ reps: Int, _ fc: Int) -> [Step] {
        var out: [Step] = []
        for _ in 0..<reps { out += [w(tcLR, 11 * size), w(tcFB, 1), w(afcLR, 11 * size), w(tcFB, 1)] }
        for _ in 0..<reps { out += [w(tcLR, 11 * size), w(afcFB, 1), w(afcLR, 11 * size), w(afcFB, 1)] }
        return out
    }

    static func lines(_ size: Double, _ reps: Int, _ fc: Int) -> [Step] {
        var out: [Step] = []
        for _ in 0..<reps { out += [w(tcFB, 11 * size), w(tcLR, 1), w(afcFB, 11 * size), w(tcLR, 1)] }
        for _ in 0..<reps { out += [w(tcFB, 11 * size), w(afcLR, 1), w(afcFB, 11 * size), w(afcLR, 1)] }
        return out
    }

    static func squares(_ size: Double, _ reps: Int, _ fc: Int) -> [Step] {
        (1...reps).flatMap { i -> [Step] in
            let d = 5 * size + Double(i)
            return [w(tcFB, d), w(tcLR, d), w(afcFB, d), w(afcLR, d)]
        }
    }

    static func diamonds(_ size: Double, _ reps: Int, _ fc: Int) -> [Step] {
        (1...reps).flatMap { i -> [Step] in
            let d = 5 * size + Double(i)
            return [w([tcFB, tcLR], d), w([tcFB, afcLR], d), w([afcFB, afcLR], d), w([afcFB, tcLR], d)]
        }
    }

    static func slimline(_ size: Double, _ reps: Int, _ fc: Int) -> [Step] {
        [w(tcLR, 4 * size + Double(reps) * 0.1 - 0.1), w(afcLR, 8 * size), w(tcLR, 4 * size)]
    }

    private static func xsnakeBody(_ size: Double, extraTail: Double) -> (body: [Step], diag4: Double) {
        let diag8 = (2 * pow(8 * size, 2)).squareRoot()
        let diag4 = (2 * pow(4 * size, 2)).squareRoot()
        let body: [Step] = [
            w(tcLR, 4 * size), w(tcFB, 2 * size), w(afcLR, 8 * size), w(tcFB, 2 * size),
            w(tcLR, 8 * size), w([afcLR, afcFB], diag8), w(tcLR, 8 * size), w(tcFB, 2 * size),
            w(afcLR, 8 * size), w(tcFB, 6.7 * size + extraTail),
        ]
        return (body, diag4)
    }

    private static func xsnakeReturn(_ size: Double, diag4: Double) -> [Step] {
        [w(tcLR, 8 * size), w(afcFB, 2 * size), w(afcLR, 8 * size), w(afcFB, 2 * size),
         w(tcLR, 8 * size), w(afcFB, 2 * size), w(afcLR, 8 * size), w(afcFB, 3 * size),
         w(tcLR, 8 * size), w([tcFB, afcLR], diag4)]
    }

    static func xsnake(_ size: Double, _ reps: Int, _ fc: Int) -> [Step] {
        var out: [Step] = []
        for _ in 0..<reps {
            let (body, diag4) = xsnakeBody(size, extraTail: 0)
            out += body + xsnakeReturn(size, diag4: diag4)
        }
        return out
    }

    static func cornerXSnake(_ size: Double, _ reps: Int, _ fc: Int) -> [Step] {
        let (body, diag4) = xsnakeBody(size, extraTail: 10)
        var out = body
        // corner alignment: push into the corner, back out, then the return half
        out += [w(afcLR, 6 + Double(reps)), w([afcLR, tcFB], 3), w(tcLR, 2 + Double(reps)), w(afcFB, 5)]
        out += xsnakeReturn(size, diag4: diag4)
        return out
    }

    static func fork(_ size: Double, _ reps: Int, _ fc: Int) -> [Step] {
        let gap = 0.75
        let diag = gap * 2.0.squareRoot()
        let length = (40 - gap * 16 - diag * 4) / 6
        var out: [Step] = []
        if fc != 0 { out.append(w("w", 1.5)) }
        out += [w([tcLR, afcFB], diag * 2), w(tcLR, (Double(reps - 1) * 4 + 2) * gap), w([tcLR, tcFB], diag * 2)]
        for _ in 0..<reps {
            out += [w(tcFB, length * size), w(afcLR, gap * 2), w(afcFB, length * size), w(afcLR, gap * 2)]
        }
        out += [w(tcFB, length * size), w(afcLR, gap * 2), w(afcFB, length * size)]
        return out
    }

    static func eLol(_ size: Double, _ reps: Int, _ fc: Int) -> [Step] {
        let spacing = 274.0 * 9 / 2000
        let long = (1094 + 25 * Double(fc)) * 9 / 2000 * size
        let r = Double(reps)
        var out: [Step] = [w(tcLR, spacing * (r * 2 + 1)), w(afcFB, 5 * size)]
        for _ in 0..<reps {
            out += [w(afcLR, spacing), w(tcFB, 5 * size), w(afcLR, spacing), w(afcFB, long)]
        }
        out += [w(tcLR, spacing * (r * 2 + 0.5)), w(tcFB, 5 * size)]
        for _ in 0..<reps {
            out += [w(afcLR, spacing), w(afcFB, long), w(afcLR, spacing * 1.5), w(tcFB, 5 * size)]
        }
        return out
    }

    static func supercat(_ size: Double, _ reps: Int, _ fc: Int) -> [Step] {
        var out: [Step] = []
        for _ in 0..<reps {
            out += [w(tcLR, 1.25 * size), w(tcFB, 7 * size), w(tcLR, 1.25 * size), w(afcFB, 6.66 * size),
                    w(tcLR, 1.25 * size), w(tcFB, 7 * size), w(tcLR, 2 * size), w(afcFB, 6.5 * size)]
        }
        for _ in 0..<reps {
            out += [w(afcLR, 1.25 * size), w(tcFB, 7 * size), w(afcLR, 1 * size), w(afcFB, 6.66 * size),
                    w(afcLR, 1.25 * size), w(tcFB, 7 * size), w(afcLR, 1.25 * size), w(afcFB, 6.5 * size)]
        }
        return out
    }
}

/// Natro's per field defaults (nm_importFieldDefaults).
public struct FieldDefault: Equatable, Sendable {
    public var pattern: String
    public var size: String
    public var width: Int
    public var camera: String
    public var turns: Int
    public var sprinkler: String
    public var distance: Int
    public var invertFB: Bool
    public var invertLR: Bool
}

public enum FieldDefaults {
    private static func d(_ pattern: String, _ size: String, _ width: Int, _ camera: String, _ turns: Int,
                          _ sprinkler: String, _ distance: Int, fb: Bool = false, lr: Bool = false) -> FieldDefault {
        FieldDefault(pattern: pattern, size: size, width: width, camera: camera, turns: turns,
                     sprinkler: sprinkler, distance: distance, invertFB: fb, invertLR: lr)
    }

    /// Ordered like Natro's field list.
    public static let order = ["sunflower", "dandelion", "mushroom", "blue flower", "clover", "strawberry", "spider",
                               "bamboo", "pineapple", "stump", "cactus", "pumpkin", "pine tree", "rose", "pepper",
                               "coconut", "mountain top"]

    public static let table: [String: FieldDefault] = [
        "sunflower": d("corner_x_snake", "m", 4, "none", 1, "upper left", 8, lr: true),
        "dandelion": d("corner_x_snake", "m", 6, "none", 1, "upper left", 10, lr: true),
        "mushroom": d("corner_x_snake", "m", 2, "none", 1, "upper left", 8, lr: true),
        "blue flower": d("corner_x_snake", "m", 7, "right", 2, "center", 1),
        "clover": d("stationary", "s", 1, "none", 1, "center", 1),
        "strawberry": d("corner_x_snake", "m", 4, "right", 2, "upper left", 6, lr: true),
        "spider": d("corner_x_snake", "m", 4, "none", 1, "upper left", 8, lr: true),
        "bamboo": d("corner_x_snake", "m", 6, "left", 2, "upper left", 8),
        "pineapple": d("corner_x_snake", "m", 6, "left", 1, "upper left", 8, lr: true),
        "stump": d("squares", "s", 2, "right", 2, "lower right", 3),
        "cactus": d("e_lol", "s", 3, "none", 1, "center", 1),
        "pumpkin": d("corner_x_snake", "s", 3, "none", 1, "upper right", 7),
        "pine tree": d("corner_x_snake", "s", 4, "left", 2, "upper left", 8),
        "rose": d("corner_x_snake", "m", 3, "right", 2, "lower right", 7),
        "pepper": d("e_lol", "m", 2, "left", 2, "upper right", 3),
        "coconut": d("corner_x_snake", "s", 3, "right", 4, "upper right", 5),
        "mountain top": d("corner_x_snake", "m", 3, "none", 1, "left", 3, fb: true),
    ]
}
